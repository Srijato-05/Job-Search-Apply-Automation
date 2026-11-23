"""Application Mini-CRM endpoints: Draft vs. Submitted tracking, Offline Snapshots & Cooldowns."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.deps import get_session, get_settings
from app.applications.service import (
    VALID_STAGES,
    build_application_response,
    get_company_cooldown_status,
    mark_application_submitted,
    start_or_resume_draft,
    update_application,
)
from app.config import Settings
from app.db.models import Application
from app.schemas.applications import (
    ApplicationResponse,
    ApplicationStartDraftRequest,
    ApplicationSubmitRequest,
    ApplicationUpdateRequest,
    CooldownStatusResponse,
)

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.get("", response_model=list[ApplicationResponse])
def list_applications(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    stage: Optional[str] = Query(default=None, description="Filter by CRM stage (draft, applied, oa, interview, etc.)"),
    company_slug: Optional[str] = Query(default=None, description="Filter by normalized company slug"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ApplicationResponse]:
    """List tracked applications ordered newest-first with snapshot and cooldown context."""
    stmt = select(Application)
    if stage:
        cleaned = stage.strip().lower()
        if cleaned not in VALID_STAGES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid stage '{stage}'. Must be one of: {sorted(VALID_STAGES)}",
            )
        stmt = stmt.where(Application.stage == cleaned)
    if company_slug:
        stmt = stmt.where(Application.company_slug == company_slug.strip().lower())

    stmt = stmt.order_by(Application.id.desc()).limit(limit)  # type: ignore[attr-defined]
    rows = list(session.exec(stmt).all())
    return [build_application_response(session, row, settings=settings) for row in rows]


@router.post("/draft", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_or_resume_draft(
    payload: ApplicationStartDraftRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApplicationResponse:
    """Record or resume an autofill Draft (`autofill_started_at` set, `submitted_at` remains NULL)."""
    return start_or_resume_draft(session, payload, settings=settings)


@router.get("/cooldown/{company_slug}", response_model=CooldownStatusResponse)
def read_company_cooldown(
    company_slug: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CooldownStatusResponse:
    """Check trailing 30-day submitted application count vs. company cooldown cap."""
    return get_company_cooldown_status(session, company_slug.strip().lower(), settings=settings)


@router.get("/{app_id}", response_model=ApplicationResponse)
def get_application(
    app_id: int,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApplicationResponse:
    """Retrieve a single application including its immutable offline JD and resume snapshots."""
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {app_id} not found",
        )
    return build_application_response(session, app, settings=settings)


@router.post("/{app_id}/submit", response_model=ApplicationResponse)
def submit_application(
    app_id: int,
    payload: ApplicationSubmitRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApplicationResponse:
    """Mark an application submitted and freeze its immutable offline JD + resume snapshot."""
    return mark_application_submitted(session, app_id, payload, settings=settings)


@router.patch("/{app_id}", response_model=ApplicationResponse)
def patch_application(
    app_id: int,
    payload: ApplicationUpdateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApplicationResponse:
    """Transition CRM stage (`applied -> oa -> screen -> interview -> offer -> rejected`) or edit notes."""
    return update_application(session, app_id, payload, settings=settings)

