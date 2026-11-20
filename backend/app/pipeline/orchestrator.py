"""Orchestrator running Jobs atomically through Gates 1 -> 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlmodel import Session, select

from app.config import Settings
from app.db.models import (
    Company,
    FactVault,
    Job,
    JobResumeScore,
    JobSource,
    utc_now,
)
from app.pipeline.gate1_filters import evaluate_gate1
from app.pipeline.gate2_identity import (
    compute_description_hash,
    compute_simhash64,
    resolve_job_identity,
)
from app.pipeline.gate3_extractor import extract_job_signals, extract_requirement_lines
from app.pipeline.gate4_scorer import score_job_against_resumes
from app.resumes.embedder import EmbedderProtocol, vector_to_blob


@dataclass
class RawJobInput:
    """Normalized raw input passed from collectors, extension harvester, or API ingest."""

    title: str
    company_name: str
    description_raw: str
    location_raw: str = ""
    portal_name: str = "manual"
    external_job_id: Optional[str] = None
    job_url: str = ""
    apply_url: str = ""
    posted_at: Optional[datetime] = None
    portal_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    """Summary of what happened when a job entered the 5-Gate pipeline."""

    job_id: int
    action: str
    hidden_by_gate1: bool
    hidden_reason: Optional[str]
    winning_tier: Optional[str]
    winning_resume_id: Optional[int]


def _get_or_create_vault(session: Session) -> FactVault:
    vault = session.get(FactVault, 1)
    if vault is None:
        vault = FactVault(id=1)
        session.add(vault)
        session.flush()
    return vault


def _winning_summary(session: Session, job_id: int) -> tuple[Optional[str], Optional[int]]:
    winner = session.exec(
        select(JobResumeScore).where(
            JobResumeScore.job_id == job_id,
            JobResumeScore.is_winning_resume.is_(True),
        )
    ).first()
    if winner is None:
        return None, None
    return winner.tier, int(winner.resume_id)


def ingest_job(
    session: Session,
    raw: RawJobInput,
    embedder: EmbedderProtocol,
    settings: Optional[Settings] = None,
    semantic_threshold: Optional[float] = None,
) -> IngestionResult:
    """Run a single raw job through Gates 1-4 and persist atomically."""
    cfg = settings or Settings()
    vault = _get_or_create_vault(session)
    signals = extract_job_signals(
        title=raw.title,
        company_name=raw.company_name,
        raw_description=raw.description_raw,
        location_raw=raw.location_raw,
        job_url=raw.job_url,
        apply_url=raw.apply_url,
        portal_name=raw.portal_name,
        portal_metadata=raw.portal_metadata,
    )

    embed_input = (signals.boilerplate_stripped_text or signals.raw_title)[: cfg.jd_embed_max_chars]
    jd_vector = embedder.embed_texts([embed_input])[0]

    company_row = session.exec(
        select(Company).where(Company.slug == signals.company_slug)
    ).first()
    company_blacklisted = bool(company_row.is_blacklisted) if company_row is not None else False

    gate1 = evaluate_gate1(
        signals,
        vault,
        company_blacklisted=company_blacklisted,
        exp_buffer_years=cfg.gate1_exp_buffer_years,
    )
    identity = resolve_job_identity(
        session=session,
        signals=signals,
        jd_vector=jd_vector,
        portal_name=raw.portal_name,
        external_job_id=raw.external_job_id,
        job_url=raw.job_url,
        similarity_threshold=cfg.dedup_similarity_threshold,
        stack_overlap_threshold=cfg.dedup_stack_overlap_threshold,
    )

    now = utc_now()

    if identity.action == "existing_source" and identity.target_job is not None:
        target = identity.target_job
        session.commit()
        win_tier, win_resume_id = _winning_summary(session, int(target.id))
        return IngestionResult(
            job_id=int(target.id),
            action="existing_source",
            hidden_by_gate1=target.hidden_by_gate1,
            hidden_reason=target.hidden_reason,
            winning_tier=win_tier,
            winning_resume_id=win_resume_id,
        )

    if identity.action == "merge_same_role" and identity.target_job is not None:
        target = identity.target_job
        target.repost_count += 1
        target.last_reposted_at = now
        if raw.portal_metadata:
            merged_signals = dict(target.portal_signals_json)
            merged_signals.update(raw.portal_metadata)
            target.portal_signals_json = merged_signals
        session.add(target)
        session.add(
            JobSource(
                job_id=int(target.id),
                portal_name=raw.portal_name,
                external_job_id=raw.external_job_id,
                job_url=raw.job_url,
                apply_url=raw.apply_url or raw.job_url,
                seen_at=now,
            )
        )
        session.commit()
        win_tier, win_resume_id = _winning_summary(session, int(target.id))
        return IngestionResult(
            job_id=int(target.id),
            action="merge_same_role",
            hidden_by_gate1=target.hidden_by_gate1,
            hidden_reason=target.hidden_reason,
            winning_tier=win_tier,
            winning_resume_id=win_resume_id,
        )

    portal_signals = dict(raw.portal_metadata)
    portal_signals["notice_compatible"] = gate1.notice_compatible

    job = Job(
        title=signals.raw_title,
        company_name=signals.company_name,
        company_slug=signals.company_slug,
        normalized_title=signals.normalized_title,
        role_subtag=signals.role_subtag,
        req_id=signals.req_id,
        normalized_city=signals.normalized_city,
        office_locality=signals.office_locality,
        work_mode=signals.work_mode,
        exp_min_years=signals.exp_min_years,
        exp_max_years=signals.exp_max_years,
        salary_min_lpa=signals.salary_min_lpa,
        salary_max_lpa=signals.salary_max_lpa,
        max_notice_days=signals.max_notice_days,
        description_raw=raw.description_raw,
        boilerplate_stripped_text=signals.boilerplate_stripped_text,
        description_hash=compute_description_hash(signals.boilerplate_stripped_text),
        simhash_64=compute_simhash64(signals.boilerplate_stripped_text),
        jd_embedding_blob=vector_to_blob(jd_vector),
        primary_skills_json=signals.primary_skills,
        secondary_skills_json=signals.secondary_skills,
        apply_friction=signals.apply_friction,
        employer_type=signals.employer_type,
        hidden_by_gate1=gate1.hidden_by_gate1,
        hidden_reason=gate1.hidden_reason,
        status="active",
        parent_sibling_job_id=identity.sibling_parent_id,
        portal_signals_json=portal_signals,
        posted_at=raw.posted_at,
        first_seen_at=now,
        last_reposted_at=now,
        repost_count=0,
    )
    session.add(job)
    session.flush()

    session.add(
        JobSource(
            job_id=int(job.id),
            portal_name=raw.portal_name,
            external_job_id=raw.external_job_id,
            job_url=raw.job_url,
            apply_url=raw.apply_url or raw.job_url,
            seen_at=now,
        )
    )

    scores = score_job_against_resumes(
        session=session,
        job=job,
        requirement_lines=signals.requirement_lines,
        vault=vault,
        embedder=embedder,
        settings=cfg,
        semantic_threshold=semantic_threshold,
    )
    session.commit()

    winner = next((s for s in scores if s.is_winning_resume), None)
    return IngestionResult(
        job_id=int(job.id),
        action=identity.action,
        hidden_by_gate1=job.hidden_by_gate1,
        hidden_reason=job.hidden_reason,
        winning_tier=winner.tier if winner else None,
        winning_resume_id=int(winner.resume_id) if winner else None,
    )


def rescore_active_jobs(
    session: Session,
    embedder: EmbedderProtocol,
    settings: Optional[Settings] = None,
    semantic_threshold: Optional[float] = None,
) -> int:
    """Re-evaluate all active jobs against the current resumes and Fact Vault."""
    cfg = settings or Settings()
    vault = _get_or_create_vault(session)
    jobs = list(session.exec(select(Job).where(Job.status == "active")).all())
    for job in jobs:
        req_lines = extract_requirement_lines(job.boilerplate_stripped_text or job.description_raw)
        score_job_against_resumes(
            session=session,
            job=job,
            requirement_lines=req_lines,
            vault=vault,
            embedder=embedder,
            settings=cfg,
            semantic_threshold=semantic_threshold,
        )
    session.commit()
    return len(jobs)

