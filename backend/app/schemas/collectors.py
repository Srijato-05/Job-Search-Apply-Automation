"""Pydantic schemas for Collector runs, telemetry, and source health."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CollectorRunRequest(BaseModel):
    """Payload to manually trigger a collector run."""

    source: str = Field(
        default="all",
        description="Target source: 'all', 'ats', 'jobspy', or a specific company slug",
    )
    force: bool = Field(
        default=False,
        description="If True, bypasses active cooldown timers and resumable sweep checkpoints",
    )
    hours_old: int = Field(
        default=24,
        ge=1,
        le=720,
        description="Lookback window in hours for JobSpy portal searches (e.g. 168 for initial 7-day seed)",
    )
    force_refresh_details: bool = Field(
        default=False,
        description="If True, re-fetches per-job detail JSONs even for already-known ATS external IDs",
    )


class CollectorProgressResponse(BaseModel):
    """Live progress state for an in-flight or recently completed collection sweep."""

    running: bool = False
    target: Optional[str] = None
    phase: str = "idle"
    completed: int = 0
    total: int = 0
    current_item: Optional[str] = None
    fetched_so_far: int = 0
    new_so_far: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class CollectorRunResponse(BaseModel):
    """Result of a triggered collector execution."""

    source_name: str
    company_slug: Optional[str] = None
    status: str
    fetched_count: int = 0
    new_count: int = 0
    closed_count: int = 0
    cooldown_until: Optional[datetime] = None
    error_message: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class SourceHealthItem(BaseModel):
    """Current health badge and telemetry for a single collector source."""

    source_key: str
    source_type: str  # "ats" or "jobspy"
    display_name: str
    ats_type: Optional[str] = None
    status: str  # "ok", "cooldown", "error", "never_run"
    last_polled_at: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    last_fetched_count: int = 0
    last_new_count: int = 0
    last_error: Optional[str] = None


class CollectorHealthResponse(BaseModel):
    """Aggregated health check for all configured collection sources."""

    total_sources: int
    healthy_sources: int
    cooldown_sources: int
    error_sources: int
    sources: list[SourceHealthItem]

