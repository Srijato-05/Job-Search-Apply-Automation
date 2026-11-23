"""Cycle 4 tests: Application Mini-CRM, Offline Snapshots, 30-Day Cooldown, Extension 4-State Banner & ZIP Backup."""

from __future__ import annotations

from datetime import timedelta
import io
import json
import zipfile

from sqlmodel import Session

from app.db.models import Application, Job, utc_now


def test_full_application_lifecycle_snapshots_and_4state_banner(
    client,
    auth_headers,
    sample_backend_pdf,
):
    """Test Discovered -> Draft -> Submitted -> Immutability -> Repost Red Banner -> Sibling Diff."""
    # 1. Upload resume
    with open(sample_backend_pdf, "rb") as f:
        r_res = client.post(
            "/api/v1/resumes",
            headers=auth_headers,
            data={"track_name": "Backend Core"},
            files={"file": ("Backend_Python_Go.pdf", f, "application/pdf")},
        )
    assert r_res.status_code == 201
    resume_id = r_res.json()["id"]

    # 2. Ingest primary role (Razorpay SDE II Payments)
    payments_jd = (
        "Req ID: JR9001\n"
        "Join Razorpay Payments Core team in Bengaluru.\n"
        "Requirements:\n"
        "- 3+ years building high-throughput APIs with Python, FastAPI, Go, PostgreSQL, and Apache Kafka.\n"
        "- Production Kubernetes and Redis experience."
    )
    r_ing = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "jobs": [
                {
                    "title": "SDE II",
                    "company_name": "Razorpay",
                    "description_raw": payments_jd,
                    "location_raw": "Bengaluru, India",
                    "portal_name": "greenhouse",
                    "external_job_id": "9001",
                    "job_url": "https://boards.greenhouse.io/razorpay/jobs/9001",
                }
            ]
        },
    )
    assert r_ing.status_code == 201
    job_id = r_ing.json()[0]["job_id"]

    # 3. Check page -> NEW_ROLE
    r_chk1 = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={
            "page_url": "https://boards.greenhouse.io/razorpay/jobs/9001",
            "title": "SDE II",
            "company_name": "Razorpay",
            "description_raw": payments_jd,
        },
    )
    assert r_chk1.status_code == 200
    chk1 = r_chk1.json()
    assert chk1["banner_state"] == "NEW_ROLE"
    assert chk1["job_id"] == job_id
    assert chk1["winning_score"]["resume_id"] == resume_id

    # 4. Autofill starts -> Draft (does NOT set submitted_at)
    r_draft = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={
            "job_id": job_id,
            "portal_used": "greenhouse",
            "submitted_answers_json": {"notice_period": "30 days"},
        },
    )
    assert r_draft.status_code == 201
    draft = r_draft.json()
    app_id = draft["id"]
    assert draft["stage"] == "draft"
    assert draft["autofill_started_at"] is not None
    assert draft["submitted_at"] is None

    # 5. Check page -> STARTED_BUT_NOT_SUBMITTED
    r_chk2 = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={"page_url": "https://boards.greenhouse.io/razorpay/jobs/9001"},
    )
    assert r_chk2.status_code == 200
    assert r_chk2.json()["banner_state"] == "STARTED_BUT_NOT_SUBMITTED"
    assert r_chk2.json()["application_id"] == app_id

    # 6. User clicks Submit -> freezes immutable offline snapshot
    r_sub = client.post(
        f"/api/v1/applications/{app_id}/submit",
        headers=auth_headers,
        json={
            "submitted_answers_json": {"expected_ctc": "35 LPA"},
            "recruiter_notes": "Applied directly on Greenhouse",
        },
    )
    assert r_sub.status_code == 200
    sub = r_sub.json()
    assert sub["stage"] == "applied"
    assert sub["submitted_at"] is not None
    assert "Apache Kafka" in sub["jd_snapshot_text"]
    assert sub["resume_filename_snapshot"] == "Backend_Python_Go.pdf"
    assert sub["submitted_answers_json"]["notice_period"] == "30 days"
    assert sub["submitted_answers_json"]["expected_ctc"] == "35 LPA"

    # Attempt to overwrite snapshot after submit -> must stay immutable
    r_resub = client.post(
        f"/api/v1/applications/{app_id}/submit",
        headers=auth_headers,
        json={
            "jd_snapshot_text": "TAMPERED JD",
            "resume_filename_snapshot": "TAMPERED.pdf",
        },
    )
    assert r_resub.status_code == 200
    assert r_resub.json()["resume_filename_snapshot"] == "Backend_Python_Go.pdf"
    assert "TAMPERED" not in r_resub.json()["jd_snapshot_text"]

    # 7. Repost / Mirror URL (new LinkedIn URL, same role/Req ID) -> ALREADY_APPLIED Red Banner
    r_repost = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={
            "page_url": "https://www.linkedin.com/jobs/view/999888777",
            "title": "SDE II",
            "company_name": "Razorpay",
            "location_raw": "Bengaluru, India",
            "portal_name": "linkedin",
            "description_raw": payments_jd,
        },
    )
    assert r_repost.status_code == 200
    repost = r_repost.json()
    assert repost["banner_state"] == "ALREADY_APPLIED"
    assert repost["application_id"] == app_id

    # 8. Same company + same title, different team & Req ID -> NEW_SIBLING_ROLE + JD Diff
    frontend_jd = (
        "Req ID: JR9002\n"
        "Join Razorpay Merchant Dashboard Frontend team in Bengaluru.\n"
        "Requirements:\n"
        "- 3+ years building responsive SPAs using React, TypeScript, Next.js, and Tailwind CSS."
    )
    r_sib = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={
            "page_url": "https://boards.greenhouse.io/razorpay/jobs/9002",
            "title": "SDE II",
            "company_name": "Razorpay",
            "location_raw": "Bengaluru, India",
            "portal_name": "greenhouse",
            "description_raw": frontend_jd,
        },
    )
    assert r_sib.status_code == 200
    sib = r_sib.json()
    assert sib["banner_state"] == "NEW_SIBLING_ROLE"
    assert sib["sibling_parent_id"] == job_id
    assert sib["sibling_diff"] is not None
    assert "React" in sib["sibling_diff"]["only_in_job_b_skills"]

    # 9. CRM stage transition & survival if original Job row is deleted
    r_patch = client.patch(
        f"/api/v1/applications/{app_id}",
        headers=auth_headers,
        json={"stage": "interview", "recruiter_notes": "Cleared OA, technical round Friday"},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["stage"] == "interview"

    with Session(client.app.state.engine) as session:
        orig_job = session.get(Job, job_id)
        session.delete(orig_job)
        session.commit()

    r_after_del = client.get(f"/api/v1/applications/{app_id}", headers=auth_headers)
    assert r_after_del.status_code == 200
    survived = r_after_del.json()
    assert survived["job_id"] is None
    assert "Apache Kafka" in survived["jd_snapshot_text"]
    assert survived["resume_filename_snapshot"] == "Backend_Python_Go.pdf"
    assert survived["stage"] == "interview"


def test_30_day_company_cooldown_counts_only_submitted(client, auth_headers):
    """Verify drafts don't count toward 30-day cap and 3 submitted apps trigger limit."""
    # Start 1 draft -> must NOT count toward cooldown
    r_draft = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={"company_slug": "swiggy", "portal_used": "greenhouse"},
    )
    assert r_draft.status_code == 201
    cd0 = client.get("/api/v1/applications/cooldown/swiggy", headers=auth_headers).json()
    assert cd0["apps_last_30d"] == 0
    assert cd0["is_at_limit"] is False

    # Submit 3 separate applications within trailing 30 days
    for i in range(3):
        d = client.post(
            "/api/v1/applications/draft",
            headers=auth_headers,
            json={"company_slug": "swiggy", "portal_used": "greenhouse"},
        ).json()
        s = client.post(
            f"/api/v1/applications/{d['id']}/submit",
            headers=auth_headers,
            json={"jd_snapshot_text": f"Swiggy Role #{i}"},
        )
        assert s.status_code == 200

    cd3 = client.get("/api/v1/applications/cooldown/swiggy", headers=auth_headers).json()
    assert cd3["apps_last_30d"] == 3
    assert cd3["remaining_apps"] == 0
    assert cd3["is_at_limit"] is True
    assert cd3["next_slot_opens_at"] is not None
    assert "cooldown limit reached" in cd3["warning_message"].lower()

    # Submitted application older than 30 days should not count
    with Session(client.app.state.engine) as session:
        old_app = Application(
            company_slug="groww",
            stage="applied",
            submitted_at=utc_now() - timedelta(days=35),
            jd_snapshot_text="Old Groww Role",
        )
        session.add(old_app)
        session.commit()

    cd_groww = client.get("/api/v1/applications/cooldown/groww", headers=auth_headers).json()
    assert cd_groww["apps_last_30d"] == 0
    assert cd_groww["is_at_limit"] is False


def test_zip_backup_export_restore_and_validation(
    client,
    auth_headers,
    sample_backend_pdf,
):
    """Verify ZIP Backup bundles SQLite + PDFs and restores cleanly after mutation."""
    # 1. Seed a resume PDF + submitted application
    with open(sample_backend_pdf, "rb") as f:
        r_res = client.post(
            "/api/v1/resumes",
            headers=auth_headers,
            data={"track_name": "Backend Core"},
            files={"file": ("Backend_Python_Go.pdf", f, "application/pdf")},
        )
    assert r_res.status_code == 201
    resume_id = r_res.json()["id"]

    d = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={"company_slug": "cred", "resume_id": resume_id, "portal_used": "greenhouse"},
    ).json()
    r_sub = client.post(
        f"/api/v1/applications/{d['id']}/submit",
        headers=auth_headers,
        json={"jd_snapshot_text": "CRED Backend Snapshot", "recruiter_notes": "Preserve this"},
    )
    assert r_sub.status_code == 200
    app_id = r_sub.json()["id"]

    # 2. Export ZIP backup
    r_exp = client.get("/api/v1/backup/export", headers=auth_headers)
    assert r_exp.status_code == 200
    assert r_exp.headers["content-type"] == "application/zip"
    zip_bytes = r_exp.content

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = set(zf.namelist())
        assert "jobs.db" in names
        assert any(
            n.startswith("resumes/") and n.endswith("Backend_Python_Go.pdf")
            for n in names
        )
        assert "manifest.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["resumes_count"] == 1

    # 3. Validation guards: reject corrupt ZIP and Zip Slip path traversal
    r_bad = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
    )
    assert r_bad.status_code == 422

    slip_buf = io.BytesIO()
    with zipfile.ZipFile(slip_buf, "w") as zf:
        zf.writestr("../escape.txt", "evil")
        zf.writestr("jobs.db", b"SQLite format 3\x00dummy")
    r_slip = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("slip.zip", slip_buf.getvalue(), "application/zip")},
    )
    assert r_slip.status_code == 422

    # 4. Mutate live state (add unwanted app + delete resume PDF) then restore backup
    r_extra = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={"company_slug": "unwanted-corp"},
    )
    assert r_extra.status_code == 201
    client.delete(f"/api/v1/resumes/{resume_id}", headers=auth_headers)

    r_rest = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r_rest.status_code == 200
    rest = r_rest.json()
    assert rest["status"] == "restored"
    assert rest["restored_resumes_count"] == 1

    # 5. Verify original state restored cleanly and unwanted mutation reverted
    r_apps = client.get("/api/v1/applications", headers=auth_headers).json()
    slugs = {a["company_slug"] for a in r_apps}
    assert "cred" in slugs
    assert "unwanted-corp" not in slugs

    r_orig = client.get(f"/api/v1/applications/{app_id}", headers=auth_headers)
    assert r_orig.status_code == 200
    assert r_orig.json()["recruiter_notes"] == "Preserve this"

    r_pdf = client.get(f"/api/v1/resumes/{resume_id}/file", headers=auth_headers)
    assert r_pdf.status_code == 200
    assert len(r_pdf.content) > 0

