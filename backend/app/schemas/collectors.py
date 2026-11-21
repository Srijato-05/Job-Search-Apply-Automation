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
        description="If True, bypasses active cooldown timers",
    )


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

