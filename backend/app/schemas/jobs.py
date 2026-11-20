"""Pydantic v2 request/response contracts for Jobs, Pipeline Scores, and JD Diff."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobIngestItem(BaseModel):
    """Raw job payload submitted for 5-Gate pipeline ingestion."""

    title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    description_raw: str = Field(min_length=1)
    location_raw: str = ""
    portal_name: str = "manual"
    external_job_id: Optional[str] = None
    job_url: str = ""
    apply_url: str = ""
    posted_at: Optional[datetime] = None
    portal_metadata: dict[str, Any] = Field(default_factory=dict)


class JobIngestBatchRequest(BaseModel):
    """Batch ingestion request wrapping multiple raw jobs."""

    jobs: list[JobIngestItem] = Field(min_length=1)


class JobIngestResultResponse(BaseModel):
    """Per-job outcome returned after pipeline processing."""

    job_id: int
    action: str
    hidden_by_gate1: bool
    hidden_reason: Optional[str]
    winning_tier: Optional[str]
    winning_resume_id: Optional[int]


class JobSourceResponse(BaseModel):
    """Single portal link pointing to a job."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    portal_name: str
    external_job_id: Optional[str]
    job_url: str
    apply_url: str
    seen_at: datetime


class WinningScoreSummary(BaseModel):
    """Condensed score badge attached to each job card."""

    resume_id: int
    track_name: str
    pdf_filename: str
    tier: str
    semantic_bullet_coverage_pct: float
    matched_primary_skills_json: list[str]
    missing_primary_skills_json: list[str]
    missing_secondary_skills_json: list[str]
    cross_resume_alerts_count: int = 0


class JobResumeScoreDetail(BaseModel):
    """Full Option 1 + Option 3 score breakdown for a single resume variant."""

    resume_id: int
    track_name: str
    pdf_filename: str
    tier: str
    is_winning_resume: bool
    semantic_bullet_coverage_pct: float
    matched_primary_skills_json: list[str]
    missing_primary_skills_json: list[str]
    missing_secondary_skills_json: list[str]
    bullet_proof_json: list[dict[str, Any]]
    cross_resume_alerts_json: list[dict[str, Any]]
    scored_at: datetime


class JobCardResponse(BaseModel):
    """Faceted job queue item with Gate 3 signals and winning resume badge."""

    id: int
    title: str
    company_name: str
    company_slug: str
    role_subtag: str
    req_id: Optional[str]
    normalized_city: str
    office_locality: str
    work_mode: str
    exp_min_years: Optional[float]
    exp_max_years: Optional[float]
    salary_min_lpa: Optional[float]
    salary_max_lpa: Optional[float]
    max_notice_days: Optional[int]
    notice_compatible: bool
    apply_friction: str
    employer_type: str
    hidden_by_gate1: bool
    hidden_reason: Optional[str]
    status: str
    parent_sibling_job_id: Optional[int]
    repost_count: int
    posted_at: Optional[datetime]
    first_seen_at: datetime
    last_reposted_at: datetime
    winning_score: Optional[WinningScoreSummary] = None
    sources: list[JobSourceResponse] = Field(default_factory=list)


class JobListResponse(BaseModel):
    """Paginated response for faceted job queue queries."""

    total: int
    items: list[JobCardResponse]


class SiblingJobSummary(BaseModel):
    """Minimal summary for navigating between Same-Title Sibling Roles."""

    id: int
    title: str
    role_subtag: str
    req_id: Optional[str]
    normalized_city: str
    status: str


class JobDetailResponse(JobCardResponse):
    """Full job detail payload including raw/cleaned JD, scores across resumes, and siblings."""

    description_raw: str
    boilerplate_stripped_text: str
    primary_skills_json: list[str]
    secondary_skills_json: list[str]
    portal_signals_json: dict[str, Any]
    all_scores: list[JobResumeScoreDetail] = Field(default_factory=list)
    sibling_jobs: list[SiblingJobSummary] = Field(default_factory=list)


class JobDiffResponse(BaseModel):
    """Side-by-Side JD diff between two sibling or compared jobs."""

    job_a_id: int
    job_b_id: int
    job_a_subtag: str
    job_b_subtag: str
    similarity_pct: float
    shared_skills: list[str]
    only_in_job_a_skills: list[str]
    only_in_job_b_skills: list[str]
    unchanged_lines: list[str]
    removed_lines: list[str]
    added_lines: list[str]


class JobStatusUpdate(BaseModel):
    """Manual status or Gate 1 audit override."""

    status: Optional[str] = Field(default=None, pattern="^(active|closed)$")
    hidden_by_gate1: Optional[bool] = None
    hidden_reason: Optional[str] = None

