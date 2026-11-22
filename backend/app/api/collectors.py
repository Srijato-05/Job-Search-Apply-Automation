"""Collector API endpoints for on-demand execution, telemetry runs, and source health."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlmodel import Session, select

from app.api.deps import get_embedder, get_engine, get_session, get_settings
from app.collectors.manager import CollectionProgress, CollectorManager
from app.config import Settings
from app.db.models import CollectorRun, Company, utc_now
from app.resumes.embedder import EmbedderProtocol
from app.schemas.collectors import (
    CollectorHealthResponse,
    CollectorProgressResponse,
    CollectorRunRequest,
    CollectorRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collectors", tags=["Collectors"])


@router.post("/run", response_model=list[CollectorRunResponse])
async def trigger_collector_run(
    payload: CollectorRunRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    engine=Depends(get_engine),
    settings: Settings = Depends(get_settings),
    embedder: EmbedderProtocol = Depends(get_embedder),
    background: bool = Query(default=False, description="Run in background asynchronously if True"),
) -> list[CollectorRunResponse]:
    """Manually initiate collection across 'all', 'ats', 'jobspy', or a specific company slug."""
    manager = CollectorManager(settings=settings)
    target = payload.source.strip().lower()
    progress: Optional[CollectionProgress] = getattr(request.app.state, "collection_progress", None)
    lock: Optional[asyncio.Lock] = getattr(request.app.state, "collection_lock", None)

    if (progress is not None and progress.running) or (lock is not None and lock.locked()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A collection sweep is already in progress.",
        )

    if background:
        if progress is not None:
            progress.begin(target=target, total=0, phase="queued")

        # Reuse request.app.state.engine (never create a duplicate SQLAlchemy engine)
        async def _run_bg():
            lock_ctx = lock if lock is not None else nullcontext()
            try:
                async with lock_ctx:
                    with Session(engine) as bg_session:
                        if target in ("all", "ats"):
                            await manager.collect_all_watched(
                                bg_session,
                                embedder,
                                force=payload.force,
                                force_refresh_details=payload.force_refresh_details,
                                progress=progress,
                            )
                        if target in ("all", "jobspy"):
                            await manager.jobspy.run(
                                bg_session,
                                embedder,
                                hours_old=payload.hours_old,
                                progress=progress,
                            )
            finally:
                if progress is not None and progress.running:
                    progress.finish()

        background_tasks.add_task(_run_bg)
        return [
            CollectorRunResponse(
                source_name=f"collector_task:{target}",
                status="started_in_background",
                started_at=utc_now(),
            )
        ]

    # Synchronous execution
    results: list[CollectorRunResponse] = []
    lock_ctx = lock if lock is not None else nullcontext()

    async with lock_ctx:
        if target in ("all", "ats"):
            ats_results = await manager.collect_all_watched(
                session,
                embedder,
                force=payload.force,
                force_refresh_details=payload.force_refresh_details,
                progress=progress,
            )
            for r in ats_results:
                results.append(
                    CollectorRunResponse(
                        source_name="ats_batch",
                        status=r.status,
                        fetched_count=r.fetched_count,
                        new_count=r.new_count,
                        closed_count=r.closed_count,
                        cooldown_until=r.cooldown_until,
                        error_message=r.error_message,
                        started_at=utc_now(),
                    )
                )

        if target in ("all", "jobspy"):
            jobspy_res = await manager.jobspy.run(
                session,
                embedder,
                hours_old=payload.hours_old,
                progress=progress,
            )
            results.append(
                CollectorRunResponse(
                    source_name="jobspy",
                    status=jobspy_res.status,
                    fetched_count=jobspy_res.fetched_count,
                    new_count=jobspy_res.new_count,
                    closed_count=jobspy_res.closed_count,
                    cooldown_until=jobspy_res.cooldown_until,
                    error_message=jobspy_res.error_message,
                    started_at=utc_now(),
                )
            )

        # Specific company slug target
        if target not in ("all", "ats", "jobspy"):
            company = session.exec(select(Company).where(Company.slug == target)).first()
            if not company:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Company with slug '{target}' not found")

            comp_res = await manager.collect_company(session, embedder, company, force=payload.force)
            results.append(
                CollectorRunResponse(
                    source_name=f"ats:{company.slug}",
                    company_slug=company.slug,
                    status=comp_res.status,
                    fetched_count=comp_res.fetched_count,
                    new_count=comp_res.new_count,
                    closed_count=comp_res.closed_count,
                    cooldown_until=comp_res.cooldown_until,
                    error_message=comp_res.error_message,
                    started_at=utc_now(),
                )
            )

    return results


@router.get("/progress", response_model=CollectorProgressResponse)
def get_collection_progress(request: Request) -> CollectorProgressResponse:
    """Return live progress state for an in-flight or recently completed collection run."""
    progress: Optional[CollectionProgress] = getattr(request.app.state, "collection_progress", None)
    if progress is None:
        return CollectorProgressResponse()
    return progress.snapshot()


@router.get("/health", response_model=CollectorHealthResponse)
def get_source_health(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CollectorHealthResponse:
    """Retrieve operational status, cooldown countdowns, and run stats across all sources."""
    manager = CollectorManager(settings=settings)
    return manager.get_health_overview(session)


@router.get("/runs", response_model=list[CollectorRunResponse])
def get_recent_runs(
    session: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
    source: Optional[str] = Query(default=None),
) -> list[CollectorRun]:
    """Retrieve historical collector telemetry runs."""
    stmt = select(CollectorRun)
    if source:
        stmt = stmt.where(CollectorRun.source_name == source)

    stmt = stmt.order_by(CollectorRun.id.desc()).limit(limit)  # type: ignore[attr-defined]
    return list(session.exec(stmt).all())

