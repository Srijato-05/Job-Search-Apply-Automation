"""API routes for 5-Gate job ingestion, faceted filtering, FTS5 search, and JD diffing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.deps import get_embedder, get_session, get_settings
from app.config import Settings
from app.db.database import search_jobs_fts
from app.db.models import Job, JobResumeScore, JobSource, Resume, utc_now
from app.pipeline.gate2_identity import compute_jd_diff
from app.pipeline.orchestrator import RawJobInput, ingest_job, rescore_active_jobs
from app.resumes.embedder import EmbedderProtocol
from app.schemas.jobs import (
    JobCardResponse,
    JobDetailResponse,
    JobDiffResponse,
    JobIngestBatchRequest,
    JobIngestItem,
    JobIngestResultResponse,
    JobListResponse,
    JobResumeScoreDetail,
    JobSourceResponse,
    JobStatusUpdate,
    SiblingJobSummary,
    WinningScoreSummary,
)
from app.vault.taxonomy import cities_compatible

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TIER_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3}


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _to_ingest_input(item: JobIngestItem) -> RawJobInput:
    return RawJobInput(
        title=item.title,
        company_name=item.company_name,
        description_raw=item.description_raw,
        location_raw=item.location_raw,
        portal_name=item.portal_name,
        external_job_id=item.external_job_id,
        job_url=item.job_url,
        apply_url=item.apply_url,
        posted_at=item.posted_at,
        portal_metadata=item.portal_metadata,
    )


def _build_card(
    job: Job,
    scores: list[JobResumeScore],
    resumes_by_id: dict[int, Resume],
    sources: list[JobSource],
) -> JobCardResponse:
    winner = next((s for s in scores if s.is_winning_resume), None)
    winning_dto: Optional[WinningScoreSummary] = None
    if winner is not None:
        res = resumes_by_id.get(int(winner.resume_id))
        winning_dto = WinningScoreSummary(
            resume_id=int(winner.resume_id),
            track_name=res.track_name if res else "",
            pdf_filename=res.pdf_filename if res else "",
            tier=winner.tier,
            semantic_bullet_coverage_pct=winner.semantic_bullet_coverage_pct,
            matched_primary_skills_json=winner.matched_primary_skills_json,
            missing_primary_skills_json=winner.missing_primary_skills_json,
            missing_secondary_skills_json=winner.missing_secondary_skills_json,
            cross_resume_alerts_count=len(winner.cross_resume_alerts_json),
        )

    notice_compat = bool(job.portal_signals_json.get("notice_compatible", True))
    return JobCardResponse(
        id=int(job.id),
        title=job.title,
        company_name=job.company_name,
        company_slug=job.company_slug,
        role_subtag=job.role_subtag,
        req_id=job.req_id,
        normalized_city=job.normalized_city,
        office_locality=job.office_locality,
        work_mode=job.work_mode,
        exp_min_years=job.exp_min_years,
        exp_max_years=job.exp_max_years,
        salary_min_lpa=job.salary_min_lpa,
        salary_max_lpa=job.salary_max_lpa,
        max_notice_days=job.max_notice_days,
        notice_compatible=notice_compat,
        apply_friction=job.apply_friction,
        employer_type=job.employer_type,
        hidden_by_gate1=job.hidden_by_gate1,
        hidden_reason=job.hidden_reason,
        status=job.status,
        parent_sibling_job_id=job.parent_sibling_job_id,
        repost_count=job.repost_count,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        last_reposted_at=job.last_reposted_at,
        winning_score=winning_dto,
        sources=[JobSourceResponse.model_validate(src) for src in sources],
    )


@router.post("/ingest", response_model=list[JobIngestResultResponse], status_code=status.HTTP_201_CREATED)
def ingest_jobs(
    payload: Union[JobIngestItem, JobIngestBatchRequest],
    session: Session = Depends(get_session),
    embedder: EmbedderProtocol = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
) -> list[JobIngestResultResponse]:
    """Ingest one or more jobs through the 5-Gate pipeline."""
    items = payload.jobs if isinstance(payload, JobIngestBatchRequest) else [payload]
    results: list[JobIngestResultResponse] = []
    for item in items:
        res = ingest_job(
            session=session,
            raw=_to_ingest_input(item),
            embedder=embedder,
            settings=settings,
        )
        results.append(
            JobIngestResultResponse(
                job_id=res.job_id,
                action=res.action,
                hidden_by_gate1=res.hidden_by_gate1,
                hidden_reason=res.hidden_reason,
                winning_tier=res.winning_tier,
                winning_resume_id=res.winning_resume_id,
            )
        )
    return results


@router.get("", response_model=JobListResponse)
def list_jobs(
    tier: Optional[str] = Query(default=None),
    resume_id: Optional[int] = Query(default=None),
    fresh_6h: bool = Query(default=False),
    missing_max: Optional[int] = Query(default=None, ge=0),
    friction: Optional[str] = Query(default=None),
    employer_type: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    notice_compatible: Optional[bool] = Query(default=None),
    include_hidden: bool = Query(default=False),
    only_hidden: bool = Query(default=False),
    job_status: str = Query(default="active", alias="status"),
    fts_query: Optional[str] = Query(default=None),
    sort: str = Query(default="tier"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JobListResponse:
    """Query jobs with Gate 5 faceted filters and offline SQLite FTS5 boolean search."""
    stmt = select(Job)
    if job_status != "all":
        stmt = stmt.where(Job.status == job_status)

    if only_hidden:
        stmt = stmt.where(Job.hidden_by_gate1.is_(True))
    elif not include_hidden:
        stmt = stmt.where(Job.hidden_by_gate1.is_(False))

    if friction:
        stmt = stmt.where(Job.apply_friction == friction)
    if employer_type:
        stmt = stmt.where(Job.employer_type == employer_type)

    if fts_query and fts_query.strip():
        matching_ids = search_jobs_fts(session, fts_query, limit=500)
        if not matching_ids:
            return JobListResponse(total=0, items=[])
        stmt = stmt.where(Job.id.in_(matching_ids))

    jobs = list(session.exec(stmt).all())
    if not jobs:
        return JobListResponse(total=0, items=[])

    job_ids = [int(j.id) for j in jobs]
    all_scores = list(session.exec(select(JobResumeScore).where(JobResumeScore.job_id.in_(job_ids))).all())
    all_sources = list(session.exec(select(JobSource).where(JobSource.job_id.in_(job_ids))).all())
    resumes_by_id = {int(r.id): r for r in session.exec(select(Resume)).all()}

    scores_by_job: dict[int, list[JobResumeScore]] = {}
    for sc in all_scores:
        scores_by_job.setdefault(int(sc.job_id), []).append(sc)

    sources_by_job: dict[int, list[JobSource]] = {}
    for src in all_sources:
        sources_by_job.setdefault(int(src.job_id), []).append(src)

    allowed_tiers = (
        {t.strip().upper() for t in tier.split(",") if t.strip()} if tier else None
    )
    cutoff_6h = utc_now() - timedelta(hours=settings.freshness_hours)

    cards: list[JobCardResponse] = []
    for job in jobs:
        if city and not cities_compatible(job.normalized_city, city):
            continue

        job_notice_ok = bool(job.portal_signals_json.get("notice_compatible", True))
        if notice_compatible is not None and job_notice_ok != notice_compatible:
            continue

        if fresh_6h:
            ref_dt = _as_utc(job.posted_at) or _as_utc(job.first_seen_at)
            if ref_dt is None or ref_dt < cutoff_6h:
                continue

        card = _build_card(
            job=job,
            scores=scores_by_job.get(int(job.id), []),
            resumes_by_id=resumes_by_id,
            sources=sources_by_job.get(int(job.id), []),
        )

        if allowed_tiers is not None:
            if not card.winning_score or card.winning_score.tier not in allowed_tiers:
                continue
        if resume_id is not None:
            if not card.winning_score or card.winning_score.resume_id != resume_id:
                continue
        if missing_max is not None:
            if not card.winning_score or len(card.winning_score.missing_primary_skills_json) > missing_max:
                continue

        cards.append(card)

    if sort == "freshness":
        cards.sort(
            key=lambda c: (_as_utc(c.posted_at) or _as_utc(c.first_seen_at) or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
    elif sort == "semantic":
        cards.sort(
            key=lambda c: (
                c.winning_score.semantic_bullet_coverage_pct if c.winning_score else -1.0,
                -(_TIER_ORDER.get(c.winning_score.tier, 99) if c.winning_score else 99),
            ),
            reverse=True,
        )
    else:
        cards.sort(
            key=lambda c: (
                _TIER_ORDER.get(c.winning_score.tier, 99) if c.winning_score else 99,
                -(c.winning_score.semantic_bullet_coverage_pct if c.winning_score else 0.0),
                -int((_as_utc(c.posted_at) or _as_utc(c.first_seen_at) or datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
            )
        )

    total = len(cards)
    paged = cards[offset : offset + limit]
    return JobListResponse(total=total, items=paged)


@router.post("/rescore")
def rescore_all_active_jobs(
    session: Session = Depends(get_session),
    embedder: EmbedderProtocol = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
) -> dict[str, int]:
    """Re-run Gate 4 Option 1+3 evaluation across all active jobs."""
    count = rescore_active_jobs(session=session, embedder=embedder, settings=settings)
    return {"rescored_count": count}


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job_detail(
    job_id: int,
    session: Session = Depends(get_session),
) -> JobDetailResponse:
    """Retrieve complete job metadata, all resume proof tables, and sibling links."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    scores = list(
        session.exec(select(JobResumeScore).where(JobResumeScore.job_id == job_id)).all()
    )
    sources = list(session.exec(select(JobSource).where(JobSource.job_id == job_id)).all())
    resumes_by_id = {int(r.id): r for r in session.exec(select(Resume)).all()}

    card = _build_card(job=job, scores=scores, resumes_by_id=resumes_by_id, sources=sources)

    all_scores_dto = [
        JobResumeScoreDetail(
            resume_id=int(sc.resume_id),
            track_name=resumes_by_id[int(sc.resume_id)].track_name if int(sc.resume_id) in resumes_by_id else "",
            pdf_filename=resumes_by_id[int(sc.resume_id)].pdf_filename if int(sc.resume_id) in resumes_by_id else "",
            tier=sc.tier,
            is_winning_resume=sc.is_winning_resume,
            semantic_bullet_coverage_pct=sc.semantic_bullet_coverage_pct,
            matched_primary_skills_json=sc.matched_primary_skills_json,
            missing_primary_skills_json=sc.missing_primary_skills_json,
            missing_secondary_skills_json=sc.missing_secondary_skills_json,
            bullet_proof_json=sc.bullet_proof_json,
            cross_resume_alerts_json=sc.cross_resume_alerts_json,
            scored_at=sc.scored_at,
        )
        for sc in sorted(scores, key=lambda x: (not x.is_winning_resume, _TIER_ORDER.get(x.tier, 9)))
    ]

    anchor_id = job.parent_sibling_job_id or job_id
    sibling_rows = session.exec(
        select(Job).where(
            Job.company_slug == job.company_slug,
            Job.id != job_id,
            (Job.id == anchor_id) | (Job.parent_sibling_job_id == anchor_id) | (Job.parent_sibling_job_id == job_id),
        )
    ).all()
    siblings = [
        SiblingJobSummary(
            id=int(s.id),
            title=s.title,
            role_subtag=s.role_subtag,
            req_id=s.req_id,
            normalized_city=s.normalized_city,
            status=s.status,
        )
        for s in sibling_rows
    ]

    return JobDetailResponse(
        **card.model_dump(),
        description_raw=job.description_raw,
        boilerplate_stripped_text=job.boilerplate_stripped_text,
        primary_skills_json=job.primary_skills_json,
        secondary_skills_json=job.secondary_skills_json,
        portal_signals_json=job.portal_signals_json,
        all_scores=all_scores_dto,
        sibling_jobs=siblings,
    )


@router.get("/{job_id}/diff/{sibling_id}", response_model=JobDiffResponse)
def diff_sibling_jobs(
    job_id: int,
    sibling_id: int,
    session: Session = Depends(get_session),
) -> JobDiffResponse:
    """Compute a Side-by-Side requirement & skill diff between two jobs."""
    job_a = session.get(Job, job_id)
    job_b = session.get(Job, sibling_id)
    if job_a is None or job_b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found for diff")
    return JobDiffResponse(**compute_jd_diff(job_a, job_b))


@router.patch("/{job_id}/status", response_model=JobCardResponse)
def update_job_status(
    job_id: int,
    payload: JobStatusUpdate,
    session: Session = Depends(get_session),
) -> JobCardResponse:
    """Manually close/reopen a job or unhide a Gate 1 filtered record."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if payload.status is not None:
        job.status = payload.status
    if payload.hidden_by_gate1 is not None:
        job.hidden_by_gate1 = payload.hidden_by_gate1
        if payload.hidden_by_gate1 is False and payload.hidden_reason is None:
            job.hidden_reason = None
    if payload.hidden_reason is not None:
        job.hidden_reason = payload.hidden_reason

    session.add(job)
    session.commit()
    session.refresh(job)

    scores = list(session.exec(select(JobResumeScore).where(JobResumeScore.job_id == job_id)).all())
    sources = list(session.exec(select(JobSource).where(JobSource.job_id == job_id)).all())
    resumes_by_id = {int(r.id): r for r in session.exec(select(Resume)).all()}
    return _build_card(job=job, scores=scores, resumes_by_id=resumes_by_id, sources=sources)

