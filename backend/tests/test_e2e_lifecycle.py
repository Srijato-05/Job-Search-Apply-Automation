"""End-to-End Integration Lifecycle Test across Vault, Resumes, 5-Gate Pipeline, Extension, CRM, Analytics & Backup."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_full_end_to_end_job_automation_lifecycle(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_backend_pdf: Path,
    sample_fullstack_pdf: Path,
) -> None:
    """Walk through the complete real-world workflow from onboarding through backup restore."""
    # 1. Populate Fact Vault & Pause-and-Learn Q&A Rule
    r_vault = client.put(
        "/api/v1/vault",
        headers=auth_headers,
        json={
            "full_name": "Aarav Sharma",
            "email": "aarav@example.in",
            "phone": "+91-9876543210",
            "current_ctc_lpa": 20.0,
            "expected_ctc_lpa": 30.0,
            "notice_period_days": 30,
            "serving_notice": False,
            "total_exp_years": 4.5,
            "relevant_exp_years": 4.0,
            "current_city": "Bengaluru",
            "preferred_cities_json": ["Bengaluru", "Remote (India)"],
            "willing_to_relocate": True,
            "negative_keywords_json": ["Intern"],
            "company_blacklist_json": ["BlacklistedAgency"],
            "max_company_apps_30d": 3,
        },
    )
    assert r_vault.status_code == 200

    r_qa = client.post(
        "/api/v1/vault/qa-rules",
        headers=auth_headers,
        json={
            "question": "Authorized to work in India?",
            "canonical_aliases": ["work authorization"],
            "verified_answer": "Yes",
            "answer_type": "boolean",
            "portal_scope": "global",
        },
    )
    assert r_qa.status_code == 201

    # 2. Upload two tailored resumes (Backend & Full-Stack)
    r_back = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Backend Core", "target_titles": '["Backend Engineer", "SDE 2"]'},
        files={"file": ("Backend_Python_Go.pdf", sample_backend_pdf.read_bytes(), "application/pdf")},
    )
    assert r_back.status_code == 201
    backend_id = r_back.json()["id"]

    r_fs = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "FullStack Web", "target_titles": '["Full-Stack Engineer"]'},
        files={"file": ("FullStack_React_Node.pdf", sample_fullstack_pdf.read_bytes(), "application/pdf")},
    )
    assert r_fs.status_code == 201

    # 3. Ingest batch: one clean Backend role + one sibling Frontend role + one Gate-1-hidden Intern role
    payments_jd = (
        "Req ID: JR5001\n"
        "Requirements:\n"
        "- Architected async Apache Kafka event consumers in Python and FastAPI processing 2M events/day.\n"
        "- PostgreSQL, Redis, Docker, Kubernetes on AWS."
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
                    "external_job_id": "5001",
                    "job_url": "https://boards.greenhouse.io/razorpay/jobs/5001",
                },
                {
                    "title": "SDE II",
                    "company_name": "Razorpay",
                    "description_raw": (
                        "Req ID: JR5002\n"
                        "Requirements:\n"
                        "- Build React, TypeScript, Next.js and Tailwind CSS merchant dashboards.\n"
                    ),
                    "location_raw": "Bengaluru, India",
                    "portal_name": "greenhouse",
                    "external_job_id": "5002",
                    "job_url": "https://boards.greenhouse.io/razorpay/jobs/5002",
                },
                {
                    "title": "Software Engineering Intern",
                    "company_name": "Razorpay",
                    "description_raw": "Python internship.",
                    "location_raw": "Bengaluru",
                    "portal_name": "naukri",
                    "job_url": "https://www.naukri.com/job/intern-5003",
                },
            ]
        },
    )
    assert r_ing.status_code == 201
    ing_rows = r_ing.json()
    job_be_id = ing_rows[0]["job_id"]
    job_sib_id = ing_rows[1]["job_id"]
    assert ing_rows[1]["action"] == "sibling_role"
    assert ing_rows[2]["hidden_by_gate1"] is True

    # Active queue shows only the 2 non-hidden jobs; FTS5 finds the Kafka role
    q = client.get("/api/v1/jobs?fts_query=Kafka", headers=auth_headers).json()
    assert q["total"] == 1
    assert q["items"][0]["id"] == job_be_id
    assert q["items"][0]["winning_score"]["resume_id"] == backend_id

    # 4. Extension Check-Page -> NEW_ROLE -> Start Draft -> STARTED_BUT_NOT_SUBMITTED -> Submit -> ALREADY_APPLIED
    chk1 = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={"page_url": "https://boards.greenhouse.io/razorpay/jobs/5001"},
    ).json()
    assert chk1["banner_state"] == "NEW_ROLE"

    draft = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={"job_id": job_be_id, "portal_used": "greenhouse", "submitted_answers_json": {"authorized": "Yes"}},
    ).json()
    app_id = draft["id"]

    chk2 = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={"page_url": "https://boards.greenhouse.io/razorpay/jobs/5001"},
    ).json()
    assert chk2["banner_state"] == "STARTED_BUT_NOT_SUBMITTED"

    sub = client.post(
        f"/api/v1/applications/{app_id}/submit",
        headers=auth_headers,
        json={"recruiter_notes": "Submitted after manual review"},
    ).json()
    assert sub["stage"] == "applied"
    assert sub["resume_filename_snapshot"] == "Backend_Python_Go.pdf"

    # Mirror URL on LinkedIn for same JD -> ALREADY_APPLIED Red Banner
    chk_mirror = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={
            "page_url": "https://www.linkedin.com/jobs/view/999000111",
            "title": "SDE II",
            "company_name": "Razorpay",
            "location_raw": "Bengaluru",
            "portal_name": "linkedin",
            "description_raw": payments_jd,
        },
    ).json()
    assert chk_mirror["banner_state"] == "ALREADY_APPLIED"

    # Sibling URL -> NEW_SIBLING_ROLE + diff
    chk_sib = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={"page_url": "https://boards.greenhouse.io/razorpay/jobs/5002"},
    ).json()
    assert chk_sib["banner_state"] == "NEW_SIBLING_ROLE"
    assert chk_sib["job_id"] == job_sib_id

    # 5. Cooldown & Analytics reflect 1 submitted app
    assert client.get("/api/v1/applications/cooldown/razorpay", headers=auth_headers).json()["apps_last_30d"] == 1
    analytics = client.get("/api/v1/applications/analytics", headers=auth_headers).json()
    assert analytics["total_submitted"] == 1
    assert analytics["total_drafts"] == 0

    # 6. Export Backup ZIP -> Mutate Vault -> Restore Backup ZIP -> Verify Original Vault Restored
    zip_bytes = client.get("/api/v1/backup/export", headers=auth_headers).content
    client.put(
        "/api/v1/vault",
        headers=auth_headers,
        json={"full_name": "Mutated Name", "expected_ctc_lpa": 99.0},
    )
    assert client.get("/api/v1/vault", headers=auth_headers).json()["full_name"] == "Mutated Name"

    r_rest = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("e2e_backup.zip", zip_bytes, "application/zip")},
    )
    assert r_rest.status_code == 200
    assert client.get("/api/v1/vault", headers=auth_headers).json()["full_name"] == "Aarav Sharma"
    assert client.get(f"/api/v1/applications/{app_id}", headers=auth_headers).json()["stage"] == "applied"

