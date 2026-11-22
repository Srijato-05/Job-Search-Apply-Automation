# Technical Reference: Job Collectors, ATS Feeds, Circuit Breakers & Pruner

This document details the exact execution mechanisms, data flows, safety constraints, and circuit-breaker telemetry governing the collection engine implemented in **Cycle 3**.

---

## 1. Architectural Overview & Collection Tiers

The system uses a tiered ingestion strategy to balance data freshness against anti-bot friction:

```
+-----------------------------------------------------------------------------------------+
|                                Collection Engine (Cycle 3)                              |
+-----------------------------------------------------------------------------------------+
       |                                                                           |
       v                                                                           v
 [ Tier 3: Direct ATS Feeds ]                                       [ Tier 1: JobSpy Aggregator ]
   - Polled every 4h via Async HTTP                                   - On-demand / Nightly batches
   - Zero-bot friction (Official JSON APIs)                           - Multi-portal: Naukri, LinkedIn, Indeed
   - 68 Pre-seeded Indian Tech firms & GCCs                           - Polite Jitter (4-8s), hours_old=24
   - Greenhouse / Lever / Ashby / SmartRecruiters / Workday           - Credential safety & rate limit traps
       |                                                                           |
       +------------------------------------+--------------------------------------+
                                            |
                                            v
                              [ Location Filter: India Only ]
                                - Excludes US/EMEA foreign jobs
                                - Identifies 22 Indian cities + Remote India
                                            |
                                            v
                            [ 5-Gate Pipeline & Orchestrator ]
                                - Gate 3A: Strips boilerplate, 10 fields
                                - Gate 1: Dealbreakers & audit trail
                                - Gate 2: Sibling roles & Req ID dedup
                                - Gate 4: Combined Option 1+3 scoring
                                            |
                                            v
                              [ Closed-Job Auto-Pruner ]
                                - Compares active DB jobs with ATS feed
                                - Marks vanished jobs as status="closed"
```

---

## 2. Direct ATS Connectors & API Specifications

### 2.1. Greenhouse (`ats_greenhouse.py`)
- **Endpoint:** `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
- **Mechanism:** Fetches official public job board JSON with full HTML descriptions (`content`).
- **Data Extracted:** `id`, `title`, `location.name`, `content`, `absolute_url`, `departments`.
- **Location Filter:** Passes `location.name` through `is_india_location()`.

### 2.2. Lever (`ats_lever.py`)
- **Endpoint:** `GET https://api.lever.co/v0/postings/{company_name}?mode=json`
- **Mechanism:** Fetches open postings directly from Lever's public postings API.
- **Data Extracted:** `id`, `text`, `hostedUrl`, `applyUrl`, `categories.location`, `categories.allLocations`, `descriptionPlain`, `additionalPlain`.
- **Text Composition:** Combines `descriptionPlain` and `additionalPlain` into clean plaintext.

### 2.3. Ashby (`ats_ashby.py`)
- **Endpoint:** `GET https://api.ashbyhq.com/posting-api/job-board/{company_name}?includeCompensation=true`
- **Mechanism:** Queries Ashby's public board API with compensation metadata included.
- **Data Extracted:** `id`, `title`, `locationName`, `secondaryLocations`, `jobUrl`, `descriptionHtml`, `compensation`.

### 2.4. SmartRecruiters (`ats_smartrecruiters.py`)
- **Endpoint:** `GET https://api.smartrecruiters.com/v1/companies/{company_id}/postings?limit=100`
- **Mechanism:** Queries postings list with country filter (`country == "in"` or Indian city text). Optional secondary call fetches deep job ad details (`jobAd.sections`).

### 2.5. Workday CXS API (`ats_workday.py`)
- **Endpoint:** `POST https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
- **Hard Constraints & Loop Guards:**
  1. **Strict Limit Guard:** Enforces `limit <= 20` in all JSON POST bodies. Workday CXS endpoints return `400 Bad Request` if `limit > 20`.
  2. **Loop Stop Condition:** Terminates pagination loop when `offset >= total` or when returned `jobPostings` length is 0.
  3. **Runaway Cap:** Hard-capped at 50 pages (1,000 jobs maximum per run).
  4. **Requisition ID Extraction:** Parses `bulletFields` or extracts `JR[-_]?\d{3,}` from `externalPath`.
  5. **Detail Enrichment:** Resolves `GET .../job/{externalPath}` to extract complete structured description.

---

## 3. Circuit Breaker & Telemetry State Machine

Every collector run is registered in the `collector_runs` SQLite table.

### 3.1. Cooldown Triggering
When any collector encounters:
- `HTTP 429` (Too Many Requests / Rate Limited)
- `HTTP 403` (Forbidden / Cloudflare Bot Protection)
- Anti-bot / CAPTCHA challenge pages

The collector immediately calls:
```python
collector.trip_circuit_breaker(
    session=session,
    reason=f"HTTP {status_code}: {err}",
    cooldown_hours=8,
    company_slug=company.slug,
)
```

### 3.2. State Transitions
1. `running` → Collector starts execution.
2. `ok` → Successful run, `fetched_count`, `new_count`, and `closed_count` logged.
3. `cooldown` → `cooldown_until = now() + 8h`. Company `health_status` set to `"cooldown"`.
4. Subsequent runs for this company or source are **instantly rejected** without making outbound HTTP requests until `cooldown_until` expires (unless overridden with `force=True`).
5. Fault isolation: A cooldown on one company (e.g. `walmart-global-tech`) does not abort or interrupt other companies.

---

## 4. Closed-Job Auto-Pruner Flow (`pruner.py`)

Direct ATS feeds are authoritative snapshots of a company's currently open roles.
When a role is unlisted or filled, it disappears from the feed.

```
                    +--------------------------------+
                    |  Fetch Latest Company ATS Feed |
                    +--------------------------------+
                                   |
                                   v
             [ Extract active_external_ids & active_urls ]
                                   |
                                   v
             [ Query DB: Job.company_slug == slug AND status == 'active' ]
                                   |
                                   v
                     +----------------------------+
                     | For each active DB Job:    |
                     | Is JobSource ID or URL in  |
                     | the active feed set?       |
                     +----------------------------+
                              /          \
                           YES            NO
                           /                \
                     [ Keep Active ]    [ Mark Job.status = 'closed' ]
                                        [ Log in CollectorRun.closed_count ]
```

**Safety Guard:** If an ATS feed returns 0 jobs unexpectedly (e.g. temporary outage or network error), the pruner skips execution to prevent accidental mass-closure of active jobs.

---

## 5. JobSpy Multi-Portal Aggregator Flow (`jobspy_collector.py`)

- **Dynamic Query Generation:** Extracts `target_titles_json` and `search_locations_json` from active user resumes in the database.
- **Polite Jitter:** Injects `random.uniform(jobspy_min_delay_sec, jobspy_max_delay_sec)` between queries.
- **Incremental Crawling:** Uses `hours_old=24` to ingest only fresh listings.
- **Deduplication Check:** Before invoking `orchestrator.ingest_job`, checks `job_sources.job_url` in SQLite.
- **Graceful Fallback:** If `python-jobspy` is not installed, logs a clear notification without raising unhandled exceptions or failing the system.

---

## 6. Pre-Seeded Watchlist (`watchlist_seed.json`)

Pre-populated with 68 premier Indian tech companies across:
- **Greenhouse:** Razorpay, Postman, Meesho, BrowserStack, CRED, Swiggy, Groww, Freshworks, Chargebee, CleverTap, Hasura, Zepto, Apna, Khatabook, Innovaccer, Darwinbox, Druva, InMobi, Udaan, Ather Energy, Slice, Jupiter, Urban Company, Shiprocket, Classplus, Quizizz, ShareChat, Licious, CoinSwitch, Navi, Porter, MPL.
- **Lever:** Atlassian, Rubrik, Confluent, Docker, GitLab, Fivetran, Databricks, ThoughtSpot, Nutanix, Cohesity, FalconX, Vercel, PostHog, Sourcegraph.
- **Ashby:** Rippling, Ramp, Deel, Linear, Retool, Notion, Figma, OpenAI, Cursor / Anysphere.
- **SmartRecruiters:** Publicis Sapient, Delivery Hero, Bosch Group, Ubisoft, Visa.
- **Workday:** Walmart Global Tech, Salesforce, NVIDIA, Adobe, Cisco, Target in India, Intuit, Mastercard, PayPal.

Synchronization via `POST /api/v1/watchlist/seed` inserts new entries and updates configurations while preserving custom user status (`is_watched`, `is_blacklisted`).

---

## 7. Incremental Detail Fetching, Portal Expirations & Checkpoints (Cycle 3.5)

### 7.1. Incremental Detail Fetching (Workday & SmartRecruiters)
- **Initial Run:** `known_external_ids` is empty, so **100%** of India job detail pages are downloaded.
- **Repeat Runs:** The list endpoint is *always* fetched in full (so the Closed-Job Pruner still has the complete active ID set), while per-job detail HTTP calls are skipped for `external_job_id`s already present in `job_sources` (unless `force_refresh_details=true`).

### 7.2. Direct ATS vs. Job Portals (LinkedIn, Naukri, Indeed)
- **Initial vs. Daily Window:** JobSpy supports `hours_old` up to `720` (30 days) for initial seeding via `POST /api/v1/collectors/run` and defaults to `hours_old=24` for daily polite sweeps.
- **Expirations:** The ATS Closed-Job Pruner **never** runs on JobSpy/portal jobs (since a listing absent from a 24-hour search may simply be 3 days old). Portal expirations are detected by the Chromium Extension `"Expired"` Watcher (Cycle 6).
- **Progress Tracking:** Exposed via `GET /api/v1/collectors/progress` — ATS sweeps report `completed / total` companies; JobSpy sweeps report bounded query batches (`titles × cities`).

### 7.3. Checkpoints, Failsafes & Scale Safeguards
- **Stale Run Recovery:** On server boot, `recover_stale_runs()` marks any `collector_runs` row stuck in `"running"` (from crash/restart) as `"interrupted"`.
- **Resumable Sweep Checkpoint:** `collect_all_watched()` skips companies already successfully polled within the last `30` minutes (when `force=False`) so an interrupted sweep resumes where it left off.
- **Watchlist Verifier:** `POST /api/v1/watchlist/verify` concurrently probes all watched ATS boards (`asyncio.Semaphore`) and flags `404` boards as `health_status="invalid_config"`.
- **Composite SQLite Indexes:** `idx_jobs_company_status`, `idx_jobs_identity_lookup`, `idx_collector_runs_lookup`, and `idx_job_sources_job_portal` keep queries fast at 10,000+ jobs.
- **Rotating Local Logs & Online Snapshots:** `data/app.log` is hard-capped at `20 MB` (`5 MB × 3` backups), and `create_sqlite_snapshot()` uses SQLite's WAL-safe `conn.backup()` API keeping the last 5 rolling snapshots in `data/backups/`.

