# Technical Reference: Application Mini-CRM, Offline Snapshots, Extension Bridge & ZIP Backup

This document explains the internal mechanics, state transitions, and safety invariants implemented in **Cycle 4** across [applications/service.py](file:///f:/Projects/JobAutomation/backend/app/applications/service.py), [applications/backup.py](file:///f:/Projects/JobAutomation/backend/app/applications/backup.py), [api/applications.py](file:///f:/Projects/JobAutomation/backend/app/api/applications.py), [api/extension.py](file:///f:/Projects/JobAutomation/backend/app/api/extension.py), and [api/backup.py](file:///f:/Projects/JobAutomation/backend/app/api/backup.py).

---

## 1. Draft vs. Submitted Lifecycle & CRM Stages

`VALID_STAGES` in `applications/service.py` defines 8 lifecycle states:

```text
draft ──(submit / non-draft PATCH)──► applied ──► oa ──► screen ──► interview ──► offer
                                        │                                           │
                                        └──────────────► rejected / withdrawn ◄─────┘
```

### Strict Timestamp & Ownership Guarantees
- **Draft Creation (`POST /api/v1/applications/draft` -> `start_or_resume_draft()`):**
  - Sets `stage = "draft"`, `autofill_started_at = utc_now()`, and leaves `submitted_at = None`.
  - If `resume_id` is omitted and `job_id` is present, automatically defaults to the winning `JobResumeScore` (`is_winning_resume == True`).
  - If a `draft` already exists for `job_id`, merges incoming `submitted_answers_json` and resumes it instead of duplicating rows.
  - If an application for `job_id` has already left `draft` (`submitted_at is not None` or `stage != "draft"`), raises **`409 Conflict`** so submitted snapshots cannot be reverted.
- **Submission (`POST /api/v1/applications/{app_id}/submit` -> `mark_application_submitted()`):**
  - On first submission (`submitted_at is None`), sets `submitted_at = utc_now()`, transitions `draft` -> `applied`, and invokes `_freeze_offline_snapshots()`.
  - If `PATCH /api/v1/applications/{app_id}` moves a `draft` directly to a non-draft stage (e.g., `applied`, `oa`, `interview`), `update_application()` also triggers `submitted_at` + `_freeze_offline_snapshots()` so snapshots are never bypassed.

---

## 2. Immutable Offline Snapshots & Relational Survival

Once an application is submitted, companies frequently edit or delete the live job posting months before interviews begin.

- **Frozen Columns on `applications`:**
  1. `jd_snapshot_text`: Captures `jd_override` or `Job.description_raw` on first submit.
  2. `resume_filename_snapshot`: Captures `resume_filename_override` or `Resume.pdf_filename` on first submit.
  3. `submitted_answers_json`: Preserves the exact screening answers filled at submission time.
- **Immutability Enforced in Code:** `_freeze_offline_snapshots()` only populates `jd_snapshot_text` and `resume_filename_snapshot` when `first_submit` (`app.submitted_at is None`) and those fields are empty. Subsequent `POST /submit` calls can update `recruiter_notes` but **cannot** overwrite already-frozen JD or resume snapshots.
- **Surviving Deleted Jobs/Resumes:** `Application.job_id` and `Application.resume_id` use `ON DELETE SET NULL` foreign keys (`models.py`), so removing an expired `jobs` row sets `job_id = NULL` while leaving all offline snapshots and CRM history intact.

---

## 3. 30-Day Rolling Company Cooldown (`get_company_cooldown_status`)

Many product companies and GCCs enforce a 30-day cooling-off rule per candidate.

- **Limit Resolution:** Reads `FactVault.max_company_apps_30d` (fallback to `Settings.max_company_apps_30d`, default `3`).
- **Calculation Window:** Queries `Application` rows for `company_slug` where `submitted_at >= now - 30 days` (normalizing SQLite's naive `DateTime` values to UTC via `_as_utc()`).
- **Draft Exclusion:** Rows with `stage == "draft"` or `submitted_at is None` **never** count toward the cooldown limit.
- **Outputs (`CooldownStatusResponse`):**
  - `apps_last_30d`, `max_company_apps_30d`, `remaining_apps`, `is_at_limit` (`count >= max_apps`).
  - `next_slot_opens_at`: Exact timestamp `min(submitted_dates) + 30 days` when `is_at_limit` is `True`.
  - `warning_message`: Emitted both when approaching the limit (`count == max_apps - 1`) and when reached (`count >= max_apps`).

---

## 4. Extension 4-State Banner Resolver (`POST /api/v1/extension/check-page`)

`check_extension_page()` resolves the active browser tab read-only (no DB writes) in 3 steps:

```text
Tab Context (URL / external_job_id / title / company / JD text)
  │
  ├─► Step 1: Exact JobSource lookup (job_url or portal_name + external_job_id)
  │
  ├─► Step 2 (if unmatched & JD/title supplied): Run Gate 3 extract_job_signals()
  │           + FastEmbed vector + Gate 2 resolve_job_identity()
  │             ├── merge_same_role / existing_source ──► canonical Job matched (catches Reposts!)
  │             └── sibling_role ───────────────────────► compute_jd_diff(parent, temp_job(id=0))
  │
  └─► Step 3: Resolve Application state + Cooldown
        ├── Application submitted ──► ALREADY_APPLIED (Red Banner, even on reposted URLs)
        ├── Application draft ──────► STARTED_BUT_NOT_SUBMITTED
        ├── Sibling parent linked ──► NEW_SIBLING_ROLE (includes side-by-side sibling_diff)
        └── Unapplied / unmatched ──► NEW_ROLE (with winning_score if tracked + cooldown)
```

- Using `temp_job = Job(id=0, ...)` for un-ingested sibling pages keeps `check-page` strictly read-only while reusing `compute_jd_diff()` without `NoneType` errors.

---

## 5. WAL-Safe ZIP Backup Export & Validated Restore

### Export (`GET /api/v1/backup/export` -> `export_backup_zip`)
1. Calls `create_sqlite_snapshot(db_path, backups_dir)` using `sqlite3.Connection.backup()` so all committed WAL frames are included cleanly without locking live queries.
2. Packages `jobs.db`, all `resumes/*.pdf`, and `manifest.json` (`version`, `exported_at`, `resumes_count`, `resume_filenames`) into an in-memory deflated ZIP download.

### Restore (`POST /api/v1/backup/restore` -> `restore_backup_zip`)
1. **Archive & Security Validation:** Rejects non-ZIP payloads, blocks Zip Slip path traversal (`/`-prefixed, Windows drive letters, or `..` path parts), and requires `jobs.db`.
2. **SQLite Integrity Verification:** Checks the 16-byte SQLite header (`b"SQLite format 3\x00"`) and runs `PRAGMA quick_check;` against a temporary copy *before* touching the live DB.
3. **Windows-Safe Replacement:**
   - Creates an automatic pre-restore safety snapshot of the current DB in `data/backups/`.
   - Calls `engine.dispose()` so SQLAlchemy closes all connection handles on Windows before overwriting `jobs.db`.
   - Unlinks stale `jobs.db-wal` and `jobs.db-shm` sidecar files so old WAL frames cannot replay onto the restored file.
   - Restores `jobs.db` and `resumes/*.pdf`, then re-runs `init_db(engine)` to verify FTS5 triggers and composite indexes.

