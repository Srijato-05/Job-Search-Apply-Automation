"""Pydantic v2 request/response contracts for Multi-Resume Registry."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ResumeBulletResponse(BaseModel):
    """Single verbatim extracted bullet from a resume PDF."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    section_name: str
    bullet_order: int
    bullet_text: str
    extracted_skills_json: list[str]
    has_embedding: bool = False


class ResumeUpdatePayload(BaseModel):
    """Mutable metadata for a registered resume track."""

    track_name: Optional[str] = Field(default=None, min_length=1)
    target_titles_json: Optional[list[str]] = None
    search_locations_json: Optional[list[str]] = None
    track_skills_json: Optional[list[str]] = None
    cover_template: Optional[str] = None
    is_active: Optional[bool] = None


class ResumeSummaryResponse(BaseModel):
    """Resume track metadata without full bullet array."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    track_name: str
    pdf_filename: str
    pdf_sha256: str
    target_titles_json: list[str]
    search_locations_json: list[str]
    track_skills_json: list[str]
    cover_template: str
    is_active: bool
    bullet_count: int = 0
    created_at: datetime
    updated_at: datetime


class ResumeDetailResponse(ResumeSummaryResponse):
    """Full resume details including all extracted bullets."""

    raw_text: str
    bullets: list[ResumeBulletResponse] = Field(default_factory=list)

