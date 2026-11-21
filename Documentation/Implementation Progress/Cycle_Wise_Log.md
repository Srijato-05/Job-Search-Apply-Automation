# Cycle-Wise Implementation Log

Chronological record of everything built, tested, and fixed through **Cycle 3**.

---

## Phase 0: Repository Setup & Stage 1–2 Documentation

- **Stage 1 Research Docs:** Created 5 files in [Documentation/Innitial Research/README.md](file:///f:/Projects/JobAutomation/Documentation/Innitial%20Research/README.md) covering India-first portals, multi-resume routing, combined Option 1 + Option 3 scoring, Sibling Role diffing, and zero-hallucination Chromium autofill.
- **Stage 2 Planning Docs:** Created 5 files in [Documentation/Planning/README.md](file:///f:/Projects/JobAutomation/Documentation/Planning/README.md) defining the 10-table SQLite schema, `/api/v1` REST contracts, safety/anti-flagging rules, boilerplate stripping, frontend/extension architecture, and 7 Code & Test Cycles.
- **Repository Hygiene & Skeleton:** Created [.gitignore](file:///f:/Projects/JobAutomation/.gitignore) (strictly excluding `data/jobs.db`, `.local_token`, `data/resumes/*`, `data/backups/*`, `.env`), [.gitattributes](file:///f:/Projects/JobAutomation/.gitattributes), [.editorconfig](file:///f:/Projects/JobAutomation/.editorconfig), [.env.example](file:///f:/Projects/JobAutomation/.env.example), [README.md](file:///f:/Projects/JobAutomation/README.md), and monorepo `.gitkeep` directories (`data/`, `backend/`, `frontend/`, `extension/`).

---

## Cycle 1: Foundation, Loopback Security, SQLite WAL+FTS5, Fact Vault & Multi-Resume Vectorizer

### Built
1. **Virtual Environment & Dependencies:** Installed `FastAPI`, `Uvicorn`, `SQLModel`, `SQLAlchemy`, `pydantic-settings`, `pdfplumber`, `pypdf`, `fastembed` (`onnxruntime`), `numpy`, `pytest`, `httpx`, and `reportlab` via [requirements.txt](file:///f:/Projects/JobAutomation/backend/requirements.txt).
2. **Loopback Security & App Factory:** Built [config.py](file:///f:/Projects/JobAutomation/backend/app/config.py) and [main.py](file:///f:/Projects/JobAutomation/backend/app/main.py) generating `data/.local_token`, enforcing `X-Local-Token` via `hmac.compare_digest`, and restricting CORS to local UI origins and `chrome-extension://` origins.
3. **Database & FTS5:** Built all 10 SQLModel tables in [models.py](file:///f:/Projects/JobAutomation/backend/app/db/models.py) and WAL + foreign-key pragmas + `jobs_fts` triggers + BM25 query helper in [database.py](file:///f:/Projects/JobAutomation/backend/app/db/database.py).
4. **India Fact Vault, PII Guardrails & Taxonomy:** Implemented [pii_guard.py](file:///f:/Projects/JobAutomation/backend/app/vault/pii_guard.py) (PAN/Aadhaar/Passport/DoB/Bank/UAN blocklist), [taxonomy.py](file:///f:/Projects/JobAutomation/backend/app/vault/taxonomy.py) (22 Indian cities + Remote India, 35 localities, 500+ skill aliases), [templates.py](file:///f:/Projects/JobAutomation/backend/app/vault/templates.py), [schemas/vault.py](file:///f:/Projects/JobAutomation/backend/app/schemas/vault.py), and [api/vault.py](file:///f:/Projects/JobAutomation/backend/app/api/vault.py).
5. **Multi-Resume PDF Parser & Vectorizer:** Implemented [parser.py](file:///f:/Projects/JobAutomation/backend/app/resumes/parser.py), [embedder.py](file:///f:/Projects/JobAutomation/backend/app/resumes/embedder.py) (`BAAI/bge-small-en-v1.5` ONNX), [schemas/resumes.py](file:///f:/Projects/JobAutomation/backend/app/schemas/resumes.py), and [api/resumes.py](file:///f:/Projects/JobAutomation/backend/app/api/resumes.py) (upload, bullet embedding, byte-identical `/file` download, patch, reparse, cascade delete).

### Verification & Issues Resolved
- **FTS5 Test Assertion Fix:** `test_fts5_triggers_insert_update_delete_and_boolean_query` initially caught `role_subtag` still containing `"Kafka"` after updating `boilerplate_stripped_text`—updated both columns in the test fixture.
- **Sandbox `asyncio` Finding:** Python 3.12's `asyncio` loopback `socketpair` deadlocks inside the network-isolated Windows sandbox; running tests directly in visible PowerShell avoids this cleanly.
- **Cycle 1 Result:** **9 / 9 passed in 13.84s** in PowerShell, verifying ONNX Runtime loads natively on Windows and caches `BAAI/bge-small-en-v1.5` into `.fastembed_cache/`.

---

## Cycle 2: The 5-Gate Pipeline & `/api/v1/jobs` API

### Built
1. **Cycle 1 Warning Cleanup:** Replaced deprecated `HTTP_422_UNPROCESSABLE_ENTITY` with `HTTP_422_UNPROCESSABLE_CONTENT` in [vault.py](file:///f:/Projects/JobAutomation/backend/app/api/vault.py) and [resumes.py](file:///f:/Projects/JobAutomation/backend/app/api/resumes.py).
2. **Gate 3A Extractor ([gate3_extractor.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate3_extractor.py)):** HTML cleanup, corporate boilerplate removal (`About Us`, `Perks`, `Equal Opportunity`), requirement sentence segmentation, and deterministic 10-field extraction (mandatory vs. bonus skills, experience band, LPA salary, city/locality/work mode, notice constraint, `req_id`, `role_subtag`, `apply_friction`, `employer_type`).
3. **Gate 1 Filters ([gate1_filters.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate1_filters.py)):** Effective notice calculation (`LWD` > negotiable > official), company blacklist, negative title keywords, and extreme experience floor checks with non-destructive `hidden_by_gate1` + `hidden_reason`.
4. **Gate 2 Role Identity & Diff ([gate2_identity.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate2_identity.py)):** 4-layer fingerprint (`JobSource` lookup, Req ID isolation, SHA-256 + signed 64-bit SimHash + `0.88` vector / `0.70` skill-Jaccard threshold, Sibling Role linking via `parent_sibling_job_id`) plus `compute_jd_diff()`.
5. **Gate 4 Combined Scorer ([gate4_scorer.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate4_scorer.py)):** Combined Option 1 (`Tier S/A/B/C` + hard core-language guard) and Option 3 (L2 cosine bullet alignment + verbatim `bullet_proof_json`), winning resume selection, and Cross-Resume Bullet Alerts.
6. **Orchestrator & Jobs API ([orchestrator.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/orchestrator.py), [schemas/jobs.py](file:///f:/Projects/JobAutomation/backend/app/schemas/jobs.py), [api/jobs.py](file:///f:/Projects/JobAutomation/backend/app/api/jobs.py)):** Atomic ingestion plus `/api/v1/jobs` faceted filtering (`tier`, `resume_id`, `fresh_6h`, `missing_max`, `friction`, `city`, `only_hidden`, FTS5 `fts_query`), `/diff/{sibling_id}`, `/status`, and `/rescore`.

### Bugs Caught & Fixed During Cycle 2 Testing
1. **Domain Sub-Tag Misclassification:** `_DOMAIN_CUES` previously matched generic `"analytics"` under `"Data Platform"` before checking `"Frontend"`, mislabeling a React/TypeScript/Tailwind dashboard role. **Fix:** Removed generic `"analytics"`, added frontend cues, and switched from first-match `break` to weighted text + `domain_skill_map` scoring (`text_weight = 3` for specific team domains vs `2` for architectural layers).
2. **Hybrid Role Primary-Skill Cutoff:** `_compute_tier` required `len(missing_primary) <= 1` even for `Tier B`, wrongly assigning `Tier C` to a hybrid Backend+UI job where `Backend Track` matched `62.5%` of primary skills and `66.7%` of bullets. **Fix:** Added `primary_match_ratio` thresholds (`>= 0.75` for `Tier A`, `>= 0.50` for `Tier B`, `< 0.40` hard cap `Tier C`) while keeping the hard core-language `Tier C` guard intact.
3. **Workday Underscore Requisition ID (`_JR`):** In Python regex, `_` is a word character (`\w`), causing `\b(JR[-_]?\d{3,})\b` to miss Workday URLs like `.../FS_JR8801`. **Fix:** Switched to `(?<![A-Za-z0-9])(JR[-_]?\d{3,})(?![A-Za-z0-9])`; `py_compile` and `test_gate3` verified (`0.03s`).

---

## Cycle 2.5: De-Hardcoding & External Configuration Refactor

### Built
1. **Editable JSON Rule & Taxonomy Files (`backend/app/data/`):**
   - [india_locations.json](file:///f:/Projects/JobAutomation/backend/app/data/india_locations.json) — City aliases, 35 office localities, NCR compatibility group.
   - [skills_taxonomy.json](file:///f:/Projects/JobAutomation/backend/app/data/skills_taxonomy.json) — `core_languages`, ambiguous short-token sets, and 500+ skill synonym groups.
   - [pipeline_rules.json](file:///f:/Projects/JobAutomation/backend/app/data/pipeline_rules.json) — IT service firm names, specific team domains, domain regex cues, skill maps, backend fallback skills, and friction domains.
2. **Tunable `Settings` & `.env.example`:** Moved all 17 pipeline thresholds (`semantic_threshold`, `dedup_similarity_threshold`, `dedup_stack_overlap_threshold`, `gate1_exp_buffer_years`, `exp_fit_*`, `tier_*` cutoffs, `freshness_hours`, `jd_embed_max_chars`) and `allowed_cors_origins` into [config.py](file:///f:/Projects/JobAutomation/backend/app/config.py) and [.env.example](file:///f:/Projects/JobAutomation/.env.example), wired cleanly through [taxonomy.py](file:///f:/Projects/JobAutomation/backend/app/vault/taxonomy.py), [gate1_filters.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate1_filters.py), [gate2_identity.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate2_identity.py), [gate3_extractor.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate3_extractor.py), [gate4_scorer.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate4_scorer.py), [orchestrator.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/orchestrator.py), [api/jobs.py](file:///f:/Projects/JobAutomation/backend/app/api/jobs.py), and [main.py](file:///f:/Projects/JobAutomation/backend/app/main.py).
3. **Config & Data Tests ([test_config_and_data.py](file:///f:/Projects/JobAutomation/backend/tests/test_config_and_data.py)):** 3 unit tests proving JSON loading and dynamic `Settings` override propagation.

### Verification Status
- `py_compile` across all modified files + 4 pure-Python tests (`test_config_and_data.py` + `test_gate3`) passed in `0.24s`.
- Full 16-test suite (`.\.venv\Scripts\pytest.exe backend\tests -v`) passed cleanly in visible PowerShell.

---

## Cycle 3: Job Collectors (Tier 3 ATS + Tier 1 JobSpy), India Watchlist, Circuit Breaker, Pruner & Scheduler

### Built
1. **Pre-Seeded India Tech Watchlist (`backend/app/data/watchlist_seed.json`):**
   - 68 top Indian tech product companies, unicorns, and GCCs categorized across Greenhouse (32), Lever (14), Ashby (9), SmartRecruiters (5), and Workday (8).
   - Seed loader function `seed_watchlist(session)` syncs default watchlist on startup without overwriting customized user edits.
2. **Indian Location Filter (`location_filter.py`):**
   - Normalizes locations and filters out foreign postings (USA, UK, Canada, Germany, etc.) while recognizing 22 Indian cities, 35 IT hubs, and Remote India.
3. **Collector Telemetry & Circuit Breaker (`base.py`):**
   - Logs every collection run in `collector_runs`.
   - On `HTTP 429` (Rate Limited), `HTTP 403` (Forbidden/Cloudflare), or bot challenges, trips circuit breaker, sets `cooldown_until` (default +8 hours), marks company health as `cooldown`, and immediately skips execution during cooldown.
4. **Direct ATS Connectors:**
   - [ats_greenhouse.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_greenhouse.py): Official public boards API (`/v1/boards/{token}/jobs?content=true`), extracting full HTML JD and metadata.
   - [ats_lever.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_lever.py): Official public postings API (`/v0/postings/{company}?mode=json`), combining description and additional requirements.
   - [ats_ashby.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_ashby.py): Official job-board posting API (`/posting-api/job-board/{company}?includeCompensation=true`), extracting description and compensation.
   - [ats_smartrecruiters.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_smartrecruiters.py): Public postings API with India country filter (`country == "in"`), reference number extraction, and detail fetching.
   - [ats_workday.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_workday.py): Modern CXS POST endpoint (`/wday/cxs/{tenant}/{site}/jobs`) enforcing `limit <= 20`, pagination loop prevention (`offset >= total` stop), and requisition ID extraction.
5. **Closed-Job Pruner (`pruner.py`):**
   - Compares active database jobs for an ATS company against the feed's currently active external IDs and URLs; automatically marks vanished jobs as `status="closed"`.
6. **JobSpy Connector (`jobspy_collector.py`):**
   - Integrates `python-jobspy` with graceful fallback if not installed, random polite jitter (4–8s), search queries derived from active resume target titles, and deduplication against existing `job_sources`.
7. **Central Coordinator & Scheduler (`manager.py`, `scheduler.py`):**
   - `CollectorManager`: Coordinates ATS feeds, JobSpy aggregators, pruners, and health status reporting.
   - `CollectorScheduler`: Lightweight async background loop running periodic collection (e.g. every 4 hours) inside FastAPI lifecycle.
8. **Watchlist & Collectors API Endpoints:**
   - `/api/v1/watchlist`: `GET` (faceted search/filter), `POST` (add/update company), `PATCH /{slug}`, `DELETE /{slug}` (unwatch or hard delete), `POST /seed` (sync defaults).
   - `/api/v1/collectors/run`: On-demand manual trigger for `all`, `ats`, `jobspy`, or specific company slug (supports synchronous or `background=true`).
   - `/api/v1/collectors/health`: Aggregated health badges, cooldown countdowns, and success/failure statistics.
   - `/api/v1/collectors/runs`: Historical execution telemetry.
9. **Automated Unit Tests (`test_collectors.py`):**
   - 10 comprehensive tests covering location filtering, watchlist seeding and CRUD, mocked Greenhouse, Lever, Ashby, SmartRecruiters, Workday limit <= 20 & pagination safety, circuit breaker tripping on 429, closed-job pruner, and end-to-end manager execution.

### Bugs Caught & Fixed During Cycle 3 Testing
1. **`pytest-asyncio` Missing:** Test suite initially failed on `@pytest.mark.asyncio` because `pytest-asyncio` wasn't installed. **Fix:** Replaced `@pytest.mark.asyncio` decorators with native `asyncio.run()` wrappers inside sync test functions in [test_collectors.py](file:///f:/Projects/JobAutomation/backend/tests/test_collectors.py).
2. **Duplicate `CollectorRun` on HTTP 429 (`cooldown_until` was `None`):** `collect_company()` called `record_run_start()`, then `trip_circuit_breaker()` inserted a second `CollectorRun` row while `record_run_finish()` closed the first row without `cooldown_until`. **Fix:** Added `existing_run: Optional[CollectorRun] = None` to `BaseCollector.trip_circuit_breaker()` in [base.py](file:///f:/Projects/JobAutomation/backend/app/collectors/base.py) and passed `existing_run=run_record` in [manager.py](file:///f:/Projects/JobAutomation/backend/app/collectors/manager.py) so `cooldown_until` updates directly on the active run record.
3. **`MockEmbedder` Return Type Mismatch (`'list' object has no attribute 'size'`):** `MockEmbedder.embed_texts()` returned `list[list[float]]`, failing inside `gate2_identity.py` / `orchestrator.py` when accessing `.size`. **Fix:** Updated `MockEmbedder.embed_texts()` in [test_collectors.py](file:///f:/Projects/JobAutomation/backend/tests/test_collectors.py) to return a `float32` `np.ndarray` via `np.vstack`.
4. **`new_count` Staying `0` After Successful Ingestion:** `orchestrator.ingest_job()` returns `action="new_role"` / `"sibling_role"`, whereas collectors checked `("created_new", "created_sibling")`. **Fix:** Updated [manager.py](file:///f:/Projects/JobAutomation/backend/app/collectors/manager.py) and [jobspy_collector.py](file:///f:/Projects/JobAutomation/backend/app/collectors/jobspy_collector.py) to count `("new_role", "sibling_role", "created_new", "created_sibling")`.
5. **`company_slug` Mismatch (`cred-test` vs. `cred`):** `gate3_extractor.py` recomputed `company_slug` solely from `slugify_company(company_name)`, losing explicit `Company.slug` identity during ATS ingestion and breaking pruner correlation. **Fix:** Updated [manager.py](file:///f:/Projects/JobAutomation/backend/app/collectors/manager.py) to attach `company.slug` into `raw_job.portal_metadata["company_slug"]` and updated `extract_job_signals()` in [gate3_extractor.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate3_extractor.py) to prefer `meta["company_slug"]` before falling back to `slugify_company(company_name)`.

### Summary of Files Added, Modified, and Removed (Cycle 3)
- **Added (19 files):**
  - Data Seed: [watchlist_seed.json](file:///f:/Projects/JobAutomation/backend/app/data/watchlist_seed.json)
  - Collectors Package: [__init__.py](file:///f:/Projects/JobAutomation/backend/app/collectors/__init__.py), [base.py](file:///f:/Projects/JobAutomation/backend/app/collectors/base.py), [location_filter.py](file:///f:/Projects/JobAutomation/backend/app/collectors/location_filter.py), [ats_greenhouse.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_greenhouse.py), [ats_lever.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_lever.py), [ats_ashby.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_ashby.py), [ats_smartrecruiters.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_smartrecruiters.py), [ats_workday.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_workday.py), [pruner.py](file:///f:/Projects/JobAutomation/backend/app/collectors/pruner.py), [jobspy_collector.py](file:///f:/Projects/JobAutomation/backend/app/collectors/jobspy_collector.py), [manager.py](file:///f:/Projects/JobAutomation/backend/app/collectors/manager.py), [scheduler.py](file:///f:/Projects/JobAutomation/backend/app/collectors/scheduler.py)
  - Schemas & Routers: [schemas/watchlist.py](file:///f:/Projects/JobAutomation/backend/app/schemas/watchlist.py), [schemas/collectors.py](file:///f:/Projects/JobAutomation/backend/app/schemas/collectors.py), [api/watchlist.py](file:///f:/Projects/JobAutomation/backend/app/api/watchlist.py), [api/collectors.py](file:///f:/Projects/JobAutomation/backend/app/api/collectors.py)
  - Tests & Docs: [test_collectors.py](file:///f:/Projects/JobAutomation/backend/tests/test_collectors.py), [04_Job_Collectors_ATS_Feeds_and_Circuit_Breakers.md](file:///f:/Projects/JobAutomation/Documentation/Technical%20Reference/04_Job_Collectors_ATS_Feeds_and_Circuit_Breakers.md)
- **Modified (7 files):**
  - [main.py](file:///f:/Projects/JobAutomation/backend/app/main.py) (mounted `watchlist_router` and `collectors_router`, seeded watchlist on boot, attached `CollectorScheduler`)
  - [gate3_extractor.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate3_extractor.py) (preserved explicit `portal_metadata["company_slug"]`)
  - [README.md](file:///f:/Projects/JobAutomation/README.md) (updated Cycle 3 status, REST endpoints, and 26-test count)
  - [Technical Reference/README.md](file:///f:/Projects/JobAutomation/Documentation/Technical%20Reference/README.md) (linked `04_Job_Collectors_ATS_Feeds_and_Circuit_Breakers.md`)
  - [Implementation Progress/README.md](file:///f:/Projects/JobAutomation/Documentation/Implementation%20Progress/README.md) (updated Cycle 3 progress status)
  - [Implementation Progress/Cycle_Wise_Log.md](file:///f:/Projects/JobAutomation/Documentation/Implementation%20Progress/Cycle_Wise_Log.md) (logged Cycle 3, bug fixes, and changelog)
  - [Implementation Progress/File_Wise_Inventory.md](file:///f:/Projects/JobAutomation/Documentation/Implementation%20Progress/File_Wise_Inventory.md) (added Cycle 3 collector/schema/API/test entries)
- **Removed:** None (`0` files deleted).


