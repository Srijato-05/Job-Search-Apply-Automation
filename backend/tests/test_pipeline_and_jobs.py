"""Cycle 2 tests: 5-Gate pipeline, boilerplate stripping, sibling identity, JD diff & Option 1+3 scoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipeline.gate3_extractor import extract_job_signals, strip_boilerplate

_REPO_ROOT = Path(__file__).resolve().parents[2]

SHARED_RAZORPAY_BOILERPLATE = """
About Razorpay
Razorpay is India's leading full-stack financial solutions company enabling millions of businesses
to accept, process, and disburse payments seamlessly across UPI, cards, netbanking, and wallets.
We empower startups, unicorns, and enterprises across Bengaluru, Gurugram, and Mumbai with modern
financial infrastructure, treasury automation, lending, and neo-banking suites at massive scale.

Benefits & Perks
We provide comprehensive health insurance, wellness allowances, flexible hybrid work culture,
learning budgets, annual retreats, parental support, and stock options for all full-time staff.

Equal Opportunity Employer
Razorpay is an equal opportunity employer committed to building diverse teams without regard to
race, color, religion, gender, sexual orientation, or disability status.
""".strip()


@pytest.fixture()
def pipeline_env(
    tmp_path: Path,
    real_fastembed_service,
    sample_backend_pdf: Path,
    sample_fullstack_pdf: Path,
):
    """Real FastAPI + real FastEmbed app pre-seeded with Fact Vault and 2 Resume Tracks."""
    settings = Settings(
        data_dir=tmp_path / "data",
        fastembed_cache_dir=_REPO_ROOT / ".fastembed_cache",
    )
    app = create_app(settings=settings, embedder=real_fastembed_service)
    client = TestClient(app)
    headers = {"X-Local-Token": app.state.local_token}

    vault_payload = {
        "full_name": "Aarav Sharma",
        "email": "aarav@example.in",
        "current_ctc_lpa": 20.0,
        "expected_ctc_lpa": 28.0,
        "notice_period_days": 30,
        "serving_notice": False,
        "total_exp_years": 4.5,
        "relevant_exp_years": 4.0,
        "current_city": "Bengaluru",
        "preferred_cities_json": ["Bengaluru", "Hyderabad", "Remote (India)"],
        "willing_to_relocate": True,
        "negative_keywords_json": ["Intern", "PHP", "WordPress"],
        "company_blacklist_json": ["ToxicAgency Pvt Ltd"],
    }
    assert client.put("/api/v1/vault", json=vault_payload, headers=headers).status_code == 200

    r_back = client.post(
        "/api/v1/resumes",
        headers=headers,
        data={
            "track_name": "Backend Track",
            "target_titles": '["Backend Engineer", "SDE 2"]',
            "search_locations": "Bengaluru",
        },
        files={"file": ("Backend_Python_Go.pdf", sample_backend_pdf.read_bytes(), "application/pdf")},
    )
    assert r_back.status_code == 201

    r_fs = client.post(
        "/api/v1/resumes",
        headers=headers,
        data={
            "track_name": "FullStack Track",
            "target_titles": '["Full-Stack Engineer", "SDE 2"]',
            "search_locations": "Bengaluru",
        },
        files={"file": ("FullStack_React_Node.pdf", sample_fullstack_pdf.read_bytes(), "application/pdf")},
    )
    assert r_fs.status_code == 201

    return {
        "client": client,
        "headers": headers,
        "backend_resume_id": r_back.json()["id"],
        "fullstack_resume_id": r_fs.json()["id"],
    }


def test_gate3_boilerplate_stripping_and_10_field_extraction() -> None:
    raw_jd = f"""
    <div>
      <h2>About the Role</h2>
      <p>Join our Checkout Payments engineering team in Bellandur, Bangalore (Hybrid).</p>
      <h3>Requirements</h3>
      <ul>
        <li>3-6 years of production experience building microservices with Python, FastAPI, Apache Kafka, and PostgreSQL.</li>
        <li>Notice period up to 30 days preferred. Compensation: 24 - 36 LPA.</li>
        <li>Requisition ID: JR-10421</li>
      </ul>
      <h3>Nice to Have</h3>
      <ul>
        <li>Experience with Docker, Kubernetes, and AWS.</li>
      </ul>
      {SHARED_RAZORPAY_BOILERPLATE}
    </div>
    """
    cleaned = strip_boilerplate(raw_jd)
    assert "About Razorpay" not in cleaned
    assert "Equal Opportunity" not in cleaned
    assert "24 - 36 LPA" in cleaned

    sig = extract_job_signals(
        title="SDE-II Backend",
        company_name="Razorpay Technologies Pvt. Ltd.",
        raw_description=raw_jd,
        location_raw="Bellandur, Bangalore",
        job_url="https://boards.greenhouse.io/razorpay/jobs/9911",
        apply_url="https://boards.greenhouse.io/razorpay/jobs/9911#app",
        portal_name="greenhouse",
    )

    assert sig.company_slug == "razorpay"
    assert sig.normalized_title == "sde 2 backend"
    assert sig.normalized_city == "Bengaluru"
    assert sig.office_locality == "Bellandur"
    assert sig.work_mode == "hybrid"
    assert sig.exp_min_years == 3.0 and sig.exp_max_years == 6.0
    assert sig.salary_min_lpa == 24.0 and sig.salary_max_lpa == 36.0
    assert sig.max_notice_days == 30
    assert sig.req_id == "JR-10421"
    assert sig.role_subtag.startswith("Payments • ")
    assert sig.apply_friction == "fast_apply"
    assert sig.employer_type == "direct_product"
    assert {"Python", "FastAPI", "Apache Kafka", "PostgreSQL"}.issubset(set(sig.primary_skills))
    assert {"Docker", "Kubernetes", "AWS"}.issubset(set(sig.secondary_skills))


def test_gate1_hidden_audit_trail_and_unhide(pipeline_env) -> None:
    client: TestClient = pipeline_env["client"]
    headers = pipeline_env["headers"]

    ingest = client.post(
        "/api/v1/jobs/ingest",
        headers=headers,
        json={
            "jobs": [
                {
                    "title": "Software Engineering Intern",
                    "company_name": "StartupOne",
                    "description_raw": "Python backend internship in Bengaluru.",
                    "location_raw": "Bengaluru",
                    "portal_name": "naukri",
                    "job_url": "https://naukri.com/job/intern-1",
                },
                {
                    "title": "Principal Backend Architect",
                    "company_name": "EnterpriseTwo",
                    "description_raw": "Minimum 9 years experience required in Python and AWS.",
                    "location_raw": "Bengaluru",
                    "portal_name": "linkedin",
                    "job_url": "https://linkedin.com/jobs/view/999",
                },
                {
                    "title": "Senior Backend Engineer",
                    "company_name": "ToxicAgency Pvt Ltd",
                    "description_raw": "Hiring for a leading MNC client. 4+ yrs Python.",
                    "location_raw": "Bengaluru",
                    "portal_name": "naukri",
                    "job_url": "https://naukri.com/job/agency-2",
                },
            ]
        },
    )
    assert ingest.status_code == 201
    results = ingest.json()
    assert all(r["hidden_by_gate1"] is True for r in results)
    assert "negative keyword" in results[0]["hidden_reason"].lower()
    assert "experience floor" in results[1]["hidden_reason"].lower()
    assert "blacklisted company" in results[2]["hidden_reason"].lower()

    # Hidden jobs do not pollute default queue, but appear in Hidden Audit tab
    default_q = client.get("/api/v1/jobs", headers=headers).json()
    assert default_q["total"] == 0

    audit_q = client.get("/api/v1/jobs?only_hidden=true", headers=headers).json()
    assert audit_q["total"] == 3

    # Manual unhide brings job back into active queue
    job_id = results[1]["job_id"]
    unhide = client.patch(
        f"/api/v1/jobs/{job_id}/status",
        headers=headers,
        json={"hidden_by_gate1": False},
    )
    assert unhide.status_code == 200
    assert unhide.json()["hidden_by_gate1"] is False
    assert client.get("/api/v1/jobs", headers=headers).json()["total"] == 1


def test_gate2_sibling_roles_boilerplate_isolation_mirrors_and_diff(pipeline_env) -> None:
    client: TestClient = pipeline_env["client"]
    headers = pipeline_env["headers"]

    # Same title ("SDE II"), same company ("Razorpay"), same city ("Bengaluru"),
    # and identical 400-word corporate boilerplate -- ONLY the team requirements differ!
    jd_payments = f"""
    Responsibilities
    • Build high-throughput UPI settlement and payment ledger services using Python, FastAPI, and Go.
    • Design async Apache Kafka event consumers and PostgreSQL transactional schemas.
    • Optimize Redis caching and deploy Docker containers to AWS EKS.
    {SHARED_RAZORPAY_BOILERPLATE}
    """

    jd_frontend = f"""
    Responsibilities
    • Architect responsive merchant dashboard interfaces with React, TypeScript, and Tailwind CSS.
    • Build GraphQL and Node.js BFF APIs for real-time analytics visualizations.
    • Implement end-to-end UI regression testing using Playwright and Vitest.
    {SHARED_RAZORPAY_BOILERPLATE}
    """

    r1 = client.post(
        "/api/v1/jobs/ingest",
        headers=headers,
        json={
            "title": "SDE II",
            "company_name": "Razorpay",
            "description_raw": jd_payments,
            "location_raw": "Bengaluru",
            "portal_name": "greenhouse",
            "external_job_id": "gh-101",
            "job_url": "https://boards.greenhouse.io/razorpay/jobs/101",
        },
    )
    assert r1.status_code == 201
    res1 = r1.json()[0]
    assert res1["action"] == "new_role"

    # Cross-portal mirror on Naukri for the exact same Payments JD -> merges!
    r1_mirror = client.post(
        "/api/v1/jobs/ingest",
        headers=headers,
        json={
            "title": "SDE 2",
            "company_name": "Razorpay Pvt Ltd",
            "description_raw": jd_payments,
            "location_raw": "Bangalore",
            "portal_name": "naukri",
            "external_job_id": "nk-555",
            "job_url": "https://naukri.com/job/razorpay-sde2-555",
        },
    )
    assert r1_mirror.status_code == 201
    res_mirror = r1_mirror.json()[0]
    assert res_mirror["action"] == "merge_same_role"
    assert res_mirror["job_id"] == res1["job_id"]

    # Sibling role (same title "SDE II", same company, different team/JD) -> stays separate!
    r2 = client.post(
        "/api/v1/jobs/ingest",
        headers=headers,
        json={
            "title": "SDE II",
            "company_name": "Razorpay",
            "description_raw": jd_frontend,
            "location_raw": "Bengaluru",
            "portal_name": "greenhouse",
            "external_job_id": "gh-202",
            "job_url": "https://boards.greenhouse.io/razorpay/jobs/202",
        },
    )
    assert r2.status_code == 201
    res2 = r2.json()[0]
    assert res2["action"] == "sibling_role"
    assert res2["job_id"] != res1["job_id"]

    # Verify detail & sibling linkage + 2 merged portal sources on Payments job
    d1 = client.get(f"/api/v1/jobs/{res1['job_id']}", headers=headers).json()
    assert d1["repost_count"] == 1
    assert len(d1["sources"]) == 2
    assert "Payments" in d1["role_subtag"]

    d2 = client.get(f"/api/v1/jobs/{res2['job_id']}", headers=headers).json()
    assert d2["parent_sibling_job_id"] == res1["job_id"]
    assert "Frontend" in d2["role_subtag"]
    assert any(sib["id"] == res1["job_id"] for sib in d2["sibling_jobs"])

    # Side-by-Side JD Diff endpoint
    diff = client.get(f"/api/v1/jobs/{res1['job_id']}/diff/{res2['job_id']}", headers=headers).json()
    assert diff["similarity_pct"] < 50.0
    assert "Python" in diff["only_in_job_a_skills"]
    assert "React" in diff["only_in_job_b_skills"]
    assert len(diff["added_lines"]) >= 2
    assert len(diff["removed_lines"]) >= 2


def test_gate4_combined_option1_plus_option3_routing_cross_alerts_and_filters(pipeline_env) -> None:
    client: TestClient = pipeline_env["client"]
    headers = pipeline_env["headers"]
    back_id = pipeline_env["backend_resume_id"]
    fs_id = pipeline_env["fullstack_resume_id"]

    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

    # 1. Slam-dunk Backend JD (Tier S -> routes to Backend Track)
    jd_backend = """
    Requirements
    • Design and scale async Apache Kafka event consumers in Python and FastAPI.
    • Optimize PostgreSQL query latency using composite indexing and Redis caching.
    • Containerize backend microservices with Docker and deploy to AWS EKS via CI/CD.
    """
    # 2. Hybrid Backend + React JD (routes to Backend Track with Cross-Resume Alert pointing to FullStack Track)
    jd_hybrid = """
    Requirements
    • Architect async Apache Kafka event consumers in Python and FastAPI.
    • Optimize PostgreSQL query performance with indexing and Redis caching.
    • Develop responsive React and TypeScript analytics dashboards with Tailwind CSS.
    """
    # 3. Java/Spring Boot JD (no Python/Go/JS/TS -> Option 1 hard caps at Tier C!)
    jd_java = """
    Requirements
    • Build high-throughput microservices using Java, Spring Boot, and Hibernate.
    • Optimize SQL schemas and deploy containerized services to Kubernetes.
    • Implement CI/CD pipelines and distributed event streaming.
    """
    # 4. Workday FullStack Enterprise ATS JD (routes to FullStack Track)
    jd_fs = """
    Requirements
    • Develop responsive React and TypeScript analytics dashboards with Tailwind CSS.
    • Build GraphQL and Node.js Express APIs backed by MongoDB and PostgreSQL.
    • Implement automated end-to-end UI test suites using Playwright and Vitest.
    """

    resp = client.post(
        "/api/v1/jobs/ingest",
        headers=headers,
        json={
            "jobs": [
                {
                    "title": "Senior Backend Engineer",
                    "company_name": "Swiggy",
                    "description_raw": jd_backend,
                    "location_raw": "Bengaluru",
                    "portal_name": "lever",
                    "job_url": "https://jobs.lever.co/swiggy/be-1",
                    "posted_at": fresh_ts,
                },
                {
                    "title": "Product Engineer (Backend + UI)",
                    "company_name": "Cred",
                    "description_raw": jd_hybrid,
                    "location_raw": "Bengaluru",
                    "portal_name": "greenhouse",
                    "job_url": "https://boards.greenhouse.io/cred/jobs/hyb-1",
                    "posted_at": old_ts,
                },
                {
                    "title": "Backend Engineer (Java)",
                    "company_name": "Flipkart",
                    "description_raw": jd_java,
                    "location_raw": "Bengaluru",
                    "portal_name": "naukri",
                    "job_url": "https://naukri.com/job/flipkart-java",
                    "posted_at": old_ts,
                },
                {
                    "title": "Full-Stack Engineer",
                    "company_name": "Salesforce India",
                    "description_raw": jd_fs,
                    "location_raw": "Hyderabad",
                    "portal_name": "workday",
                    "job_url": "https://salesforce.wd12.myworkdayjobs.com/External/job/Hyd/FS_JR8801",
                    "posted_at": fresh_ts,
                },
            ]
        },
    )
    assert resp.status_code == 201
    ingested = {r["job_id"]: r for r in resp.json()}
    ids = [r["job_id"] for r in resp.json()]
    be_job_id, hyb_job_id, java_job_id, fs_job_id = ids

    # Check Swiggy Backend -> Tier S + Backend Track
    be_detail = client.get(f"/api/v1/jobs/{be_job_id}", headers=headers).json()
    assert be_detail["winning_score"]["resume_id"] == back_id
    assert be_detail["winning_score"]["tier"] == "S"
    assert be_detail["winning_score"]["semantic_bullet_coverage_pct"] == 100.0
    win_score = next(s for s in be_detail["all_scores"] if s["is_winning_resume"])
    assert all(row["status"] == "MATCHED" and row["matched_bullet"] for row in win_score["bullet_proof_json"])

    # Check Cred Hybrid -> Backend Track wins (Tier A) AND Cross-Resume Alert points to FullStack Track!
    hyb_detail = client.get(f"/api/v1/jobs/{hyb_job_id}", headers=headers).json()
    assert hyb_detail["winning_score"]["resume_id"] == back_id
    assert hyb_detail["winning_score"]["tier"] in {"A", "B"}
    hyb_win = next(s for s in hyb_detail["all_scores"] if s["is_winning_resume"])
    assert len(hyb_win["cross_resume_alerts_json"]) >= 1
    assert hyb_win["cross_resume_alerts_json"][0]["other_resume_id"] == fs_id
    assert "React" in hyb_win["cross_resume_alerts_json"][0]["matching_bullet"]

    # Check Flipkart Java -> Hard Tier C cap by Option 1 despite backend phrasing
    assert ingested[java_job_id]["winning_tier"] == "C"

    # Check Salesforce Workday FullStack -> Tier S + FullStack Track + enterprise_ats friction
    fs_detail = client.get(f"/api/v1/jobs/{fs_job_id}", headers=headers).json()
    assert fs_detail["winning_score"]["resume_id"] == fs_id
    assert fs_detail["winning_score"]["tier"] == "S"
    assert fs_detail["apply_friction"] == "enterprise_ats"
    assert fs_detail["req_id"] == "JR8801"

    # Gate 5 Faceted Filtering & Offline FTS5 Search checks
    fresh_only = client.get("/api/v1/jobs?fresh_6h=true", headers=headers).json()
    assert {item["id"] for item in fresh_only["items"]} == {be_job_id, fs_job_id}

    tier_s_backend = client.get(f"/api/v1/jobs?tier=S&resume_id={back_id}", headers=headers).json()
    assert [item["id"] for item in tier_s_backend["items"]] == [be_job_id]

    enterprise_hyd = client.get("/api/v1/jobs?friction=enterprise_ats&city=Hyd", headers=headers).json()
    assert [item["id"] for item in enterprise_hyd["items"]] == [fs_job_id]

    fts_kafka = client.get("/api/v1/jobs?fts_query=Kafka+AND+FastAPI", headers=headers).json()
    assert {item["id"] for item in fts_kafka["items"]} == {be_job_id, hyb_job_id}

