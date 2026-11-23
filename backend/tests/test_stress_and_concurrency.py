"""Backend Stress, Shared-PDF Refcounting, Snapshot Rotation, Idempotency & Gate 4 Boundary Tests."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings
from app.db.database import create_sqlite_snapshot
from app.db.models import FactVault, Job, JobResumeScore, JobSource, LearnedQARule
from app.pipeline.gate4_scorer import (
    _compute_tier,
    _evaluate_experience_fit,
    _evaluate_logistics,
)


def test_50_job_batch_stress_ingestion_and_fts_consistency(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_backend_pdf: Path,
) -> None:
    """Ingest 50 jobs (clean + mirrors + siblings + Gate-1 hidden) in one atomic batch and verify counts."""
    r_res = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Backend Core"},
        files={"file": ("Backend_Python_Go.pdf", sample_backend_pdf.read_bytes(), "application/pdf")},
    )
    assert r_res.status_code == 201

    jobs_payload = []
    # 30 distinct Backend active roles across 30 companies
    for i in range(30):
        jobs_payload.append(
            {
                "title": "SDE II Backend",
                "company_name": f"TechCorp{i}",
                "description_raw": (
                    f"Req ID: JR{1000 + i}\n"
                    f"Build Python, FastAPI, PostgreSQL, and Apache Kafka team-{i} services."
                ),
                "location_raw": "Bengaluru, India",
                "portal_name": "greenhouse",
                "external_job_id": f"tc-{i}",
                "job_url": f"https://boards.greenhouse.io/techcorp{i}/jobs/{i}",
            }
        )
    # 10 exact mirrors of TechCorp0..9 from LinkedIn (should merge -> repost_count == 1)
    for i in range(10):
        jobs_payload.append(
            {
                "title": "SDE 2 Backend",
                "company_name": f"TechCorp{i}",
                "description_raw": (
                    f"Req ID: JR{1000 + i}\n"
                    f"Build Python, FastAPI, PostgreSQL, and Apache Kafka team-{i} services."
                ),
                "location_raw": "Bangalore",
                "portal_name": "linkedin",
                "external_job_id": f"li-{i}",
                "job_url": f"https://www.linkedin.com/jobs/view/{9000 + i}",
            }
        )
    # 10 Gate-1 hidden Intern roles
    client.put(
        "/api/v1/vault",
        headers=auth_headers,
        json={"negative_keywords_json": ["Intern"]},
    )
    for i in range(10):
        jobs_payload.append(
            {
                "title": "Software Intern",
                "company_name": f"InternCorp{i}",
                "description_raw": "Internship in Python and SQL.",
                "location_raw": "Bengaluru",
                "portal_name": "naukri",
                "job_url": f"https://www.naukri.com/job/intern-{i}",
            }
        )

    r_batch = client.post("/api/v1/jobs/ingest", headers=auth_headers, json={"jobs": jobs_payload})
    assert r_batch.status_code == 201
    results = r_batch.json()
    assert len(results) == 50

    with Session(client.app.state.engine) as session:
        all_jobs = list(session.exec(select(Job)).all())
        all_sources = list(session.exec(select(JobSource)).all())
        all_scores = list(session.exec(select(JobResumeScore)).all())

        assert len(all_jobs) == 40  # 30 active + 10 hidden (10 mirrors merged!)
        assert len(all_sources) == 50
        assert len(all_scores) == 40

    active_q = client.get("/api/v1/jobs?limit=100", headers=auth_headers).json()
    assert active_q["total"] == 30
    hidden_q = client.get("/api/v1/jobs?only_hidden=true&limit=100", headers=auth_headers).json()
    assert hidden_q["total"] == 10


def test_shared_resume_pdf_reference_counting_on_delete(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_backend_pdf: Path,
) -> None:
    """Uploading identical PDF twice shares storage; deleting Track A keeps file alive for Track B."""
    pdf_bytes = sample_backend_pdf.read_bytes()
    resumes_dir = client.app.state.settings.resumes_dir

    r1 = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Track A"},
        files={"file": ("Backend_Python_Go.pdf", pdf_bytes, "application/pdf")},
    ).json()
    r2 = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Track B"},
        files={"file": ("Backend_Python_Go.pdf", pdf_bytes, "application/pdf")},
    ).json()

    assert len(list(resumes_dir.glob("*Backend_Python_Go.pdf"))) == 1

    # Delete Track A -> file MUST still exist for Track B
    assert client.delete(f"/api/v1/resumes/{r1['id']}", headers=auth_headers).status_code == 204
    assert len(list(resumes_dir.glob("*Backend_Python_Go.pdf"))) == 1
    assert client.get(f"/api/v1/resumes/{r2['id']}/file", headers=auth_headers).status_code == 200

    # Delete Track B -> unreferenced file unlinked from disk
    assert client.delete(f"/api/v1/resumes/{r2['id']}", headers=auth_headers).status_code == 204
    assert len(list(resumes_dir.glob("*Backend_Python_Go.pdf"))) == 0


def test_sqlite_snapshot_rotation_and_idempotent_qa_alias_merging(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    """Verify keep_last=2 snapshot rotation and idempotent Q&A alias merging."""
    backups_dir = tmp_path / "rot_backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    # Seed 3 older fake snapshots with monotonically earlier mtimes
    for idx in range(3):
        p = backups_dir / f"jobs_snapshot_20261120_00000{idx}.db"
        p.write_bytes(b"old-snap")
        os.utime(p, (1_700_000_000 + idx, 1_700_000_000 + idx))

    db_path = client.app.state.settings.db_path
    newest = create_sqlite_snapshot(db_path, backups_dir, keep_last=2)
    assert newest is not None and newest.exists()
    remaining = list(backups_dir.glob("jobs_snapshot_*.db"))
    assert len(remaining) == 2

    # Q&A rule upsert merges aliases without creating duplicate rows
    q1 = client.post(
        "/api/v1/vault/qa-rules",
        headers=auth_headers,
        json={
            "question": "  Are you willing to relocate? ",
            "canonical_aliases": ["Open to relocate"],
            "verified_answer": "Yes",
        },
    )
    assert q1.status_code == 201
    q2 = client.post(
        "/api/v1/vault/qa-rules",
        headers=auth_headers,
        json={
            "question": "are you   willing to relocate?",
            "canonical_aliases": ["Relocation OK"],
            "verified_answer": "Yes, to Bengaluru",
        },
    )
    assert q2.status_code == 201
    assert q2.json()["id"] == q1.json()["id"]
    assert q2.json()["canonical_aliases_json"] == ["open to relocate", "relocation ok"]
    assert q2.json()["verified_answer"] == "Yes, to Bengaluru"

    with Session(client.app.state.engine) as session:
        assert len(list(session.exec(select(LearnedQARule)).all())) == 1


def test_gate4_exact_boundary_math_exp_logistics_and_tiers() -> None:
    """Directly test Gate 4 helper boundary conditions across exp, logistics, and Tier S/A/B/C cutoffs."""
    cfg = Settings()

    # Experience fit: total = 4.0; lower_grace = 0.5; stretch = 1.5; upper_grace = 2.0
    v = FactVault(total_exp_years=4.0, willing_to_relocate=False, preferred_cities_json=["Bengaluru"], notice_period_days=30)
    assert _evaluate_experience_fit(Job(title="J", company_name="C", exp_min_years=4.5, exp_max_years=6.0), v, cfg) == "exact"
    assert _evaluate_experience_fit(Job(title="J", company_name="C", exp_min_years=5.0, exp_max_years=8.0), v, cfg) == "stretch"
    assert _evaluate_experience_fit(Job(title="J", company_name="C", exp_min_years=6.5, exp_max_years=9.0), v, cfg) == "under"
    assert _evaluate_experience_fit(Job(title="J", company_name="C", exp_min_years=None, exp_max_years=None), v, cfg) == "exact"

    # Logistics: city mismatch blocks unless relocate=True or Remote
    assert _evaluate_logistics(Job(title="J", company_name="C", normalized_city="Pune", work_mode="onsite"), v) is False
    assert _evaluate_logistics(Job(title="J", company_name="C", normalized_city="Pune", work_mode="remote"), v) is True
    assert _evaluate_logistics(Job(title="J", company_name="C", normalized_city="Bengaluru", max_notice_days=15), v) is False
    assert _evaluate_logistics(Job(title="J", company_name="C", normalized_city="Bengaluru", max_notice_days=30), v) is True

    # Tier cutoffs
    assert _compute_tier(True, True, [], [], 1.0, "exact", True, 95.0, cfg) == "C"  # 0 core lang match -> C
    assert _compute_tier(False, True, [], [], 1.0, "under", True, 95.0, cfg) == "C"  # under exp -> C
    assert _compute_tier(False, False, [], [], 1.0, "exact", True, 95.0, cfg) == "A"  # archetype mismatch prevents S -> A
    assert _compute_tier(False, True, [], [], 1.0, "exact", True, cfg.tier_s_coverage_pct, cfg) == "S"
    assert _compute_tier(False, True, [], ["Docker"], 1.0, "exact", True, cfg.tier_a_coverage_pct, cfg) == "A"
    assert _compute_tier(False, True, ["Go"], [], 0.65, "exact", True, cfg.tier_b_coverage_pct, cfg) == "B"

