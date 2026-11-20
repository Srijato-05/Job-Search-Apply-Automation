"""Tests for India Fact Vault validation, PII guardrails, Q&A rules, taxonomy, and templates."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.vault.taxonomy import (
    SKILL_ALIASES,
    cities_compatible,
    extract_office_locality,
    extract_skills_from_text,
    is_india_location,
    normalize_city,
    normalize_skill,
)


def test_fact_vault_round_trip_and_validation(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = {
        "full_name": "Aarav Sharma",
        "email": "aarav@example.in",
        "phone": "+91-9876543210",
        "linkedin_url": "https://linkedin.com/in/aaravsharma",
        "github_url": "https://github.com/aaravsharma",
        "current_ctc_lpa": 18.5,
        "current_fixed_lpa": 16.0,
        "current_variable_lpa": 2.5,
        "expected_ctc_lpa": 25.0,
        "notice_period_days": 30,
        "serving_notice": True,
        "last_working_day": "2026-12-15",
        "notice_negotiable": True,
        "min_negotiable_days": 15,
        "total_exp_years": 4.5,
        "relevant_exp_years": 4.0,
        "skill_years_json": {"Python": 4.5, "FastAPI": 3.0, "PostgreSQL": 3.5},
        "current_city": "Bengaluru",
        "hometown": "Jaipur",
        "preferred_cities_json": ["Bengaluru", "Hyderabad", "Remote (India)"],
        "willing_to_relocate": True,
        "work_modes_json": ["Hybrid", "Remote"],
        "tenth_pct": 94.2,
        "tenth_board": "CBSE",
        "tenth_year": 2016,
        "twelfth_pct": 91.6,
        "twelfth_board": "CBSE",
        "twelfth_year": 2018,
        "education_history_json": [
            {
                "degree": "B.Tech",
                "specialization": "CSE",
                "university": "VTU",
                "passing_year": 2022,
                "cgpa": 8.7,
                "percentage": 82.0,
            }
        ],
        "active_backlogs": 0,
        "negative_keywords_json": ["Intern", "PHP", "WordPress"],
        "company_blacklist_json": ["BadAgency Pvt Ltd"],
        "max_company_apps_30d": 3,
    }

    put_resp = client.put("/api/v1/vault", json=payload, headers=auth_headers)
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["current_ctc_lpa"] == 18.5
    assert body["expected_ctc_lpa"] == 25.0
    assert body["last_working_day"] == "2026-12-15"
    assert body["tenth_pct"] == 94.2

    get_resp = client.get("/api/v1/vault", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["skill_years_json"]["FastAPI"] == 3.0

    # Invalid negative CTC or >100 percentage rejected with 422
    bad_payload = dict(payload, tenth_pct=105.0)
    assert client.put("/api/v1/vault", json=bad_payload, headers=auth_headers).status_code == 422
    bad_ctc = dict(payload, expected_ctc_lpa=-5.0)
    assert client.put("/api/v1/vault", json=bad_ctc, headers=auth_headers).status_code == 422


def test_pii_guard_blocks_gov_ids_and_allows_safe_qa_rules(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    blocked_questions = [
        ("Please enter your PAN Card Number", "ABCDE1234F"),
        ("What is your Aadhaar number?", "1234 5678 9012"),
        ("Passport Number", "Z1234567"),
        ("Date of Birth", "1999-05-10"),
        ("Provide your UAN number", "100123456789"),
    ]
    for question, answer in blocked_questions:
        resp = client.post(
            "/api/v1/vault/qa-rules",
            json={"question": question, "verified_answer": answer},
            headers=auth_headers,
        )
        assert resp.status_code == 422, f"Expected 422 for PII question: {question}"

    # Also block PAN/Aadhaar value patterns hidden inside innocent question names
    sneaky_pan = client.post(
        "/api/v1/vault/qa-rules",
        json={"question": "Employee Reference Code", "verified_answer": "ABCDE1234F"},
        headers=auth_headers,
    )
    assert sneaky_pan.status_code == 422

    # Valid technical Q&A rule succeeds and updates idempotently
    created = client.post(
        "/api/v1/vault/qa-rules",
        json={
            "question": "How many years of experience do you have in Apache Kafka?",
            "canonical_aliases": ["Years in Kafka", "Kafka exp"],
            "verified_answer": "3.0",
            "answer_type": "number",
            "portal_scope": "global",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    # Delete works
    assert client.delete(f"/api/v1/vault/qa-rules/{rule_id}", headers=auth_headers).status_code == 204
    assert client.get("/api/v1/vault/qa-rules", headers=auth_headers).json() == []


def test_taxonomy_500_plus_aliases_no_false_positives_and_indian_cities(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert len(SKILL_ALIASES) >= 500

    assert normalize_skill("k8s") == "Kubernetes"
    assert normalize_skill("postgres") == "PostgreSQL"
    assert normalize_skill("golang") == "Go"
    assert normalize_skill("ReactJS") == "React"

    # Must NOT produce false positives on ordinary English words containing 'go' or 'c'
    prose = "We are looking for a good cloud architect willing to go above and beyond with Python, C++, and Node.js."
    extracted = extract_skills_from_text(prose)
    assert "Python" in extracted
    assert "C++" in extracted
    assert "Node.js" in extracted
    assert "Go" not in extracted
    assert "C" not in extracted

    # Explicit Go (capitalized) and C, C++ DO match
    tech_line = "Required skills: Go, C, C++, FastAPI, PostgreSQL."
    tech_extracted = extract_skills_from_text(tech_line)
    assert {"Go", "C", "C++", "FastAPI", "PostgreSQL"}.issubset(set(tech_extracted))

    # City & hub normalization
    assert normalize_city("Bangalore, Karnataka") == "Bengaluru"
    assert normalize_city("Gurgaon Cyber City") == "Gurugram"
    assert extract_office_locality("Office in Bellandur, Bengaluru") == "Bellandur"
    assert cities_compatible("Delhi NCR", "Gurugram") is True
    assert cities_compatible("Bengaluru", "Pune") is False
    assert is_india_location("HITEC City, Hyderabad") is True
    assert is_india_location("San Francisco, CA") is False

    # API endpoint integration
    api_norm = client.post(
        "/api/v1/vault/taxonomy/normalize",
        json={
            "skills": ["k8s", "postgres", "drf"],
            "city": "Whitefield, Bangalore",
            "text": "Hiring backend dev for FastAPI and ReactJS in Whitefield.",
        },
        headers=auth_headers,
    )
    assert api_norm.status_code == 200
    data = api_norm.json()
    assert data["normalized_skills"] == ["Kubernetes", "PostgreSQL", "Django"]
    assert data["normalized_city"] == "Bengaluru"
    assert data["office_locality"] == "Whitefield"
    assert data["is_india"] is True


def test_deterministic_cover_template_renderer(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/vault/templates/render",
        json={
            "template": "Hi {{company}} team, applying for {{role_title}} with {{total_exp_years}} yrs exp in {{matched_top_3_skills}}. Notice: {{notice_period_days}}d ({{unknown_var}}).",
            "variables": {
                "company": "Razorpay",
                "role_title": "SDE II Backend",
                "matched_top_3_skills": "Python, FastAPI, Kafka",
                "total_exp_years": "4.5",
                "notice_period_days": "30",
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()
    assert "Hi Razorpay team, applying for SDE II Backend with 4.5 yrs exp in Python, FastAPI, Kafka." in result["rendered"]
    assert "{{unknown_var}}" in result["rendered"]
    assert result["unresolved_placeholders"] == ["unknown_var"]

