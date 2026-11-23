"""Deep unit coverage for embedder math, templates, closed-job pruner, location filter & config."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.collectors.location_filter import is_india_location
from app.collectors.pruner import prune_closed_ats_jobs
from app.config import Settings, ensure_data_dirs, get_or_create_local_token
from app.db.models import Job, JobSource
from app.resumes.embedder import (
    blob_to_vector,
    cosine_similarity,
    l2_normalize_matrix,
    vector_to_blob,
)
from app.vault.templates import ALLOWED_TEMPLATE_VARIABLES, render_cover_template


def test_embedder_vector_math_blob_roundtrip_and_zero_vector_safety() -> None:
    """Verify BLOB serialization precision, NaN-free zero normalization, and cosine similarities."""
    mat = np.array([[3.0, 4.0], [0.0, 0.0]], dtype=np.float32)
    normed = l2_normalize_matrix(mat)
    assert normed.dtype == np.float32
    assert not np.isnan(normed).any()
    assert not np.isinf(normed).any()
    assert abs(float(np.linalg.norm(normed[0])) - 1.0) < 1e-6
    assert np.allclose(normed[1], np.zeros(2, dtype=np.float32))

    # Empty matrix round-trip
    empty = np.zeros((0, 384), dtype=np.float32)
    assert l2_normalize_matrix(empty).shape == (0, 384)

    # BLOB serialization & similarity bounds
    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    v_opp = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
    v_zero = np.array([0.0, 0.0, 0.0], dtype=np.float32)

    restored = blob_to_vector(vector_to_blob(v1))
    assert np.allclose(restored, v1)
    assert abs(cosine_similarity(v1, restored) - 1.0) < 1e-6
    assert abs(cosine_similarity(v1, v2)) < 1e-6
    assert abs(cosine_similarity(v1, v_opp) + 1.0) < 1e-6
    assert cosine_similarity(v1, v_zero) == 0.0


def test_cover_template_renderer_edge_cases() -> None:
    """Verify whitelisting, blank variable reporting, and special characters like $ and \\."""
    tpl = (
        "Hi {{ company }} at {{current_city}} — {{ company }} role {{role_title}} "
        "({{secret_field}} / {{notice_period_days}})."
    )
    res = render_cover_template(
        tpl,
        {
            "company": "FinTech \\ Corp $100",
            "role_title": "SDE II",
            "current_city": "Bengaluru",
            "notice_period_days": "   ",  # blank must be reported unresolved
            "secret_field": "SHOULD_NOT_INTERPOLATE",
        },
    )
    assert "FinTech \\ Corp $100" in res["rendered"]
    assert res["rendered"].count("FinTech \\ Corp $100") == 2
    assert "{{secret_field}}" in res["rendered"]
    assert res["unresolved_placeholders"] == ["secret_field", "notice_period_days"]
    assert render_cover_template("", {}) == {"rendered": "", "unresolved_placeholders": []}
    assert "company" in ALLOWED_TEMPLATE_VARIABLES


def test_pruner_empty_set_safety_url_fallback_and_closed_idempotency() -> None:
    """Pruner must never wipe active jobs on empty input and must match via job_url when external_job_id is None."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        j_url_only = Job(title="SDE I", company_name="Acme", company_slug="acme", status="active")
        j_already_closed = Job(title="Old Role", company_name="Acme", company_slug="acme", status="closed")
        j_vanished = Job(title="Vanished Role", company_name="Acme", company_slug="acme", status="active")
        session.add_all([j_url_only, j_already_closed, j_vanished])
        session.commit()
        session.refresh(j_url_only)
        session.refresh(j_vanished)

        session.add(JobSource(job_id=j_url_only.id, portal_name="lever", external_job_id=None, job_url="https://jobs.lever.co/acme/1"))
        session.add(JobSource(job_id=j_vanished.id, portal_name="lever", external_job_id=None, job_url="https://jobs.lever.co/acme/2"))
        session.commit()

        # Empty active sets abort safely -> 0 closed
        assert prune_closed_ats_jobs(session, "acme", set(), set()) == 0
        session.refresh(j_url_only)
        assert j_url_only.status == "active"

        # Keeping only acme/1 closes acme/2 while leaving acme/1 active & skipping already-closed row
        closed = prune_closed_ats_jobs(session, "acme", set(), {"https://jobs.lever.co/acme/1"})
        assert closed == 1
        session.refresh(j_url_only)
        session.refresh(j_vanished)
        assert j_url_only.status == "active"
        assert j_vanished.status == "closed"


def test_location_filter_edge_cases_and_config_token_idempotency(tmp_path: Path) -> None:
    """Verify remote/pan-India/foreign edge cases and persistent local token + Settings list properties."""
    assert is_india_location("Remote - India")[0] is True
    assert is_india_location("Pan India")[0] is True
    assert is_india_location("Bengaluru / Hybrid") == (True, "Bengaluru")
    assert is_india_location("Hyderabad, Telangana") == (True, "Hyderabad")
    assert is_india_location("Remote - US")[0] is False
    assert is_india_location("Singapore")[0] is False

    data_dir = tmp_path / "app_data"
    cfg = Settings(
        data_dir=data_dir,
        allowed_cors_origins="http://localhost:5173, http://127.0.0.1:8000, ",
        jobspy_default_sites="Naukri, Glassdoor, LinkedIn ",
    )
    ensure_data_dirs(cfg)
    assert cfg.resumes_dir.exists() and cfg.backups_dir.exists()
    assert cfg.cors_origins_list == ["http://127.0.0.1:8000", "http://localhost:5173"]
    assert cfg.jobspy_sites_list == ["naukri", "glassdoor", "linkedin"]

    tok1 = get_or_create_local_token(data_dir)
    tok2 = get_or_create_local_token(data_dir)
    assert len(tok1) >= 20
    assert tok1 == tok2

