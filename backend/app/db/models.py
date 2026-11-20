"""SQLModel database models for all 10 core tables."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, ForeignKey, Integer, LargeBinary, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class FactVault(SQLModel, table=True):
    """Singleton table holding BGV-consistent verified candidate facts."""

    __tablename__ = "fact_vault"

    id: Optional[int] = Field(default=1, primary_key=True)

    # Personal & Public Profile Links
    full_name: str = Field(default="")
    email: str = Field(default="")
    phone: str = Field(default="")
    linkedin_url: str = Field(default="")
    github_url: str = Field(default="")
    portfolio_url: str = Field(default="")
    leetcode_url: str = Field(default="")

    # Compensation (India INR / LPA)
    current_ctc_lpa: float = Field(default=0.0)
    current_fixed_lpa: float = Field(default=0.0)
    current_variable_lpa: float = Field(default=0.0)
    expected_ctc_lpa: float = Field(default=0.0)
    min_acceptable_hike_pct: float = Field(default=0.0)

    # Notice Period & Availability
    notice_period_days: int = Field(default=0)
    serving_notice: bool = Field(default=False)
    last_working_day: Optional[date] = Field(default=None)
    notice_negotiable: bool = Field(default=False)
    min_negotiable_days: Optional[int] = Field(default=None)

    # Experience Matrix
    total_exp_years: float = Field(default=0.0)
    relevant_exp_years: float = Field(default=0.0)
    skill_years_json: dict[str, float] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )

    # Location & Work Mode
    current_city: str = Field(default="")
    hometown: str = Field(default="")
    preferred_cities_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    willing_to_relocate: bool = Field(default=True)
    work_modes_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    open_to_rotational_shifts: bool = Field(default=False)

    # Indian Education Format
    tenth_pct: Optional[float] = Field(default=None)
    tenth_board: str = Field(default="")
    tenth_year: Optional[int] = Field(default=None)
    twelfth_pct: Optional[float] = Field(default=None)
    twelfth_board: str = Field(default="")
    twelfth_year: Optional[int] = Field(default=None)
    education_history_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    active_backlogs: int = Field(default=0)

    # Employment History & Dealbreaker Rules
    work_history_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    negative_keywords_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    company_blacklist_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    max_company_apps_30d: int = Field(default=3)

    updated_at: datetime = Field(default_factory=utc_now)


class LearnedQARule(SQLModel, table=True):
    """Deterministic screening Q&A rules captured via Pause-and-Learn."""

    __tablename__ = "learned_qa_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    normalized_question: str = Field(index=True, unique=True)
    canonical_aliases_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    verified_answer: str
    answer_type: str = Field(default="text")
    portal_scope: str = Field(default="global")
    usage_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Resume(SQLModel, table=True):
    """Registered resume PDF tracks for multi-resume routing."""

    __tablename__ = "resumes"

    id: Optional[int] = Field(default=None, primary_key=True)
    track_name: str = Field(index=True)
    pdf_filename: str
    pdf_path: str
    pdf_sha256: str = Field(index=True)
    target_titles_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    search_locations_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    track_skills_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    cover_template: str = Field(default="", sa_column=Column(Text, nullable=False))
    raw_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ResumeBullet(SQLModel, table=True):
    """Extracted verbatim bullet points and 384-dim embeddings per resume."""

    __tablename__ = "resume_bullets"

    id: Optional[int] = Field(default=None, primary_key=True)
    resume_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    section_name: str = Field(default="experience")
    bullet_order: int = Field(default=0)
    bullet_text: str = Field(sa_column=Column(Text, nullable=False))
    extracted_skills_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    embedding_blob: Optional[bytes] = Field(
        default=None,
        sa_column=Column(LargeBinary, nullable=True),
    )


class Company(SQLModel, table=True):
    """Watched companies, ATS feed configurations, and employer classifications."""

    __tablename__ = "companies"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    display_name: str
    employer_type: str = Field(default="direct_product")
    ats_type: Optional[str] = Field(default=None)
    ats_config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    is_watched: bool = Field(default=False)
    is_blacklisted: bool = Field(default=False)
    health_status: str = Field(default="ok")
    last_polled_at: Optional[datetime] = Field(default=None)


class Job(SQLModel, table=True):
    """Collected job postings with Role Identity, Signal Extraction & Gate 1 audit state."""

    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(default="")
    company_name: str = Field(default="")
    company_slug: str = Field(default="", index=True)
    normalized_title: str = Field(default="", index=True)
    role_subtag: str = Field(default="")
    req_id: Optional[str] = Field(default=None, index=True)
    normalized_city: str = Field(default="", index=True)
    office_locality: str = Field(default="")
    work_mode: str = Field(default="unknown")
    exp_min_years: Optional[float] = Field(default=None)
    exp_max_years: Optional[float] = Field(default=None)
    salary_min_lpa: Optional[float] = Field(default=None)
    salary_max_lpa: Optional[float] = Field(default=None)
    max_notice_days: Optional[int] = Field(default=None)
    description_raw: str = Field(default="", sa_column=Column(Text, nullable=False))
    boilerplate_stripped_text: str = Field(
        default="",
        sa_column=Column(Text, nullable=False),
    )
    description_hash: str = Field(default="", index=True)
    simhash_64: Optional[int] = Field(default=None)
    jd_embedding_blob: Optional[bytes] = Field(
        default=None,
        sa_column=Column(LargeBinary, nullable=True),
    )
    primary_skills_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    secondary_skills_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    apply_friction: str = Field(default="unknown")
    employer_type: str = Field(default="unknown")
    hidden_by_gate1: bool = Field(default=False, index=True)
    hidden_reason: Optional[str] = Field(default=None)
    status: str = Field(default="active", index=True)
    parent_sibling_job_id: Optional[int] = Field(default=None, index=True)
    portal_signals_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    posted_at: Optional[datetime] = Field(default=None)
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_reposted_at: datetime = Field(default_factory=utc_now)
    repost_count: int = Field(default=0)


class JobSource(SQLModel, table=True):
    """Consolidated portal URLs pointing to the same canonical job."""

    __tablename__ = "job_sources"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    portal_name: str = Field(index=True)
    external_job_id: Optional[str] = Field(default=None, index=True)
    job_url: str = Field(index=True)
    apply_url: str = Field(default="")
    seen_at: datetime = Field(default_factory=utc_now)


class JobResumeScore(SQLModel, table=True):
    """Combined Option 1 Tier + Option 3 Semantic Bullet scores per (job, resume)."""

    __tablename__ = "job_resume_scores"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    resume_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    tier: str = Field(default="C")
    is_winning_resume: bool = Field(default=False)
    semantic_bullet_coverage_pct: float = Field(default=0.0)
    matched_primary_skills_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    missing_primary_skills_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    missing_secondary_skills_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    bullet_proof_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    cross_resume_alerts_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    scored_at: datetime = Field(default_factory=utc_now)


class Application(SQLModel, table=True):
    """Application Mini-CRM with Draft vs Submitted state and Offline Snapshots."""

    __tablename__ = "applications"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    company_slug: str = Field(index=True)
    resume_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("resumes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    stage: str = Field(default="draft", index=True)
    autofill_started_at: Optional[datetime] = Field(default=None)
    submitted_at: Optional[datetime] = Field(default=None, index=True)
    detection_method: str = Field(default="manual")
    portal_used: str = Field(default="")
    jd_snapshot_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    resume_filename_snapshot: str = Field(default="")
    submitted_answers_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    recruiter_notes: str = Field(default="", sa_column=Column(Text, nullable=False))


class CollectorRun(SQLModel, table=True):
    """Telemetry and circuit-breaker cooldown records per collector source."""

    __tablename__ = "collector_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_name: str = Field(index=True)
    company_slug: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="ok")
    fetched_count: int = Field(default=0)
    new_count: int = Field(default=0)
    closed_count: int = Field(default=0)
    cooldown_until: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = Field(default=None)

