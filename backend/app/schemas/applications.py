"""Pydantic v2 contracts for Application Mini-CRM, Offline Snapshots, Cooldowns & Backup."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CooldownStatusResponse(BaseModel):
    """30-day rolling application cap telemetry for a company."""

    company_slug: str
    apps_last_30d: int
    max_company_apps_30d: int
    remaining_apps: int
    is_at_limit: bool
    next_slot_opens_at: Optional[datetime] = None
    warning_message: Optional[str] = None


class ApplicationStartDraftRequest(BaseModel):
    """Payload recorded when the user begins autofill (Draft, NOT Submitted)."""

    job_id: Optional[int] = None
    company_slug: Optional[str] = None
    resume_id: Optional[int] = None
    portal_used: str = ""
    detection_method: str = "extension_autofill"
    submitted_answers_json: dict[str, Any] = Field(default_factory=dict)


class ApplicationSubmitRequest(BaseModel):
    """Payload freezing an immutable snapshot when the user submits an application."""

    resume_id: Optional[int] = None
    detection_method: str = "extension_submit"
    portal_used: Optional[str] = None
    jd_snapshot_text: Optional[str] = None
    resume_filename_snapshot: Optional[str] = None
    submitted_answers_json: Optional[dict[str, Any]] = None
    recruiter_notes: Optional[str] = None


class ApplicationUpdateRequest(BaseModel):
    """Partial update for CRM stage transitions and recruiter notes."""

    stage: Optional[str] = None
    recruiter_notes: Optional[str] = None
    submitted_answers_json: Optional[dict[str, Any]] = None


class ApplicationResponse(BaseModel):
    """Full Application Mini-CRM record with immutable offline snapshots and context."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: Optional[int]
    company_slug: str
    resume_id: Optional[int]
    stage: str
    autofill_started_at: Optional[datetime]
    submitted_at: Optional[datetime]
    detection_method: str
    portal_used: str
    jd_snapshot_text: str
    resume_filename_snapshot: str
    submitted_answers_json: dict[str, Any]
    recruiter_notes: str
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    resume_track_name: Optional[str] = None
    cooldown: Optional[CooldownStatusResponse] = None


class BackupRestoreResponse(BaseModel):
    """Summary returned after restoring a full ZIP backup."""

    status: str
    restored_db_bytes: int
    restored_resumes_count: int
    safety_snapshot_path: Optional[str] = None
    message: str

