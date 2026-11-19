# Stage 2: Planning — Architecture, Contracts & Implementation Roadmap

> **Project Phase:** Stage 2 — Detailed Planning (Complete — awaiting explicit confirmation for Stage 3)  
> **Target Environment:** Windows (`Python 3.12.10`, `Node.js v24.15.0`, `npm 11.12.1`, `Git 2.44.0`)  
> **Stage 1 Research Reference:** [Documentation/Innitial Research/README.md](file:///f:/Projects/JobAutomation/Documentation/Innitial%20Research/README.md)

---

## 1. Finalized \$0 Tech Stack & Architectural Decisions

| Component | Technology Choice | Engineering Rationale |
| :--- | :--- | :--- |
| **Backend & Scheduler** | **Python 3.12 + FastAPI + Uvicorn + APScheduler** | Async REST backend serving both the React UI and Chromium Extension on `127.0.0.1:8000` with scheduled background ATS/aggregator syncs. |
| **Database & Search** | **SQLite (WAL Mode) + SQLModel/SQLAlchemy + FTS5** | Zero-config single-file local database (`data/jobs.db`), safe concurrent access via Write-Ahead Logging, and sub-10ms offline boolean search via FTS5. |
| **Local Semantic Engine (Option 3)** | **`fastembed` (`BAAI/bge-small-en-v1.5` via ONNX Runtime)** | Runs the 384-dim CPU embedding model (~90 MB) via ONNX Runtime without installing ~2.5 GB of PyTorch. 100% offline, non-generative, \$0 cost. |
| **Job Collectors** | **`python-jobspy` + async `httpx` ATS connectors** | Tier 1 aggregators (`Naukri`, `LinkedIn`, `Indeed India`, `Glassdoor`, `Google Jobs`) + Tier 3 direct ATS JSON APIs (`Greenhouse`, `Lever`, `Ashby`, `SmartRecruiters`, `Workday CXS`). |
| **PDF Resume Parser** | **`pdfplumber` + `pypdf`** | Layout-aware deterministic extraction of resume sections and exact bullet lines (zero LLM text rewriting). |
| **Web Dashboard** | **React 19 + TypeScript + Vite + Tailwind CSS + TanStack Query** | Fast local command center; builds to static files served directly by FastAPI for single-process daily execution. |
| **Chromium Extension** | **Manifest V3 (`chrome.sidePanel`) + TypeScript + Vite** | Loaded unpacked (`$0` fee) in Chrome/Brave/Edge; hosts isolated portal adapters, React-safe autofill, PDF injection, and DOM harvesting. |
| **Localhost Security** | **`127.0.0.1` Bind + `X-Local-Token` Auth + Locked CORS** | Blocks arbitrary websites open in your browser from querying `localhost:8000` to access your Fact Vault or download your resumes. |

---

## 2. Monorepo Directory Blueprint

```text
f:\Projects\JobAutomation\
├── Documentation\
│   ├── Innitial Research\              # Stage 1 Research (Complete)
│   └── Planning\                       # Stage 2 Planning (This Folder)
├── data\                               # Local runtime storage (gitignored)
│   ├── jobs.db                         # SQLite DB (WAL + FTS5)
│   ├── resumes\                        # Immutable uploaded Resume PDFs
│   └── backups\                        # 1-Click portable ZIP/JSON backups
├── backend\
│   ├── app\
│   │   ├── main.py                     # FastAPI entry, X-Local-Token middleware, static UI mount
│   │   ├── config.py                   # Paths, local secret token, polite collector throttles
│   │   ├── db\
│   │   │   ├── database.py             # SQLite WAL pragma setup, FTS5 table + sync triggers
│   │   │   └── models.py               # All 10 SQLModel tables
│   │   ├── schemas\                    # Strict Pydantic v2 request/response contracts
│   │   ├── vault\
│   │   │   ├── schema.py               # India Fact Vault model & PII blocklist (PAN/Aadhaar/Passport/DoB)
│   │   │   ├── taxonomy.py             # 500+ canonical tech skills + aliases + Indian city aliases
│   │   │   └── templates.py            # Deterministic {{variable}} cover-note renderer
│   │   ├── resumes\
│   │   │   ├── parser.py               # PDF section & bullet extractor
│   │   │   └── embedder.py             # FastEmbed singleton (BAAI/bge-small-en-v1.5)
│   │   ├── collectors\
│   │   │   ├── base.py                 # Fault-isolated runner, cooldown & health recorder
│   │   │   ├── jobspy_collector.py     # Naukri, LinkedIn, Indeed India, Glassdoor, Google Jobs
│   │   │   ├── ats_greenhouse.py       # boards-api.greenhouse.io
│   │   │   ├── ats_lever.py            # api.lever.co
│   │   │   ├── ats_ashby.py            # api.ashbyhq.com/posting-api
│   │   │   ├── ats_smartrecruiters.py  # api.smartrecruiters.com
│   │   │   ├── ats_workday.py          # CXS POST (limit<=20, 2000-cap split, loop guard)
│   │   │   ├── watchlist_seed.json     # Pre-seeded 60+ India Tech Unicorns & GCCs
│   │   │   └── pruner.py               # Auto-marks vanished ATS roles as Closed
│   │   ├── pipeline\
│   │   │   ├── gate1_filters.py        # Dealbreakers, exp regex, notice check, agency classifier
│   │   │   ├── gate2_identity.py       # 4-Layer Role Identity (Req ID, Sub-Tag, SimHash + 88% Vector)
│   │   │   ├── gate3_extractor.py      # Boilerplate stripper + 10-field signal extraction
│   │   │   ├── gate4_scorer.py         # Option 1 Tier S/A/B/C + Option 3 Semantic Bullets + Alerts
│   │   │   └── orchestrator.py         # Atomic ingestion pipeline (Gates 1 -> 4)
│   │   ├── api\                        # Modular routers: vault, resumes, jobs, collectors, applications, extension, backup
│   │   └── services\                   # JD diff engine, company cooldown checker, ZIP backup/restore
│   ├── tests\                          # Pytest unit, fixture & integration suites
│   └── requirements.txt
├── frontend\                           # React 19 + TypeScript + Vite + Tailwind Dashboard
│   ├── src\
│   │   ├── api\                        # Typed fetch wrapper with X-Local-Token
│   │   ├── pages\                      # JobQueue, Applications, FactVault, Resumes, Collectors
│   │   └── components\                 # JobDetailDrawer (Proof Table + JD Diff), StatusBadges, CooldownBadge
│   └── package.json
├── extension\                          # Manifest V3 Chromium Side-Panel Extension
│   ├── manifest.json                   # sidePanel, activeTab, scripting, storage, 127.0.0.1 host permission
│   ├── src\
│   │   ├── background\service_worker.ts # Token-authenticated localhost bridge + PDF blob proxy
│   │   ├── sidepanel\                  # 4-State Banner, Autofill trigger, Amber Pause-and-Learn, "+ Watch ATS"
│   │   └── content\
│   │       ├── dom_engine.ts           # React/Angular prototype setters, DataTransfer PDF, ARIA dropdowns
│   │       ├── pii_guard.ts            # Hard block for PAN, Aadhaar, Passport, DoB
│   │       ├── submit_watcher.ts       # Submit click, confirmation banner, native Applied badge & Expired detector
│   │       ├── harvester.ts            # On-demand DOM job card extractor (Instahyre, Hirist, Cutshort, Foundit, etc.)
│   │       └── adapters\               # naukri, linkedin, indeed, foundit, instahyre, hirist, cutshort, greenhouse, lever, ashby, workday, smartrecruiters, generic_heuristic
│   └── package.json
└── start.ps1                           # 1-click Windows startup script
```

---

## 3. Planning Document Index

| Document | Contents Covered |
| :--- | :--- |
| [01_Database_Schema_and_API_Contract.md](file:///f:/Projects/JobAutomation/Documentation/Planning/01_Database_Schema_and_API_Contract.md) | Complete ER diagram, all 10 SQLite tables + FTS5 triggers, localhost token security model, and full REST API contract (`/api/v1`). |
| [02_Safety_AntiFlagging_and_Signal_Extraction.md](file:///f:/Projects/JobAutomation/Documentation/Planning/02_Safety_AntiFlagging_and_Signal_Extraction.md) | Credential isolation, polite jitter & `429/403` circuit breaker, non-bypass human rules, high-recall title/city normalization, Hidden Audit Trail, boilerplate stripping, and 10-field extraction. |
| [03_Frontend_and_Chromium_Extension_Design.md](file:///f:/Projects/JobAutomation/Documentation/Planning/03_Frontend_and_Chromium_Extension_Design.md) | 5-page React Dashboard + Job Detail Drawer design, Manifest V3 `chrome.sidePanel` architecture, React/Angular DOM engine, `DataTransfer` PDF upload, PII guardrails, and Amber Pause-and-Learn flow. |
| [04_Implementation_Roadmap_and_Test_Cycles.md](file:///f:/Projects/JobAutomation/Documentation/Planning/04_Implementation_Roadmap_and_Test_Cycles.md) | Dependency graph and detailed specification (Scope, Automated Tests, Definition of Done) for all **7 Code & Test Cycles** + risk matrix. |
