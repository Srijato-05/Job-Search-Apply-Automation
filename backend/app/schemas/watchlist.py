"""Pydantic schemas for Watched Companies and ATS configurations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CompanyBase(BaseModel):
    slug: str
    display_name: str
    employer_type: str = "direct_product"
    ats_type: Optional[str] = None
    ats_config_json: dict[str, Any] = Field(default_factory=dict)
    is_watched: bool = True
    is_blacklisted: bool = False


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    display_name: Optional[str] = None
    employer_type: Optional[str] = None
    ats_type: Optional[str] = None
    ats_config_json: Optional[dict[str, Any]] = None
    is_watched: Optional[bool] = None
    is_blacklisted: Optional[bool] = None


class CompanyResponse(CompanyBase):
    id: int
    health_status: str
    last_polled_at: Optional[datetime] = None


class WatchlistSeedResponse(BaseModel):
    seeded_count: int
    updated_count: int
    total_count: int
    message: str

