"""Chromium Extension Bridge API endpoints (4-State Banner resolver)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_embedder, get_session, get_settings
from app.applications.service import check_extension_page
from app.config import Settings
from app.resumes.embedder import EmbedderProtocol
from app.schemas.extension import CheckPageRequest, CheckPageResponse

router = APIRouter(prefix="/extension", tags=["Extension Bridge"])


@router.post("/check-page", response_model=CheckPageResponse)
def check_page(
    payload: CheckPageRequest,
    session: Session = Depends(get_session),
    embedder: EmbedderProtocol = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
) -> CheckPageResponse:
    """Resolve current browser tab into NEW_ROLE, NEW_SIBLING_ROLE, STARTED_BUT_NOT_SUBMITTED, or ALREADY_APPLIED."""
    return check_extension_page(session, payload, embedder=embedder, settings=settings)

