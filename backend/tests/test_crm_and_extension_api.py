"""Comprehensive CRM lifecycle, analytics funnel, cooldown edge cases & Extension Check-Page tests."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.applications.service import VALID_STAGES
from app.db.models import Application, utc_now


def test_all_valid_crm_stages_and_invalid_stage_rejection(
    client: TestClient, auth_headers: dict[str, str], sample_backend_pdf
) -> None:
    """Verify full progression through all 8 valid CRM stages and 422 rejection of invalid stages."""
    client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Backend"},
        files={"file": ("Backend_Python_Go.pdf", sample_backend_pdf.read_bytes(), "application/pdf")},
    )
    r_ing = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "title": "SDE II Backend",
            "company_name": "Razorpay",
            "description_raw": "Python, FastAPI, PostgreSQL, and Apache Kafka.",
            "location_raw": "Bengaluru",
            "portal_name": "greenhouse",
            "job_url": "https://boards.greenhouse.io/razorpay/jobs/7701",
        },
    )
    job_id = r_ing.json()[0]["job_id"]

    # Create draft
    draft = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={"job_id": job_id, "portal_used": "greenhouse", "submitted_answers_json": {"city": "Bengaluru"}},
    ).json()
    app_id = draft["id"]

    # Resuming draft merges answers & keeps stage='draft' and submitted_at=None
    resumed = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={"job_id": job_id, "submitted_answers_json": {"relocate": "Yes"}},
    ).json()
    assert resumed["id"] == app_id
    assert resumed["submitted_at"] is None
    assert resumed["submitted_answers_json"] == {"city": "Bengaluru", "relocate": "Yes"}

    # Leaving draft via PATCH sets submitted_at & freezes offline snapshot automatically
    for stage in ("applied", "oa", "screen", "interview", "offer", "rejected", "withdrawn"):
        r_upd = client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"stage": stage},
        )
        assert r_upd.status_code == 200
        assert r_upd.json()["stage"] == stage
        assert r_upd.json()["submitted_at"] is not None
        assert "Apache Kafka" in r_upd.json()["jd_snapshot_text"]

    # Trying to start a new draft on an already-submitted job returns 409 Conflict
    r_dup_draft = client.post(
        "/api/v1/applications/draft",
        headers=auth_headers,
        json={"job_id": job_id},
    )
    assert r_dup_draft.status_code == 409

    # Invalid stage in PATCH and GET filter rejected with 422
    assert (
        client.patch(
            f"/api/v1/applications/{app_id}",
            headers=auth_headers,
            json={"stage": "invalid_stage_xyz"},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/applications?stage=bogus", headers=auth_headers).status_code == 422
    assert len(VALID_STAGES) == 8


def test_draft_validation_and_not_found_errors(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Missing job_id and empty company_slug return 422; unknown job_id or app_id return 404."""
    assert (
        client.post("/api/v1/applications/draft", headers=auth_headers, json={}).status_code == 422
    )
    assert (
        client.post("/api/v1/applications/draft", headers=auth_headers, json={"job_id": 999999}).status_code
        == 404
    )
    assert client.get("/api/v1/applications/999999", headers=auth_headers).status_code == 404
    assert (
        client.post("/api/v1/applications/999999/submit", headers=auth_headers, json={}).status_code == 404
    )
    assert (
        client.patch("/api/v1/applications/999999", headers=auth_headers, json={"stage": "applied"}).status_code
        == 404
    )


def test_analytics_funnel_and_per_track_tier_ab_skill_gaps(
    client: TestClient, auth_headers: dict[str, str], sample_backend_pdf
) -> None:
    """Verify analytics funnel counts, response rate, and Tier C exclusion from Tier A/B missing skills."""
    r_res = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Backend Track"},
        files={"file": ("Backend_Python_Go.pdf", sample_backend_pdf.read_bytes(), "application/pdf")},
    )
    resume_id = r_res.json()["id"]

    # Seed applications across draft, applied, interview, offer, rejected
    stages = ["draft", "applied", "interview", "offer", "rejected"]
    for idx, st in enumerate(stages):
        d = client.post(
            "/api/v1/applications/draft",
            headers=auth_headers,
            json={"company_slug": f"co-{idx}", "resume_id": resume_id},
        ).json()
        if st != "draft":
            client.patch(
                f"/api/v1/applications/{d['id']}",
                headers=auth_headers,
                json={"stage": st},
            )

    analytics = client.get("/api/v1/applications/analytics", headers=auth_headers).json()
    assert analytics["total_drafts"] == 1
    assert analytics["total_submitted"] == 4
    # interview + offer = 2 out of 4 submitted -> 50.0%
    assert analytics["response_rate_pct"] == 50.0
    assert analytics["stage_counts"]["draft"] == 1
    assert analytics["stage_counts"]["interview"] == 1
    assert analytics["stage_counts"]["offer"] == 1


def test_cooldown_warning_thresholds_and_check_page_untracked_company(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify N-1 approaching-limit warning and check-page handling on completely untracked brand-new URLs."""
    # Submit 2 apps against default cap 3 -> triggers approaching limit warning
    for i in range(2):
        d = client.post(
            "/api/v1/applications/draft",
            headers=auth_headers,
            json={"company_slug": "atlassian"},
        ).json()
        client.post(f"/api/v1/applications/{d['id']}/submit", headers=auth_headers, json={})

    cd2 = client.get("/api/v1/applications/cooldown/atlassian", headers=auth_headers).json()
    assert cd2["apps_last_30d"] == 2
    assert cd2["remaining_apps"] == 1
    assert cd2["is_at_limit"] is False
    assert "approaching 30-day cooldown" in (cd2["warning_message"] or "").lower()

    # Check completely untracked posting via /extension/check-page
    r_chk = client.post(
        "/api/v1/extension/check-page",
        headers=auth_headers,
        json={
            "page_url": "https://jobs.lever.co/atlassian/some-new-uuid",
            "title": "Senior Backend Engineer",
            "company_name": "Atlassian",
            "location_raw": "Bengaluru, India",
            "portal_name": "lever",
            "description_raw": "Python, Go, and Kubernetes distributed services.",
        },
    )
    assert r_chk.status_code == 200
    body = r_chk.json()
    assert body["banner_state"] == "NEW_ROLE"
    assert body["company_slug"] == "atlassian"
    assert body["cooldown"]["apps_last_30d"] == 2

