# 03. Configuration, Debugging & Extension Guide

---

## 1. Zero-Code Modification Guide (JSON & `.env`)

### A. Adding Skills, Cities, or Domain Heuristics Without Touching Python
Edit any JSON file in `backend/app/data/` and restart Uvicorn (or trigger `/api/v1/jobs/rescore` / `/resumes/{id}/reparse` if updating skills):

| File | What You Can Customize | Example Edit |
| :--- | :--- | :--- |
| [skills_taxonomy.json](file:///f:/Projects/JobAutomation/backend/app/data/skills_taxonomy.json) | Add new technologies, aliases, or core languages | Add `"Bun": ["bun", "bun.sh"]` or `"Zig": ["zig"]` under `skill_synonym_groups` |
| [india_locations.json](file:///f:/Projects/JobAutomation/backend/app/data/india_locations.json) | Add regional city spellings, tech parks, or metro groups | Add `"Gift City Gandhinagar"` under `Ahmedabad` or new localities to `office_localities` |
| [pipeline_rules.json](file:///f:/Projects/JobAutomation/backend/app/data/pipeline_rules.json) | Add IT service firms, sub-domain regex cues, or ATS domains | Add `"zoho"` or new sub-domain `"FinOps"` to `domain_cues` & `domain_skill_map` |

### B. Complete `.env` Tunable Threshold Reference ([config.py](file:///f:/Projects/JobAutomation/backend/app/config.py))

| Variable | Default | Controls |
| :--- | :---: | :--- |
| `SEMANTIC_THRESHOLD` | `0.72` | Minimum cosine similarity (`BAAI/bge-small-en-v1.5`) for an Option 3 bullet `MATCHED` + Cross-Resume Alert |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.88` | Minimum whole-JD cosine similarity for Gate 2 cross-portal merge vs. Sibling Role split |
| `DEDUP_STACK_OVERLAP_THRESHOLD` | `0.70` | Minimum primary-skill Jaccard overlap required alongside vector similarity to merge |
| `GATE1_EXP_BUFFER_YEARS` | `2.0` | Hides jobs when `jd_min_exp > total_exp_years + buffer` |
| `EXP_FIT_LOWER_GRACE_YEARS` | `0.5` | Lower grace below JD minimum experience still treated as `"exact"` fit |
| `EXP_FIT_UPPER_GRACE_YEARS` | `2.0` | Upper grace above JD max experience still treated as `"exact"` fit |
| `EXP_FIT_STRETCH_YEARS` | `2.0` | Stretch range below JD min (`low - stretch` .. `low - lower_grace`) before dropping to `"under"` |
| `TIER_S_COVERAGE_PCT` / `TIER_A_...` / `TIER_B_...` | `80.0` / `60.0` / `40.0` | Minimum Option 3 semantic bullet coverage % for Tiers `S`, `A`, and `B` |
| `TIER_A_PRIMARY_RATIO` / `TIER_B_...` / `TIER_C_MIN_...` | `0.75` / `0.50` / `0.40` | Primary skill match ratio thresholds for `A`, `B`, and hard `C` floor |
| `TIER_A_MAX_MISSING_SECONDARY` | `2` | Maximum missing bonus/secondary skills permitted in `Tier A` |
| `TIER_B_MAX_MISSING_PRIMARY` | `1` | Alternate absolute missing-primary allowance for `Tier B` |
| `FRESHNESS_HOURS` | `6` | Window used by `GET /api/v1/jobs?fresh_6h=true` |
| `JD_EMBED_MAX_CHARS` | `2000` | Character slice of boilerplate-stripped JD passed into whole-JD embedding |
| `ALLOWED_CORS_ORIGINS` | `127.0.0.1:8000, localhost:5173, 127.0.0.1:5173` | Comma-separated origins allowed alongside `chrome-extension://[a-p]{32}` |

---

## 2. Debugging Playbook

| Symptom | Where to Check & Root Cause | Fix / Diagnostic Command |
| :--- | :--- | :--- |
| **`HTTP 401 Invalid or missing X-Local-Token`** | Request lacked matching header from `data/.local_token`. | Read token from `data\.local_token` and pass `-H "X-Local-Token: <token>"`. |
| **`HTTP 422` when saving Q&A rule** | [pii_guard.py](file:///f:/Projects/JobAutomation/backend/app/vault/pii_guard.py) detected PAN, Aadhaar, Passport, DoB, Bank/IFSC, or UAN/PF. | Intentional guardrail—do not store gov IDs; rephrase if false-positive word match occurred. |
| **Job scored lower Tier than expected** | Inspect `GET /api/v1/jobs/{id}` -> `all_scores[].bullet_proof_json`, `missing_primary_skills_json`, and `semantic_bullet_coverage_pct`. | If real bullets match conceptually at `0.66–0.71`, lower `SEMANTIC_THRESHOLD` slightly (e.g., `0.68`) in `.env` and call `POST /api/v1/jobs/rescore`. |
| **Job missing from `GET /api/v1/jobs`** | Filtered by Gate 1 (`hidden_by_gate1=true`). | Query `GET /api/v1/jobs?only_hidden=true` to read exact `hidden_reason`; unhide via `PATCH /api/v1/jobs/{id}/status`. |
| **FTS5 syntax error on `fts_query`** | Unmatched quotes or raw punctuation (`C++`) in SQLite FTS5 `MATCH`. | Quote literal tech phrases containing special chars (`"C++"` or `"night shift"`). |
| **Slow test or ONNX download failure** | `.fastembed_cache/` unpopulated or Windows `asyncio` deadlock inside restricted sandbox. | Always run full `pytest` directly in visible PowerShell (`.\.venv\Scripts\pytest.exe backend\tests -v`). |
| **`TestClient` warning in pytest output** | Upstream Starlette 1.10 prints `install httpx2` warning once per run. | Harmless test-harness notice; zero warnings come from `backend/app/`. |

---

## 3. Extension Seams for Upcoming Cycles (Cycles 3–7)

1. **Cycle 3 (Collectors -> 5-Gate Pipeline):**
   - Every ATS/JobSpy collector converts raw responses into `RawJobInput` and calls `orchestrator.ingest_job(session, raw, embedder, settings)` directly—automatically gaining Gate 1–4 filtering, deduplication, and scoring.
   - `pruner.py` queries `JobSource` for active ATS jobs missing from the latest company feed and flips `Job.status = "closed"`.
2. **Cycle 4 (Applications, Snapshots & Extension Bridge):**
   - `/api/v1/extension/check-page` reuses `gate3_extractor.extract_job_signals` + `gate2_identity.resolve_job_identity` (in read-only preview mode) + `Application` lookup to determine the 4-State Banner (`NEW ROLE`, `NEW SIBLING ROLE`, `STARTED BUT NOT SUBMITTED`, `ALREADY APPLIED`) without inserting duplicate jobs.
   - `templates.render_cover_template` feeds `/extension/check-page` with deterministic cover snippets using the job's winning `matched_primary_skills_json[:3]`.
3. **Cycle 5–7 (React UI & Chromium Extension):**
   - Static frontend dist mounts at `/` in `main.py` (no CORS issues).
   - Chromium extension reads `X-Local-Token` once into `chrome.storage.local`, pulls winning PDF bytes from `GET /api/v1/resumes/{id}/file`, and pushes DOM-harvested cards into `POST /api/v1/jobs/ingest` (or `/extension/harvest`).

