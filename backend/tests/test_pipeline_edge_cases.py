"""Comprehensive 5-Gate pipeline edge-case tests: Gate 1..5, multi-resume routing & tier bounds."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import Settings
from app.db.models import Company, FactVault, Job
from app.main import create_app
from app.pipeline.gate1_filters import effective_candidate_notice_days, evaluate_gate1
from app.pipeline.gate2_identity import compute_description_hash, compute_simhash64
from app.pipeline.gate3_extractor import extract_job_signals, normalize_job_title, slugify_company
from app.pipeline.gate4_scorer import detect_role_archetype


def test_gate1_notice_calculation_and_blacklist_variants() -> None:
    """Verify serving notice LWD, negotiable notice, word-boundary negative keywords, and slug blacklists."""
    today = date(2026, 11, 24)

    # Serving notice uses remaining days to LWD
    v_serving = FactVault(serving_notice=True, last_working_day=date(2026, 12, 4), notice_period_days=90)
    assert effective_candidate_notice_days(v_serving, today=today) == 10

    # Past LWD clamps to 0
    v_past = FactVault(serving_notice=True, last_working_day=date(2026, 11, 20), notice_period_days=60)
    assert effective_candidate_notice_days(v_past, today=today) == 0

    # Negotiable notice picks minimum
    v_neg = FactVault(serving_notice=False, notice_negotiable=True, notice_period_days=60, min_negotiable_days=15)
    assert effective_candidate_notice_days(v_neg, today=today) == 15

    # Word boundary guard: 'Intern' blocks 'Software Intern' but NOT 'Internal Tools Engineer'
    vault = FactVault(
        total_exp_years=4.0,
        negative_keywords_json=["Intern", "PHP"],
        company_blacklist_json=["Shady Consulting Pvt Ltd"],
    )
    sig_internal = extract_job_signals(
        title="Senior Internal Tools Engineer",
        company_name="Razorpay",
        raw_description="Build developer productivity tools in Python. Notice period up to 15 days.",
    )
    res_internal = evaluate_gate1(sig_internal, vault)
    assert res_internal.hidden_by_gate1 is False

    sig_intern = extract_job_signals(
        title="Backend Engineering Intern",
        company_name="Razorpay",
        raw_description="Summer internship.",
    )
    res_intern = evaluate_gate1(sig_intern, vault)
    assert res_intern.hidden_by_gate1 is True
    assert "Intern" in (res_intern.hidden_reason or "")

    # Legal-suffix-normalized company blacklist match
    sig_black = extract_job_signals(
        title="SDE II",
        company_name="Shady Consulting",
        raw_description="Hiring Python dev.",
    )
    res_black = evaluate_gate1(sig_black, vault)
    assert res_black.hidden_by_gate1 is True

    # Experience buffer check (total=4.0, buffer=2.0 -> 6.0 allowed, 6.5 hidden)
    sig_ok = extract_job_signals("SDE II", "Swiggy", "6+ years experience required in Python.")
    assert evaluate_gate1(sig_ok, vault, exp_buffer_years=2.0).hidden_by_gate1 is False
    sig_high = extract_job_signals("Staff Engineer", "Swiggy", "7+ years experience required in Python.")
    assert evaluate_gate1(sig_high, vault, exp_buffer_years=2.0).hidden_by_gate1 is True


def test_gate3_extraction_edge_cases_salary_exp_cities_employer_type() -> None:
    """Verify title normalization, company slugification, employer types, salary/exp ranges, and empty JDs."""
    assert normalize_job_title("Sr. SDE-II (Backend)") == "senior sde 2 backend"
    assert normalize_job_title("Staff Eng IV") == "staff eng 4"
    assert slugify_company("Razorpay Technologies Pvt. Ltd.") == "razorpay"
    assert slugify_company("!!!") == "unknown-company"

    # Empty / minimal JD must not crash
    empty_sig = extract_job_signals(title="Software Engineer", company_name="Acme", raw_description="")
    assert empty_sig.boilerplate_stripped_text == ""
    assert empty_sig.requirement_lines == []

    # Staffing agency vs IT service vs Direct product detection
    staffing_sig = extract_job_signals(
        title="Python Developer",
        company_name="Apex Talent Solutions",
        raw_description="Hiring for a leading product MNC client in Noida. Immediate joiner preferred.",
        location_raw="Sector 62, Noida, NCR",
    )
    assert staffing_sig.employer_type == "staffing_agency"
    assert staffing_sig.max_notice_days == 0
    assert staffing_sig.normalized_city == "Noida"

    service_sig = extract_job_signals(
        title="Software Engineer",
        company_name="Infosys Limited",
        raw_description="Work with ₹ 18 - 26 Lakhs p.a. package. 2 to 5 yrs exp. Work from home option.",
        location_raw="Gurgaon, Haryana",
        portal_name="naukri",
        job_url="https://www.naukri.com/job-listings-12345",
    )
    assert service_sig.employer_type == "direct_service"
    assert service_sig.salary_min_lpa == 18.0
    assert service_sig.salary_max_lpa == 26.0
    assert service_sig.exp_min_years == 2.0
    assert service_sig.exp_max_years == 5.0
    assert service_sig.work_mode == "remote"
    assert service_sig.normalized_city == "Gurugram"
    assert service_sig.apply_friction == "fast_apply"

    # Single salary upper bound ("Up to 42 LPA") + inline bonus skill separation
    inline_bonus_sig = extract_job_signals(
        title="Backend Engineer",
        company_name="CRED",
        raw_description=(
            "Requirements:\n"
            "- Production Python and FastAPI microservices (Up to 42 LPA).\n"
            "Nice to have: GraphQL and Terraform experience.\n"
        ),
        portal_name="greenhouse",
        job_url="https://boards.greenhouse.io/cred/jobs/5511?gh_jid=987654",
    )
    assert inline_bonus_sig.salary_max_lpa == 42.0
    assert inline_bonus_sig.req_id == "987654"
    assert {"Python", "FastAPI"}.issubset(set(inline_bonus_sig.primary_skills))
    assert {"GraphQL", "Terraform"}.issubset(set(inline_bonus_sig.secondary_skills))


def test_gate2_simhash_req_id_conflict_and_dedup_behavior(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify SimHash determinism, duplicate URL suppression (existing_source), and conflicting Req IDs never merge."""
    h1 = compute_description_hash("Build   FastAPI   services")
    h2 = compute_description_hash("build fastapi services")
    assert h1 == h2

    sh = compute_simhash64("Python FastAPI Kafka PostgreSQL microservices")
    assert -(1 << 63) <= sh < (1 << 63)
    assert compute_simhash64("") == 0

    # Ingest first job with Req ID JR100
    base_jd = "Build reliable payment microservices in Python, FastAPI, PostgreSQL, and Apache Kafka."
    r1 = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "title": "Backend Engineer",
            "company_name": "PhonePe",
            "description_raw": f"Req ID: JR100\n{base_jd}",
            "location_raw": "Bengaluru",
            "portal_name": "greenhouse",
            "external_job_id": "pp-100",
            "job_url": "https://boards.greenhouse.io/phonepe/jobs/100",
        },
    )
    assert r1.status_code == 201
    id1 = r1.json()[0]["job_id"]

    # Re-ingest exact same URL -> existing_source (no repost_count bump)
    r_dup = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "title": "Backend Engineer",
            "company_name": "PhonePe",
            "description_raw": f"Req ID: JR100\n{base_jd}",
            "location_raw": "Bengaluru",
            "portal_name": "greenhouse",
            "external_job_id": "pp-100",
            "job_url": "https://boards.greenhouse.io/phonepe/jobs/100",
        },
    )
    assert r_dup.status_code == 201
    assert r_dup.json()[0]["action"] == "existing_source"
    assert r_dup.json()[0]["job_id"] == id1

    # Different Req ID JR200 with IDENTICAL JD text -> must still become sibling_role, NEVER merged!
    r_diff_req = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "title": "Backend Engineer",
            "company_name": "PhonePe",
            "description_raw": f"Req ID: JR200\n{base_jd}",
            "location_raw": "Bengaluru",
            "portal_name": "greenhouse",
            "external_job_id": "pp-200",
            "job_url": "https://boards.greenhouse.io/phonepe/jobs/200",
        },
    )
    assert r_diff_req.status_code == 201
    assert r_diff_req.json()[0]["action"] == "sibling_role"
    assert r_diff_req.json()[0]["job_id"] != id1


def test_gate4_no_resumes_uploaded_and_archetype_detection(
    client: TestClient, auth_headers: dict[str, str], sample_backend_pdf: Path
) -> None:
    """Ingesting jobs when 0 resumes exist succeeds with winning_tier=None, then /rescore populates scores."""
    assert detect_role_archetype("Site Reliability Engineer", {"Kubernetes"}) == "devops"
    assert detect_role_archetype("Android Developer", {"Kotlin"}) == "mobile"
    assert detect_role_archetype("ML Engineer", {"Python", "PyTorch"}) == "data_ml"
    assert detect_role_archetype("Full Stack Engineer", {"Python", "React"}) == "fullstack"

    # 1. Ingest before uploading any resume
    r_ing = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "title": "Backend Engineer",
            "company_name": "Zerodha",
            "description_raw": "Requirements:\n• Architected async Apache Kafka event consumers in Python and FastAPI.",
            "location_raw": "Bengaluru",
            "portal_name": "greenhouse",
            "job_url": "https://boards.greenhouse.io/zerodha/jobs/1",
        },
    )
    assert r_ing.status_code == 201
    ing = r_ing.json()[0]
    assert ing["winning_tier"] is None
    assert ing["winning_resume_id"] is None

    # 2. Upload resume then call POST /api/v1/jobs/rescore
    r_res = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Backend Track"},
        files={"file": ("Backend_Python_Go.pdf", sample_backend_pdf.read_bytes(), "application/pdf")},
    )
    assert r_res.status_code == 201

    r_rescore = client.post("/api/v1/jobs/rescore", headers=auth_headers)
    assert r_rescore.status_code == 200
    assert r_rescore.json()["rescored_count"] == 1

    detail = client.get(f"/api/v1/jobs/{ing['job_id']}", headers=auth_headers).json()
    assert detail["winning_score"] is not None
    assert detail["winning_score"]["resume_id"] == r_res.json()["id"]


def test_gate5_city_ncr_and_notice_filter_and_company_blacklist_table(
    client: TestClient, auth_headers: dict[str, str], sample_backend_pdf: Path
) -> None:
    """Verify Gate 5 notice_compatible filter, NCR city equivalence, and Company.is_blacklisted DB flag."""
    # Mark a watched company blacklisted directly on Company model
    with Session(client.app.state.engine) as session:
        session.add(
            Company(
                slug="evilbrand",
                display_name="EvilBrand",
                is_watched=False,
                is_blacklisted=True,
            )
        )
        session.commit()

    client.put(
        "/api/v1/vault",
        headers=auth_headers,
        json={"notice_period_days": 60, "serving_notice": False, "notice_negotiable": False},
    )
    client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Backend"},
        files={"file": ("Backend_Python_Go.pdf", sample_backend_pdf.read_bytes(), "application/pdf")},
    )

    resp = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "company_name": "EvilBrand",
                    "description_raw": "Python FastAPI Kafka developer in Bengaluru.",
                    "location_raw": "Bengaluru",
                    "job_url": "https://example.com/evil/1",
                },
                {
                    "title": "Backend Engineer",
                    "company_name": "Zomato",
                    "description_raw": "Immediate joiner or notice period max 15 days. Python and FastAPI.",
                    "location_raw": "Gurgaon",
                    "job_url": "https://example.com/zomato/1",
                },
                {
                    "title": "Backend Engineer",
                    "company_name": "Paytm",
                    "description_raw": "Notice period up to 90 days. Python and FastAPI microservices.",
                    "location_raw": "Noida",
                    "job_url": "https://example.com/paytm/1",
                },
            ]
        },
    )
    assert resp.status_code == 201
    res = resp.json()
    assert res[0]["hidden_by_gate1"] is True  # Company.is_blacklisted respected

    # Notice compatible filter separates Zomato (false: 60d > 15d) and Paytm (true: 60d <= 90d)
    compat = client.get("/api/v1/jobs?notice_compatible=true&city=Delhi+NCR", headers=auth_headers).json()
    assert [i["company_name"] for i in compat["items"]] == ["Paytm"]

    incompat = client.get("/api/v1/jobs?notice_compatible=false&city=Delhi+NCR", headers=auth_headers).json()
    assert [i["company_name"] for i in incompat["items"]] == ["Zomato"]

