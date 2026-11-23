"""Core business logic for Application Mini-CRM, Offline Snapshots, Cooldowns, and Extension 4-State Resolver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.config import Settings
from app.db.models import (
    Application,
    FactVault,
    Job,
    JobResumeScore,
    JobSource,
    Resume,
    utc_now,
)
from app.pipeline.gate2_identity import compute_jd_diff, resolve_job_identity
from app.pipeline.gate3_extractor import extract_job_signals, slugify_company
from app.resumes.embedder import EmbedderProtocol
from app.schemas.applications import (
    ApplicationResponse,
    ApplicationStartDraftRequest,
    ApplicationSubmitRequest,
    ApplicationUpdateRequest,
    CooldownStatusResponse,
)
from app.schemas.extension import CheckPageRequest, CheckPageResponse
from app.schemas.jobs import JobDiffResponse, WinningScoreSummary

VALID_STAGES = frozenset(
    {"draft", "applied", "oa", "screen", "interview", "offer", "rejected", "withdrawn"}
)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def get_company_cooldown_status(
    session: Session,
    company_slug: str,
    settings: Optional[Settings] = None,
) -> CooldownStatusResponse:
    """Count submitted applications to `company_slug` within the trailing 30 days.

    Drafts (`stage == 'draft'` or `submitted_at is None`) never count toward cooldowns.
    """
    cfg = settings or Settings()
    vault = session.get(FactVault, 1)
    max_apps = (
        vault.max_company_apps_30d
        if vault is not None and vault.max_company_apps_30d > 0
        else cfg.max_company_apps_30d
    )

    if not company_slug:
        return CooldownStatusResponse(
            company_slug="",
            apps_last_30d=0,
            max_company_apps_30d=max_apps,
            remaining_apps=max_apps,
            is_at_limit=False,
        )

    now = utc_now()
    cutoff = now - timedelta(days=30)

    candidates = list(
        session.exec(
            select(Application).where(
                Application.company_slug == company_slug,
                Application.submitted_at.is_not(None),  # type: ignore[attr-defined]
            )
        ).all()
    )

    submitted_dates: list[datetime] = []
    for app in candidates:
        if app.stage == "draft":
            continue
        sub_at = _as_utc(app.submitted_at)
        if sub_at is not None and sub_at >= cutoff:
            submitted_dates.append(sub_at)

    count = len(submitted_dates)
    remaining = max(0, max_apps - count)
    is_at_limit = count >= max_apps
    next_slot: Optional[datetime] = None
    warning: Optional[str] = None

    if is_at_limit and submitted_dates:
        next_slot = min(submitted_dates) + timedelta(days=30)
        warning = (
            f"30-day cooldown limit reached for '{company_slug}' "
            f"({count}/{max_apps} submitted apps). Next slot opens {next_slot.date().isoformat()}."
        )
    elif count == max(1, max_apps - 1) and max_apps > 1:
        warning = (
            f"Approaching 30-day cooldown limit for '{company_slug}' "
            f"({count}/{max_apps} submitted apps used)."
        )

    return CooldownStatusResponse(
        company_slug=company_slug,
        apps_last_30d=count,
        max_company_apps_30d=max_apps,
        remaining_apps=remaining,
        is_at_limit=is_at_limit,
        next_slot_opens_at=next_slot,
        warning_message=warning,
    )


def build_application_response(
    session: Session,
    app: Application,
    settings: Optional[Settings] = None,
    include_cooldown: bool = True,
) -> ApplicationResponse:
    """Hydrate an Application ORM row with job title, resume track name, and cooldown info."""
    job = session.get(Job, app.job_id) if app.job_id is not None else None
    resume = session.get(Resume, app.resume_id) if app.resume_id is not None else None
    cooldown = (
        get_company_cooldown_status(session, app.company_slug, settings=settings)
        if include_cooldown
        else None
    )
    return ApplicationResponse(
        id=int(app.id),
        job_id=app.job_id,
        company_slug=app.company_slug,
        resume_id=app.resume_id,
        stage=app.stage,
        autofill_started_at=app.autofill_started_at,
        submitted_at=app.submitted_at,
        detection_method=app.detection_method,
        portal_used=app.portal_used,
        jd_snapshot_text=app.jd_snapshot_text,
        resume_filename_snapshot=app.resume_filename_snapshot,
        submitted_answers_json=app.submitted_answers_json,
        recruiter_notes=app.recruiter_notes,
        job_title=job.title if job is not None else None,
        company_name=job.company_name if job is not None else None,
        resume_track_name=resume.track_name if resume is not None else None,
        cooldown=cooldown,
    )


def start_or_resume_draft(
    session: Session,
    payload: ApplicationStartDraftRequest,
    settings: Optional[Settings] = None,
) -> ApplicationResponse:
    """Create or resume a `draft` Application when autofill starts (does NOT set submitted_at)."""
    job: Optional[Job] = None
    if payload.job_id is not None:
        job = session.get(Job, payload.job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {payload.job_id} not found",
            )

    company_slug = (payload.company_slug or (job.company_slug if job else "")).strip().lower()
    if not company_slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Either job_id or a non-empty company_slug is required.",
        )

    resume_id = payload.resume_id
    if resume_id is None and job is not None:
        winner = session.exec(
            select(JobResumeScore).where(
                JobResumeScore.job_id == int(job.id),
                JobResumeScore.is_winning_resume.is_(True),
            )
        ).first()
        if winner is not None:
            resume_id = int(winner.resume_id)

    now = utc_now()
    if job is not None:
        existing = session.exec(
            select(Application)
            .where(Application.job_id == int(job.id))
            .order_by(Application.id.desc())  # type: ignore[attr-defined]
        ).first()
        if existing is not None:
            if existing.stage != "draft" or existing.submitted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Application #{existing.id} has already been submitted for job #{job.id}.",
                )
            merged_answers = dict(existing.submitted_answers_json or {})
            merged_answers.update(payload.submitted_answers_json or {})
            existing.submitted_answers_json = merged_answers
            if resume_id is not None:
                existing.resume_id = resume_id
            if payload.portal_used:
                existing.portal_used = payload.portal_used
            if existing.autofill_started_at is None:
                existing.autofill_started_at = now
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return build_application_response(session, existing, settings=settings)

    app = Application(
        job_id=int(job.id) if job is not None else None,
        company_slug=company_slug,
        resume_id=resume_id,
        stage="draft",
        autofill_started_at=now,
        submitted_at=None,
        detection_method=payload.detection_method,
        portal_used=payload.portal_used,
        submitted_answers_json=dict(payload.submitted_answers_json or {}),
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    return build_application_response(session, app, settings=settings)


def _freeze_offline_snapshots(
    session: Session,
    app: Application,
    jd_override: Optional[str] = None,
    resume_filename_override: Optional[str] = None,
    answers_override: Optional[dict] = None,
) -> None:
    """Freeze immutable offline JD, resume filename, and Q&A snapshots on first submission."""
    job = session.get(Job, app.job_id) if app.job_id is not None else None
    resume = session.get(Resume, app.resume_id) if app.resume_id is not None else None

    if not app.jd_snapshot_text:
        app.jd_snapshot_text = jd_override or (job.description_raw if job is not None else "")
    if not app.resume_filename_snapshot:
        app.resume_filename_snapshot = resume_filename_override or (
            resume.pdf_filename if resume is not None else ""
        )
    if answers_override:
        merged = dict(app.submitted_answers_json or {})
        merged.update(answers_override)
        app.submitted_answers_json = merged


def mark_application_submitted(
    session: Session,
    app_id: int,
    payload: ApplicationSubmitRequest,
    settings: Optional[Settings] = None,
) -> ApplicationResponse:
    """Transition an application to 'applied' and freeze immutable offline snapshots."""
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {app_id} not found",
        )

    first_submit = app.submitted_at is None
    if first_submit:
        if payload.resume_id is not None:
            app.resume_id = payload.resume_id
        app.submitted_at = utc_now()
        if app.stage == "draft":
            app.stage = "applied"
        app.detection_method = payload.detection_method
        if payload.portal_used is not None:
            app.portal_used = payload.portal_used
        _freeze_offline_snapshots(
            session,
            app,
            jd_override=payload.jd_snapshot_text,
            resume_filename_override=payload.resume_filename_snapshot,
            answers_override=payload.submitted_answers_json,
        )

    if payload.recruiter_notes is not None:
        app.recruiter_notes = payload.recruiter_notes

    session.add(app)
    session.commit()
    session.refresh(app)
    return build_application_response(session, app, settings=settings)


def update_application(
    session: Session,
    app_id: int,
    payload: ApplicationUpdateRequest,
    settings: Optional[Settings] = None,
) -> ApplicationResponse:
    """Advance CRM stage or update recruiter notes, freezing snapshots if leaving draft."""
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {app_id} not found",
        )

    if payload.stage is not None:
        new_stage = payload.stage.strip().lower()
        if new_stage not in VALID_STAGES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid stage '{payload.stage}'. Must be one of: {sorted(VALID_STAGES)}",
            )
        was_draft = app.stage == "draft" and app.submitted_at is None
        app.stage = new_stage
        if was_draft and new_stage != "draft":
            app.submitted_at = utc_now()
            _freeze_offline_snapshots(session, app)

    if payload.recruiter_notes is not None:
        app.recruiter_notes = payload.recruiter_notes

    if payload.submitted_answers_json is not None and app.stage == "draft":
        merged = dict(app.submitted_answers_json or {})
        merged.update(payload.submitted_answers_json)
        app.submitted_answers_json = merged

    session.add(app)
    session.commit()
    session.refresh(app)
    return build_application_response(session, app, settings=settings)


def _winning_score_summary(session: Session, job_id: int) -> Optional[WinningScoreSummary]:
    scores = list(
        session.exec(select(JobResumeScore).where(JobResumeScore.job_id == job_id)).all()
    )
    winner = next((s for s in scores if s.is_winning_resume), None)
    if winner is None:
        return None
    resume = session.get(Resume, winner.resume_id)
    return WinningScoreSummary(
        resume_id=int(winner.resume_id),
        track_name=resume.track_name if resume is not None else f"Resume #{winner.resume_id}",
        pdf_filename=resume.pdf_filename if resume is not None else "",
        tier=winner.tier,
        semantic_bullet_coverage_pct=winner.semantic_bullet_coverage_pct,
        matched_primary_skills_json=winner.matched_primary_skills_json,
        missing_primary_skills_json=winner.missing_primary_skills_json,
        missing_secondary_skills_json=winner.missing_secondary_skills_json,
        cross_resume_alerts_count=len(winner.cross_resume_alerts_json),
    )


def check_extension_page(
    session: Session,
    payload: CheckPageRequest,
    embedder: EmbedderProtocol,
    settings: Optional[Settings] = None,
) -> CheckPageResponse:
    """Resolve the Chrome Extension 4-State Banner read-only from URL, Req ID, and JD."""
    cfg = settings or Settings()

    # Step 1: Fast exact JobSource lookup by page_url or (portal_name, external_job_id)
    matched_job: Optional[Job] = None
    if payload.page_url.strip():
        src = session.exec(
            select(JobSource).where(JobSource.job_url == payload.page_url.strip())
        ).first()
        if src is not None:
            matched_job = session.get(Job, src.job_id)

    if matched_job is None and payload.external_job_id:
        src = session.exec(
            select(JobSource).where(
                JobSource.portal_name == payload.portal_name,
                JobSource.external_job_id == payload.external_job_id,
            )
        ).first()
        if src is not None:
            matched_job = session.get(Job, src.job_id)

    # Step 2: Run Gate 3 + Gate 2 identity detection when JD text is supplied
    signals = None
    sibling_parent_job: Optional[Job] = None
    sibling_diff_dto: Optional[JobDiffResponse] = None

    if matched_job is None and (payload.description_raw.strip() or (payload.title.strip() and payload.company_name.strip())):
        signals = extract_job_signals(
            title=payload.title or "Unknown Role",
            company_name=payload.company_name or "Unknown Company",
            raw_description=payload.description_raw or payload.title,
            location_raw=payload.location_raw,
            job_url=payload.page_url,
            apply_url=payload.apply_url or payload.page_url,
            portal_name=payload.portal_name,
        )
        embed_input = (signals.boilerplate_stripped_text or signals.raw_title)[: cfg.jd_embed_max_chars]
        jd_vector = embedder.embed_texts([embed_input])[0]

        identity = resolve_job_identity(
            session=session,
            signals=signals,
            jd_vector=jd_vector,
            portal_name=payload.portal_name,
            external_job_id=payload.external_job_id,
            job_url=payload.page_url,
            similarity_threshold=cfg.dedup_similarity_threshold,
            stack_overlap_threshold=cfg.dedup_stack_overlap_threshold,
        )
        if identity.action in ("existing_source", "merge_same_role") and identity.target_job is not None:
            matched_job = identity.target_job
        elif identity.action == "sibling_role" and identity.sibling_parent_id is not None:
            sibling_parent_job = session.get(Job, identity.sibling_parent_id)
            if sibling_parent_job is not None:
                temp_job = Job(
                    id=0,
                    title=signals.raw_title,
                    company_name=signals.company_name,
                    company_slug=signals.company_slug,
                    normalized_title=signals.normalized_title,
                    role_subtag=signals.role_subtag,
                    req_id=signals.req_id,
                    description_raw=payload.description_raw or payload.title,
                    boilerplate_stripped_text=signals.boilerplate_stripped_text,
                    primary_skills_json=signals.primary_skills,
                )
                sibling_diff_dto = JobDiffResponse(**compute_jd_diff(sibling_parent_job, temp_job))

    # Determine company context and cooldown
    company_slug = (
        matched_job.company_slug
        if matched_job is not None
        else (signals.company_slug if signals is not None else slugify_company(payload.company_name))
    )
    company_name = (
        matched_job.company_name
        if matched_job is not None
        else (signals.company_name if signals is not None else payload.company_name)
    )
    cooldown = get_company_cooldown_status(session, company_slug, settings=cfg)

    # Step 3: Check Application records against the canonical matched job
    if matched_job is not None:
        job_id = int(matched_job.id)
        existing_app = session.exec(
            select(Application)
            .where(Application.job_id == job_id)
            .order_by(Application.id.desc())  # type: ignore[attr-defined]
        ).first()
        winning = _winning_score_summary(session, job_id)

        if existing_app is not None:
            app_dto = build_application_response(session, existing_app, settings=cfg, include_cooldown=False)
            if existing_app.submitted_at is not None or existing_app.stage != "draft":
                sub_date = existing_app.submitted_at.date().isoformat() if existing_app.submitted_at else "earlier"
                return CheckPageResponse(
                    banner_state="ALREADY_APPLIED",
                    job_id=job_id,
                    application_id=int(existing_app.id),
                    company_slug=company_slug,
                    company_name=company_name,
                    role_subtag=matched_job.role_subtag,
                    req_id=matched_job.req_id,
                    winning_score=winning,
                    existing_application=app_dto,
                    cooldown=cooldown,
                    message=f"Already applied on {sub_date} ({existing_app.resume_filename_snapshot or 'resume recorded'}).",
                )

            return CheckPageResponse(
                banner_state="STARTED_BUT_NOT_SUBMITTED",
                job_id=job_id,
                application_id=int(existing_app.id),
                company_slug=company_slug,
                company_name=company_name,
                role_subtag=matched_job.role_subtag,
                req_id=matched_job.req_id,
                winning_score=winning,
                existing_application=app_dto,
                cooldown=cooldown,
                message="Autofill draft started earlier — not yet submitted.",
            )

        # Matched job exists in DB without application; check if it's a linked Sibling Role
        if matched_job.parent_sibling_job_id is not None:
            parent = session.get(Job, matched_job.parent_sibling_job_id)
            diff_dto = (
                JobDiffResponse(**compute_jd_diff(parent, matched_job))
                if parent is not None
                else None
            )
            return CheckPageResponse(
                banner_state="NEW_SIBLING_ROLE",
                job_id=job_id,
                company_slug=company_slug,
                company_name=company_name,
                role_subtag=matched_job.role_subtag,
                req_id=matched_job.req_id,
                winning_score=winning,
                sibling_parent_id=matched_job.parent_sibling_job_id,
                sibling_diff=diff_dto,
                cooldown=cooldown,
                message=f"Separate sibling opening detected at {company_name} ({matched_job.role_subtag}).",
            )

        return CheckPageResponse(
            banner_state="NEW_ROLE",
            job_id=job_id,
            company_slug=company_slug,
            company_name=company_name,
            role_subtag=matched_job.role_subtag,
            req_id=matched_job.req_id,
            winning_score=winning,
            cooldown=cooldown,
            message=f"Tracked new role at {company_name}.",
        )

    # Un-ingested Sibling Role matched against an existing company/title posting
    if sibling_parent_job is not None:
        return CheckPageResponse(
            banner_state="NEW_SIBLING_ROLE",
            company_slug=company_slug,
            company_name=company_name,
            role_subtag=signals.role_subtag if signals else "",
            req_id=signals.req_id if signals else None,
            sibling_parent_id=int(sibling_parent_job.id),
            sibling_diff=sibling_diff_dto,
            cooldown=cooldown,
            message=f"New sibling role at {company_name} (differs from existing Job #{sibling_parent_job.id}).",
        )

    return CheckPageResponse(
        banner_state="NEW_ROLE",
        company_slug=company_slug,
        company_name=company_name,
        role_subtag=signals.role_subtag if signals else "",
        req_id=signals.req_id if signals else None,
        cooldown=cooldown,
        message=f"New unapplied role at {company_name or 'company'}.",
    )

