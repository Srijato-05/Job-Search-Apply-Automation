"""Pydantic v2 contracts for the Chromium Extension 4-State Banner resolver."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.applications import ApplicationResponse, CooldownStatusResponse
from app.schemas.jobs import JobDiffResponse, WinningScoreSummary

BannerState = Literal[
    "NEW_ROLE",
    "NEW_SIBLING_ROLE",
    "STARTED_BUT_NOT_SUBMITTED",
    "ALREADY_APPLIED",
]


class CheckPageRequest(BaseModel):
    """Tab context sent by the Chromium side panel to resolve the 4-State Banner."""

    page_url: str = ""
    apply_url: str = ""
    title: str = ""
    company_name: str = ""
    description_raw: str = ""
    location_raw: str = ""
    portal_name: str = "extension"
    external_job_id: Optional[str] = None


class CheckPageResponse(BaseModel):
    """Resolved 4-State Banner, sibling JD diff, winning resume, and 30-day cooldown."""

    banner_state: BannerState
    job_id: Optional[int] = None
    application_id: Optional[int] = None
    company_slug: str = ""
    company_name: str = ""
    role_subtag: str = ""
    req_id: Optional[str] = None
    winning_score: Optional[WinningScoreSummary] = None
    sibling_parent_id: Optional[int] = None
    sibling_diff: Optional[JobDiffResponse] = None
    existing_application: Optional[ApplicationResponse] = None
    cooldown: CooldownStatusResponse
    message: str = Field(default="")

