# Job Search & Apply Automation (India-First, Zero-Hallucination, $0 Local-First)

A free-forever, local-first job aggregation, deterministic multi-resume scoring, and Chromium Side-Panel assisted application system built primarily for the **Indian tech job market** while supporting global boards and direct company ATS career portals.

## Core Design Principles

- **\$0 Forever (Local-First):** Runs 100% on your local machine (`127.0.0.1:8000` + SQLite WAL/FTS5 + Chromium unpacked extension) with zero cloud hosting bills, zero paid scraper APIs, and zero LLM API costs.
- **India-First Coverage:** Supports Naukri, LinkedIn India, Indeed India, Glassdoor India, Google Jobs India, Instahyre, Hirist, Cutshort, Wellfound, Foundit/Monster, CareerBuilder, and direct JSON feeds for Greenhouse, Lever, Ashby, SmartRecruiters, and Workday CXS.
- **Zero Hallucinations & Zero Fabricated Info:**
  - Factual form filling is 100% deterministic from your **Verified Fact Vault** (CTC, Notice Period, LWD, Per-Skill Experience Years, 10th/12th/UG/PG scores, City aliases) with an **Amber Pause-and-Learn** prompt for unknown questions and strict PII guardrails (never auto-fills PAN, Aadhaar, Passport, or DoB).
  - Job matching combines **Option 1 (`Tier S/A/B/C` Hard Checklist)** with **Option 3 (Local CPU Semantic Bullet-to-Bullet Alignment via `fastembed` `BAAI/bge-small-en-v1.5`)**—ranking and routing your multiple resume PDFs with zero generative text.
- **Safety & Anti-Ban Architecture:** Complete credential isolation (background collectors never touch personal cookies/logins), polite `4–8s` jitter + automatic `429/403` circuit breaker, on-demand DOM harvesting on strict-WAF portals, and strict non-bypass human-in-the-loop sign-off (never auto-submits).
- **Localhost Security:** Loopback-only `127.0.0.1` binding, random `X-Local-Token` authentication, and locked CORS.

## Repository Layout

```text
JobAutomation/
├── Documentation/
│   ├── Innitial Research/   # Stage 1: Platform, Multi-Resume, Tracking & Autofill Research
│   └── Planning/            # Stage 2: DB Schema, API Contracts, Safety & 7 Implementation Cycles
├── backend/                 # Python 3.12 + FastAPI + Collectors + 5-Gate Pipeline + Pytest
├── frontend/                # React 19 + TypeScript + Vite + Tailwind Local Dashboard
├── extension/               # Manifest V3 Chromium Side-Panel Copilot + Portal Adapters
└── data/                    # Gitignored local SQLite DB, Resume PDFs & Backups
```

## Documentation

- **Stage 1 — Initial Research:** [Documentation/Innitial Research/README.md](Documentation/Innitial%20Research/README.md)
- **Stage 2 — Planning & Roadmap:** [Documentation/Planning/README.md](Documentation/Planning/README.md)

## Project Status

- **Stage 1 (Deep Research):** Complete
- **Stage 2 (Planning):** Complete
- **Stage 3 (Code & Test Cycles 1–7):** Ready to begin upon confirmation
