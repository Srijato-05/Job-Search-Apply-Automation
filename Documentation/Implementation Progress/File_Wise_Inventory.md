# File-Wise Implementation Inventory

Complete inventory of every implemented file across the repository as of **Cycle 7** (All Cycles Complete).

---

## 1. Root Configuration & Documentation

| File | Responsibility | Key Contents / Exports |
| :--- | :--- | :--- |
| [README.md](file:///f:/Projects/JobAutomation/README.md) | Repository overview & layout | Core principles, folder structure, doc links, project status |
| [.gitignore](file:///f:/Projects/JobAutomation/.gitignore) | Git exclusion rules | Excludes `data/*` (except `.gitkeep`), `*.db*`, `.local_token`, `.env`, `.venv/`, `.fastembed_cache/`, `node_modules/` |
| [.gitattributes](file:///f:/Projects/JobAutomation/.gitattributes) | Line-ending & binary normalization | `LF` default, `CRLF` for `.ps1/.bat/.cmd`, binary for `.pdf/.png/.ico` |
| [.editorconfig](file:///f:/Projects/JobAutomation/.editorconfig) | Editor formatting consistency | UTF-8, 4-space Python/PowerShell, 2-space JS/TS/JSON |
| [.env.example](file:///f:/Projects/JobAutomation/.env.example) | Tunable environment template | Server host/port, collector delays, cooldowns, and 17 pipeline thresholds |
| [Documentation/Innitial Research/](file:///f:/Projects/JobAutomation/Documentation/Innitial%20Research/README.md) | Stage 1 research archive | 5 markdown files (platforms, scoring, dedup/tracking, zero-hallucination autofill) |
| [Documentation/Planning/](file:///f:/Projects/JobAutomation/Documentation/Planning/README.md) | Stage 2 architecture archive | 5 markdown files (DB ER schema, REST contract, safety, UI/extension, 7 cycles) |

---

## 2. Backend Config, Server & Data Files (`backend/`)

| File | Responsibility | Key Symbols / Endpoints | Tests |
| :--- | :--- | :--- | :--- |
| [requirements.txt](file:///f:/Projects/JobAutomation/backend/requirements.txt) | Python 3.12 dependency pins | FastAPI, SQLModel, FastEmbed, ONNX Runtime, pdfplumber, pypdf, pytest, reportlab | Environment |
| [pytest.ini](file:///f:/Projects/JobAutomation/backend/pytest.ini) | Pytest root & path config | `pythonpath = .`, `testpaths = tests` | All tests |
| [config.py](file:///f:/Projects/JobAutomation/backend/app/config.py) | Typed settings & token utility | `Settings`, `cors_origins_list`, `ensure_data_dirs`, `get_or_create_local_token` | `test_config_and_data.py` |
| [main.py](file:///f:/Projects/JobAutomation/backend/app/main.py) | FastAPI factory & security | `create_app`, `verify_local_token` middleware, `CORSMiddleware`, `/health`, router mounts | `test_security_and_db.py` |
| [india_locations.json](file:///f:/Projects/JobAutomation/backend/app/data/india_locations.json) | Editable Indian geography | `city_aliases` (22+Remote), `office_localities` (35 hubs), `ncr_group` | `test_config_and_data.py` |
| [skills_taxonomy.json](file:///f:/Projects/JobAutomation/backend/app/data/skills_taxonomy.json) | Editable tech skill taxonomy | `core_languages` (15), `ambiguous_lowercase_aliases`, `skill_synonym_groups` (500+ aliases) | `test_config_and_data.py` |
| [pipeline_rules.json](file:///f:/Projects/JobAutomation/backend/app/data/pipeline_rules.json) | Editable extractor heuristics | `it_service_companies`, `domain_cues`, `domain_skill_map`, `enterprise_ats_domains`, `fast_apply_domains` | `test_config_and_data.py` |
| [watchlist_seed.json](file:///f:/Projects/JobAutomation/backend/app/data/watchlist_seed.json) | 68 Pre-seeded India Tech companies | ATS provider config for Greenhouse, Lever, Ashby, SmartRecruiters, Workday | `test_collectors.py` |

---

## 3. Database Layer (`backend/app/db/`)

| File | Responsibility | Key Symbols | Tests |
| :--- | :--- | :--- | :--- |
| [models.py](file:///f:/Projects/JobAutomation/backend/app/db/models.py) | All 10 SQLModel tables | `FactVault`, `LearnedQARule`, `Resume`, `ResumeBullet`, `Company`, `Job`, `JobSource`, `JobResumeScore`, `Application`, `CollectorRun` | `test_security_and_db.py` |
| [database.py](file:///f:/Projects/JobAutomation/backend/app/db/database.py) | SQLite WAL + FTS5 setup | `create_db_engine`, `init_db` (triggers `jobs_fts_ai/ad/au`), `search_jobs_fts` | `test_security_and_db.py` |

---

## 4. Vault, PII Guardrails & Resume Engine (`backend/app/vault/`, `backend/app/resumes/`)

| File | Responsibility | Key Symbols | Tests |
| :--- | :--- | :--- | :--- |
| [pii_guard.py](file:///f:/Projects/JobAutomation/backend/app/vault/pii_guard.py) | Sensitive ID hard blocker | `is_blocked_pii_question`, `contains_sensitive_pii_value` | `test_vault_and_taxonomy.py` |
| [taxonomy.py](file:///f:/Projects/JobAutomation/backend/app/vault/taxonomy.py) | Skill & city normalizer | `normalize_city`, `extract_office_locality`, `is_india_location`, `cities_compatible`, `normalize_skill`, `extract_skills_from_text`, `CORE_LANGUAGES` | `test_vault_and_taxonomy.py` |
| [templates.py](file:///f:/Projects/JobAutomation/backend/app/vault/templates.py) | Cover-note template engine | `ALLOWED_TEMPLATE_VARIABLES`, `render_cover_template` | `test_vault_and_taxonomy.py` |
| [parser.py](file:///f:/Projects/JobAutomation/backend/app/resumes/parser.py) | PDF resume bullet parser | `ParsedResume`, `ExtractedBullet`, `parse_resume_pdf` | `test_resumes_and_embeddings.py` |
| [embedder.py](file:///f:/Projects/JobAutomation/backend/app/resumes/embedder.py) | Local ONNX vector embedder | `EmbedderProtocol`, `FastEmbedService`, `l2_normalize_matrix`, `vector_to_blob`, `blob_to_vector`, `cosine_similarity` | `test_resumes_and_embeddings.py` |

---

## 5. 5-Gate Pipeline (`backend/app/pipeline/`)

| File | Responsibility | Key Symbols | Tests |
| :--- | :--- | :--- | :--- |
| [gate3_extractor.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate3_extractor.py) | Boilerplate stripper & 10 fields | `strip_boilerplate`, `extract_requirement_lines`, `normalize_job_title`, `slugify_company`, `extract_job_signals`, `ExtractedJobSignals` | `test_pipeline_and_jobs.py` |
| [gate1_filters.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate1_filters.py) | Dealbreakers & Hidden Audit | `Gate1Result`, `effective_candidate_notice_days`, `evaluate_gate1` | `test_pipeline_and_jobs.py` |
| [gate2_identity.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate2_identity.py) | 4-Layer Role ID & JD Diff | `IdentityResolution`, `compute_description_hash`, `compute_simhash64`, `resolve_job_identity`, `compute_jd_diff` | `test_pipeline_and_jobs.py` |
| [gate4_scorer.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/gate4_scorer.py) | Combined Option 1 + 3 Scorer | `detect_role_archetype`, `_compute_tier`, `score_job_against_resumes` | `test_pipeline_and_jobs.py` |
| [orchestrator.py](file:///f:/Projects/JobAutomation/backend/app/pipeline/orchestrator.py) | Atomic pipeline coordinator | `RawJobInput`, `IngestionResult`, `ingest_job`, `rescore_active_jobs` | `test_pipeline_and_jobs.py` |

---

## 6. Job Collectors & Scheduler (`backend/app/collectors/`)

| File | Responsibility | Key Symbols | Tests |
| :--- | :--- | :--- | :--- |
| [location_filter.py](file:///f:/Projects/JobAutomation/backend/app/collectors/location_filter.py) | Indian location normalizer & foreign filter | `is_india_location`, `_FOREIGN_COUNTRY_RE` | `test_collectors.py` |
| [base.py](file:///f:/Projects/JobAutomation/backend/app/collectors/base.py) | Collector base & circuit breaker | `BaseCollector`, `CollectorResult`, `trip_circuit_breaker`, `get_active_cooldown` | `test_collectors.py` |
| [ats_greenhouse.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_greenhouse.py) | Greenhouse API connector | `fetch_greenhouse_jobs` | `test_collectors.py` |
| [ats_lever.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_lever.py) | Lever API connector | `fetch_lever_jobs` | `test_collectors.py` |
| [ats_ashby.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_ashby.py) | Ashby API connector | `fetch_ashby_jobs` | `test_collectors.py` |
| [ats_smartrecruiters.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_smartrecruiters.py) | SmartRecruiters API connector | `fetch_smartrecruiters_jobs` | `test_collectors.py` |
| [ats_workday.py](file:///f:/Projects/JobAutomation/backend/app/collectors/ats_workday.py) | Workday CXS connector (limit <= 20) | `fetch_workday_jobs`, `_build_workday_cxs_base_url` | `test_collectors.py` |
| [pruner.py](file:///f:/Projects/JobAutomation/backend/app/collectors/pruner.py) | Vanished job pruner | `prune_closed_ats_jobs` | `test_collectors.py` |
| [jobspy_collector.py](file:///f:/Projects/JobAutomation/backend/app/collectors/jobspy_collector.py) | Aggregator scraper (JobSpy) | `JobSpyCollector`, polite jitter, query rotation | `test_collectors.py` |
| [manager.py](file:///f:/Projects/JobAutomation/backend/app/collectors/manager.py) | Coordinator & health aggregator | `CollectorManager`, `seed_watchlist` | `test_collectors.py` |
| [scheduler.py](file:///f:/Projects/JobAutomation/backend/app/collectors/scheduler.py) | Periodic async background loop | `CollectorScheduler` | Lifecycle |

---

## 7. Pydantic Schemas & REST Routers (`backend/app/schemas/`, `backend/app/api/`)

| File | Responsibility | Key Endpoints / DTOs | Tests |
| :--- | :--- | :--- | :--- |
| [schemas/vault.py](file:///f:/Projects/JobAutomation/backend/app/schemas/vault.py) | Fact Vault & Q&A contracts | `FactVaultPayload`, `FactVaultResponse`, `QARuleCreate`, `QARuleResponse`, `TaxonomyNormalizeRequest/Response` | `test_vault_and_taxonomy.py` |
| [schemas/resumes.py](file:///f:/Projects/JobAutomation/backend/app/schemas/resumes.py) | Resume registry contracts | `ResumeSummaryResponse`, `ResumeDetailResponse`, `ResumeBulletResponse`, `ResumeUpdatePayload` | `test_resumes_and_embeddings.py` |
| [schemas/jobs.py](file:///f:/Projects/JobAutomation/backend/app/schemas/jobs.py) | Jobs, Scores & Diff contracts | `JobIngestItem`, `JobIngestBatchRequest`, `JobCardResponse`, `JobDetailResponse`, `JobDiffResponse`, `JobStatusUpdate` | `test_pipeline_and_jobs.py` |
| [schemas/watchlist.py](file:///f:/Projects/JobAutomation/backend/app/schemas/watchlist.py) | Company & Watchlist contracts | `CompanyCreate`, `CompanyUpdate`, `CompanyResponse`, `WatchlistSeedResponse`, `WatchlistVerifyResponse` | `test_collectors.py` |
| [schemas/collectors.py](file:///f:/Projects/JobAutomation/backend/app/schemas/collectors.py) | Telemetry & Health contracts | `CollectorRunRequest`, `CollectorRunResponse`, `CollectorProgressResponse`, `SourceHealthItem`, `CollectorHealthResponse` | `test_collectors.py` |
| [schemas/applications.py](file:///f:/Projects/JobAutomation/backend/app/schemas/applications.py) | Application CRM & Backup DTOs | `ApplicationStartDraftRequest`, `ApplicationSubmitRequest`, `ApplicationUpdateRequest`, `CooldownStatusResponse`, `ApplicationResponse`, `BackupRestoreResponse` | `test_applications_and_backup.py` |
| [schemas/extension.py](file:///f:/Projects/JobAutomation/backend/app/schemas/extension.py) | Extension 4-State Banner DTOs | `BannerState`, `CheckPageRequest`, `CheckPageResponse` | `test_applications_and_backup.py` |
| [applications/service.py](file:///f:/Projects/JobAutomation/backend/app/applications/service.py) | CRM, Cooldown & 4-State logic | `start_or_resume_draft`, `mark_application_submitted`, `update_application`, `get_company_cooldown_status`, `check_extension_page` | `test_applications_and_backup.py` |
| [applications/backup.py](file:///f:/Projects/JobAutomation/backend/app/applications/backup.py) | ZIP Export & Restore engine | `export_backup_zip`, `restore_backup_zip` | `test_applications_and_backup.py` |
| [api/deps.py](file:///f:/Projects/JobAutomation/backend/app/api/deps.py) | FastAPI dependency injectors | `get_settings`, `get_engine`, `get_embedder`, `get_session` | All API tests |
| [api/vault.py](file:///f:/Projects/JobAutomation/backend/app/api/vault.py) | Vault, Q&A & Taxonomy API | `GET/PUT /vault`, `GET/POST/DELETE /vault/qa-rules`, `POST /vault/taxonomy/normalize`, `POST /vault/templates/render` | `test_vault_and_taxonomy.py` |
| [api/resumes.py](file:///f:/Projects/JobAutomation/backend/app/api/resumes.py) | Multi-Resume PDF API | `GET/POST /resumes`, `GET/PATCH/DELETE /resumes/{id}`, `GET /resumes/{id}/file`, `POST /resumes/{id}/reparse` | `test_resumes_and_embeddings.py` |
| [api/jobs.py](file:///f:/Projects/JobAutomation/backend/app/api/jobs.py) | Jobs Queue, Filter & Diff API | `POST /jobs/ingest`, `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/diff/{sibling_id}`, `PATCH /jobs/{id}/status`, `POST /jobs/rescore` | `test_pipeline_and_jobs.py` |
| [api/watchlist.py](file:///f:/Projects/JobAutomation/backend/app/api/watchlist.py) | Watchlist Management API | `GET/POST /watchlist`, `PATCH/DELETE /watchlist/{slug}`, `POST /watchlist/seed`, `POST /watchlist/verify` | `test_collectors.py` |
| [api/collectors.py](file:///f:/Projects/JobAutomation/backend/app/api/collectors.py) | Collector Trigger & Health API | `POST /collectors/run`, `GET /collectors/progress`, `GET /collectors/health`, `GET /collectors/runs` | `test_collectors.py` |
| [api/applications.py](file:///f:/Projects/JobAutomation/backend/app/api/applications.py) | Application Mini-CRM API | `GET /applications`, `POST /applications/draft`, `POST /applications/{id}/submit`, `PATCH/GET /applications/{id}`, `GET /applications/cooldown/{slug}` | `test_applications_and_backup.py` |
| [api/extension.py](file:///f:/Projects/JobAutomation/backend/app/api/extension.py) | Extension 4-State Bridge API | `POST /extension/check-page` | `test_applications_and_backup.py` |
| [api/backup.py](file:///f:/Projects/JobAutomation/backend/app/api/backup.py) | 1-Click ZIP Backup API | `GET /backup/export`, `POST /backup/restore` | `test_applications_and_backup.py` |

---

## 8. Automated Test Suite (`backend/tests/` — 38 Tests Across 7 Files)

| File | Tests Count | Scope Covered |
| :--- | :--- | :--- |
| [conftest.py](file:///f:/Projects/JobAutomation/backend/tests/conftest.py) | Fixture module | `DeterministicTestEmbedder`, `real_fastembed_service`, ReportLab PDF generators, isolated `tmp_path` app client |
| [test_security_and_db.py](file:///f:/Projects/JobAutomation/backend/tests/test_security_and_db.py) | 3 | WAL + FKs + 10 tables, FTS5 insert/update/delete & boolean query, `X-Local-Token` auth + CORS |
| [test_vault_and_taxonomy.py](file:///f:/Projects/JobAutomation/backend/tests/test_vault_and_taxonomy.py) | 4 | Vault CRUD & bounds, PII Guardrails, 500+ skill taxonomy & cities, deterministic cover templates |
| [test_resumes_and_embeddings.py](file:///f:/Projects/JobAutomation/backend/tests/test_resumes_and_embeddings.py) | 2 | Full Resume PDF upload/download/patch/reparse/cascade-delete + real `BAAI/bge-small-en-v1.5` semantic ranking |
| [test_pipeline_and_jobs.py](file:///f:/Projects/JobAutomation/backend/tests/test_pipeline_and_jobs.py) | 4 | Boilerplate strip + 10-field extraction, Gate 1 audit/unhide, Gate 2 sibling roles + diff, Gate 4 Option 1+3 routing + alerts + Gate 5 filters |
| [test_config_and_data.py](file:///f:/Projects/JobAutomation/backend/tests/test_config_and_data.py) | 3 | JSON file loading, `Settings` threshold override checks on Gate 1, Gate 4, and `orchestrator.ingest_job` |
| [test_collectors.py](file:///f:/Projects/JobAutomation/backend/tests/test_collectors.py) | 19 | Location filtering, Watchlist seeding/CRUD/verify, 5 ATS connectors + Workday India fallback & incremental detail skip, 429 circuit breaker, 404 `invalid_config`, `503` retries, `409` overlap lock, closed-job pruner, stale-run recovery, resumable checkpoints, composite indexes, online snapshot, and HTTP API routes |
| [test_applications_and_backup.py](file:///f:/Projects/JobAutomation/backend/tests/test_applications_and_backup.py) | 3 | `Discovered -> Draft -> Submitted -> Immutability -> Repost Red Banner -> Sibling Diff`, 30-day cooldown cap, and validated ZIP export/restore round-trip |

---

## 9. Local Web Dashboard (`frontend/` — Cycle 5)

| File | Responsibility | Key Exports / Components | Tests |
| :--- | :--- | :--- | :--- |
| [package.json](file:///f:/Projects/JobAutomation/frontend/package.json) | React 19 + Vite + Tailwind + Vitest config | `dev`, `build`, `test` scripts | `npm run build` |
| [vite.config.ts](file:///f:/Projects/JobAutomation/frontend/vite.config.ts) | Vite `/api` proxy & Vitest `jsdom` config | `defineConfig` | `Dashboard.test.tsx` |
| [api/types.ts](file:///f:/Projects/JobAutomation/frontend/src/api/types.ts) | Typed REST contracts | `JobCard`, `JobDetail`, `JobDiffResponse`, `ApplicationRecord`, `FactVaultData`, `CollectorHealthResponse` | `Dashboard.test.tsx` |
| [api/client.ts](file:///f:/Projects/JobAutomation/frontend/src/api/client.ts) | Loopback `X-Local-Token` fetch client | `api`, `apiFetch`, `getLocalToken`, `setLocalToken`, `ApiError` | `Dashboard.test.tsx` |
| [App.tsx](file:///f:/Projects/JobAutomation/frontend/src/App.tsx) | Sidebar shell & dev token prompt | `App` | `Dashboard.test.tsx` |
| [JobDetailDrawer.tsx](file:///f:/Projects/JobAutomation/frontend/src/components/JobDetailDrawer.tsx) | Proof table, Cross-Alerts, JD Diff & Apply bar | `JobDetailDrawer` | `Dashboard.test.tsx` |
| [JobQueuePage.tsx](file:///f:/Projects/JobAutomation/frontend/src/pages/JobQueuePage.tsx) | Faceted queue, FTS5 search & Hidden Audit tab | `JobQueuePage` | `Dashboard.test.tsx` |
| [ApplicationsPage.tsx](file:///f:/Projects/JobAutomation/frontend/src/pages/ApplicationsPage.tsx) | CRM stages, notes & Offline Snapshot modal | `ApplicationsPage` | `Dashboard.test.tsx` |
| [FactVaultPage.tsx](file:///f:/Projects/JobAutomation/frontend/src/pages/FactVaultPage.tsx) | Vault form, PII-guarded Q&A & ZIP Backup/Restore | `FactVaultPage` | `Dashboard.test.tsx` |
| [ResumesPage.tsx](file:///f:/Projects/JobAutomation/frontend/src/pages/ResumesPage.tsx) | Multi-resume PDF upload & bullet inspector | `ResumesPage` | `npm run build` |
| [CollectorsPage.tsx](file:///f:/Projects/JobAutomation/frontend/src/pages/CollectorsPage.tsx) | Source health, progress bar & Watchlist CRUD | `CollectorsPage` | `npm run build` |
| [Dashboard.test.tsx](file:///f:/Projects/JobAutomation/frontend/src/__tests__/Dashboard.test.tsx) | 3 Vitest component/integration specs | Tier/FTS5/Audit, Proof+Diff Drawer, CRM Snapshot + Vault | `npm test -- --run` |

---

## 10. Chromium MV3 Extension Core (`extension/` — Cycle 6)

| File | Responsibility | Key Exports / Features | Tests |
| :--- | :--- | :--- | :--- |
| [manifest.json](file:///f:/Projects/JobAutomation/extension/public/manifest.json) | Manifest V3 permissions & portal matches | `sidePanel`, `activeTab`, `storage`, `127.0.0.1:8000` | Chrome unpacked load |
| [ats_detector.ts](file:///f:/Projects/JobAutomation/extension/src/shared/ats_detector.ts) | Career page ATS token parser | `detectAtsFromUrl` (Greenhouse, Lever, Ashby, SmartRecruiters, Workday) | `extension.test.ts` |
| [harvester.ts](file:///f:/Projects/JobAutomation/extension/src/content/harvester.ts) | On-demand portal DOM card extractor | `harvestVisibleJobs`, `extractCurrentPageContext`, `detectPortalFromUrl` | `extension.test.ts` |
| [submit_watcher.ts](file:///f:/Projects/JobAutomation/extension/src/content/submit_watcher.ts) | Applied, Confirmation & Expired detector | `detectNativeAppliedBadge`, `detectConfirmationScreen`, `detectExpiredPosting`, `attachSubmitWatcher` | `extension.test.ts` |
| [content/index.ts](file:///f:/Projects/JobAutomation/extension/src/content/index.ts) | Tab message listener & observer hook | `GET_PAGE_CONTEXT`, `HARVEST_VISIBLE_JOBS`, `PAGE_LIFECYCLE_EVENT` | `npm run build` |
| [background/index.ts](file:///f:/Projects/JobAutomation/extension/src/background/index.ts) | MV3 Service Worker bridge | `API_REQUEST`, `FETCH_RESUME_PDF`, `handleLifecycleEvent` | `npm run build` |
| [sidepanel.html](file:///f:/Projects/JobAutomation/extension/sidepanel.html) & [sidepanel/main.ts](file:///f:/Projects/JobAutomation/extension/src/sidepanel/main.ts) | Side Panel 4-State Banner UI | 4-State Banner, `+ Watch Company ATS`, `Capture Visible Jobs`, Token settings | `npm run build` |
| [extension.test.ts](file:///f:/Projects/JobAutomation/extension/src/__tests__/extension.test.ts) | 3 Vitest + `jsdom` DOM snapshot suites | ATS detection, 6 portals harvesting, Applied/Expired guards | `npm test -- --run` |

---

## 11. Autofill Engine, 13 Portal Adapters & Launcher (Cycle 7)

| File | Responsibility | Key Exports / Features | Tests |
| :--- | :--- | :--- | :--- |
| [pii_guard.ts](file:///f:/Projects/JobAutomation/extension/src/content/pii_guard.ts) | Client-side sensitive ID blocklist | `isBlockedPiiField` (PAN, Aadhaar, Passport, DoB, Bank, UAN) | `autofill.test.ts` |
| [dom_engine.ts](file:///f:/Projects/JobAutomation/extension/src/content/dom_engine.ts) | React/Angular DOM setters & PDF inject | `setNativeInputValue`, `selectNativeOrAriaOption`, `attachResumePdf`, `highlightAmberField` | `autofill.test.ts` |
| [adapters/types.ts](file:///f:/Projects/JobAutomation/extension/src/content/adapters/types.ts) & [adapters/index.ts](file:///f:/Projects/JobAutomation/extension/src/content/adapters/index.ts) | Adapter interfaces & 13-portal registry | `getAdapterForPortal`, `ALL_ADAPTER_NAMES` | `autofill.test.ts` |
| `extension/src/content/adapters/*.ts` (13 files) | Isolated per-portal autofill modules | `greenhouse`, `lever`, `ashby`, `smartrecruiters`, `workday`, `naukri` (Chatbot), `linkedin`, `indeed`, `instahyre`, `foundit`, `hirist`, `cutshort`, `generic_heuristic` | `autofill.test.ts` |
| [autofill.test.ts](file:///f:/Projects/JobAutomation/extension/src/__tests__/autofill.test.ts) | 5 Vitest + `jsdom` autofill specs | 13 adapters, Greenhouse PDF/PII/Pause, Workday+LinkedIn, Naukri Chatbot, anti-autosubmit shield | `npm test -- --run` |
| [start.ps1](file:///f:/Projects/JobAutomation/start.ps1) | 1-click Windows startup script | Launches Uvicorn (`127.0.0.1:8000`) and opens local dashboard | Manual launch |

