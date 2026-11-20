"""Tests verifying externalized JSON rules/taxonomies and tunable Settings thresholds."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.config import Settings, ensure_data_dirs
from app.db.database import create_db_engine, init_db
from app.db.models import FactVault, Job, Resume, ResumeBullet
from app.pipeline.gate1_filters import evaluate_gate1
from app.pipeline.gate3_extractor import extract_job_signals
from app.pipeline.gate4_scorer import _compute_tier, score_job_against_resumes
from app.pipeline.orchestrator import RawJobInput, ingest_job
from app.resumes.embedder import vector_to_blob
from app.vault.taxonomy import CITY_CANONICAL_MAP, CORE_LANGUAGES, SKILL_ALIASES


def test_json_taxonomy_and_rules_files_loaded() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "app" / "data"
    assert (data_dir / "india_locations.json").exists()
    assert (data_dir / "skills_taxonomy.json").exists()
    assert (data_dir / "pipeline_rules.json").exists()

    assert len(SKILL_ALIASES) >= 500
    assert {"Python", "Java", "Go", "TypeScript"}.issubset(CORE_LANGUAGES)
    assert "Bengaluru" in CITY_CANONICAL_MAP
    assert "Remote (India)" in CITY_CANONICAL_MAP


def test_tunable_settings_control_gate1_and_gate4_without_code_edits() -> None:
    sig = extract_job_signals(
        title="Backend Engineer",
        company_name="Acme Corp",
        raw_description="Minimum 6 years experience in Python and FastAPI.",
        location_raw="Bengaluru",
    )
    vault = FactVault(id=1, total_exp_years=4.5)

    # Default buffer 2.0: 6.0 <= 4.5 + 2.0 (6.5) -> NOT hidden
    assert evaluate_gate1(sig, vault, exp_buffer_years=2.0).hidden_by_gate1 is False

    # Tighter buffer 1.0: 6.0 > 4.5 + 1.0 (5.5) -> hidden
    strict_res = evaluate_gate1(sig, vault, exp_buffer_years=1.0)
    assert strict_res.hidden_by_gate1 is True
    assert "experience floor" in strict_res.hidden_reason.lower()

    # Tier cutoff override via Settings
    default_cfg = Settings()
    assert default_cfg.tier_s_coverage_pct == 80.0
    assert (
        _compute_tier(
            has_zero_core_lang_match=False,
            archetype_ok=True,
            missing_primary=[],
            missing_secondary=[],
            primary_match_ratio=1.0,
            exp_fit="exact",
            logistics_ok=True,
            coverage_pct=85.0,
            cfg=default_cfg,
        )
        == "S"
    )

    strict_cfg = Settings(tier_s_coverage_pct=95.0, tier_a_coverage_pct=70.0)
    assert (
        _compute_tier(
            has_zero_core_lang_match=False,
            archetype_ok=True,
            missing_primary=[],
            missing_secondary=[],
            primary_match_ratio=1.0,
            exp_fit="exact",
            logistics_ok=True,
            coverage_pct=85.0,
            cfg=strict_cfg,
        )
        == "A"
    )


def test_orchestrator_respects_custom_settings_thresholds(
    tmp_path: Path,
    sample_backend_pdf: Path,
) -> None:
    from tests.conftest import DeterministicTestEmbedder

    embedder = DeterministicTestEmbedder()
    cfg = Settings(
        data_dir=tmp_path / "data",
        semantic_threshold=0.99,  # Unrealistically strict -> should drop bullet coverage to 0% -> Tier C
        freshness_hours=12,
    )
    ensure_data_dirs(cfg)
    engine = create_db_engine(cfg.db_path)
    init_db(engine)

    with Session(engine) as session:
        session.add(FactVault(id=1, total_exp_years=4.5, notice_period_days=30))
        resume = Resume(
            track_name="Backend Track",
            pdf_filename="Backend_Python_Go.pdf",
            pdf_path=str(sample_backend_pdf),
            pdf_sha256="abc123",
            target_titles_json=["Backend Engineer"],
            track_skills_json=["Python", "FastAPI", "Microservices"],
        )
        session.add(resume)
        session.flush()
        vec = embedder.embed_texts(["Built FastAPI services"])[0]
        session.add(
            ResumeBullet(
                resume_id=int(resume.id),
                section_name="experience",
                bullet_order=0,
                bullet_text="Built FastAPI services",
                extracted_skills_json=["FastAPI"],
                embedding_blob=vector_to_blob(vec),
            )
        )
        session.commit()

        res = ingest_job(
            session=session,
            raw=RawJobInput(
                title="Backend Engineer",
                company_name="Razorpay",
                description_raw="Build scalable Python and FastAPI microservices for payments.",
                location_raw="Bengaluru",
                portal_name="greenhouse",
                job_url="https://boards.greenhouse.io/razorpay/jobs/1",
            ),
            embedder=embedder,
            settings=cfg,
        )
        assert res.winning_tier == "C"

        # Now relax threshold -> bullet matches cleanly and tier rises
        relaxed_cfg = Settings(data_dir=tmp_path / "data", semantic_threshold=0.10)
        job = session.get(Job, res.job_id)
        scores = score_job_against_resumes(
            session=session,
            job=job,
            requirement_lines=["Build scalable Python and FastAPI microservices for payments."],
            vault=session.get(FactVault, 1),
            embedder=embedder,
            settings=relaxed_cfg,
        )
        assert scores[0].tier in {"S", "A"}
