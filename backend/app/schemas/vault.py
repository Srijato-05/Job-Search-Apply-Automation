"""Pydantic v2 request/response contracts for Fact Vault, Q&A Rules, and Taxonomy."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkHistoryEntry(BaseModel):
    """Single verified employment entry."""

    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    is_current: bool = False


class EducationEntry(BaseModel):
    """Verified Indian UG/PG academic entry."""

    degree: str = ""
    specialization: str = ""
    institution: str = ""
    university: str = ""
    passing_year: Optional[int] = None
    cgpa: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class FactVaultPayload(BaseModel):
    """Complete India-specific Verified Fact Vault schema."""

    model_config = ConfigDict(from_attributes=True)

    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    leetcode_url: str = ""

    current_ctc_lpa: float = Field(default=0.0, ge=0.0)
    current_fixed_lpa: float = Field(default=0.0, ge=0.0)
    current_variable_lpa: float = Field(default=0.0, ge=0.0)
    expected_ctc_lpa: float = Field(default=0.0, ge=0.0)
    min_acceptable_hike_pct: float = Field(default=0.0, ge=0.0, le=500.0)

    notice_period_days: int = Field(default=0, ge=0, le=180)
    serving_notice: bool = False
    last_working_day: Optional[date] = None
    notice_negotiable: bool = False
    min_negotiable_days: Optional[int] = Field(default=None, ge=0, le=180)

    total_exp_years: float = Field(default=0.0, ge=0.0, le=60.0)
    relevant_exp_years: float = Field(default=0.0, ge=0.0, le=60.0)
    skill_years_json: dict[str, float] = Field(default_factory=dict)

    current_city: str = ""
    hometown: str = ""
    preferred_cities_json: list[str] = Field(default_factory=list)
    willing_to_relocate: bool = True
    work_modes_json: list[str] = Field(default_factory=list)
    open_to_rotational_shifts: bool = False

    tenth_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    tenth_board: str = ""
    tenth_year: Optional[int] = Field(default=None, ge=1970, le=2040)
    twelfth_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    twelfth_board: str = ""
    twelfth_year: Optional[int] = Field(default=None, ge=1970, le=2040)
    education_history_json: list[dict[str, Any]] = Field(default_factory=list)
    active_backlogs: int = Field(default=0, ge=0)

    work_history_json: list[dict[str, Any]] = Field(default_factory=list)
    negative_keywords_json: list[str] = Field(default_factory=list)
    company_blacklist_json: list[str] = Field(default_factory=list)
    max_company_apps_30d: int = Field(default=3, ge=1, le=50)

    @field_validator("skill_years_json")
    @classmethod
    def _validate_skill_years(cls, value: dict[str, float]) -> dict[str, float]:
        for skill, yrs in value.items():
            if yrs < 0 or yrs > 60:
                raise ValueError(f"Invalid experience years for skill '{skill}': {yrs}")
        return value


class FactVaultResponse(FactVaultPayload):
    """Response model including singleton ID and updated timestamp."""

    id: int
    updated_at: datetime


class QARuleCreate(BaseModel):
    """Input payload for storing a verified screening answer."""

    question: str = Field(min_length=2)
    canonical_aliases: list[str] = Field(default_factory=list)
    verified_answer: str = Field(min_length=1)
    answer_type: str = Field(default="text", pattern="^(text|number|boolean|choice)$")
    portal_scope: str = Field(default="global", min_length=1)


class QARuleResponse(BaseModel):
    """Persisted Q&A rule."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    normalized_question: str
    canonical_aliases_json: list[str]
    verified_answer: str
    answer_type: str
    portal_scope: str
    usage_count: int
    created_at: datetime
    updated_at: datetime


class TaxonomyNormalizeRequest(BaseModel):
    """Payload to normalize raw skills, cities, or text snippets."""

    skills: list[str] = Field(default_factory=list)
    city: str = ""
    text: str = ""


class TaxonomyNormalizeResponse(BaseModel):
    """Normalized skills and Indian location metadata."""

    normalized_skills: list[str]
    extracted_skills: list[str]
    normalized_city: str
    office_locality: str
    is_india: bool

