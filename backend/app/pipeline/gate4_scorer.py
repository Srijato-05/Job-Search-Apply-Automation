"""Gate 4: Combined Option 1 (Tier S/A/B/C) + Option 3 (Semantic Bullet Proof) Scorer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlmodel import Session, select

from app.config import Settings
from app.db.models import FactVault, Job, JobResumeScore, Resume, ResumeBullet, utc_now
from app.pipeline.gate1_filters import effective_candidate_notice_days
from app.resumes.embedder import EmbedderProtocol, blob_to_vector
from app.vault.taxonomy import CORE_LANGUAGES, cities_compatible

_TIER_RANK: dict[str, int] = {"S": 3, "A": 2, "B": 1, "C": 0}


@dataclass
class _ResumeBundle:
    resume: Resume
    bullets: list[ResumeBullet]
    bullet_matrix: np.ndarray
    skills_set: set[str]
    archetype: str


def detect_role_archetype(text: str, skills: list[str] | set[str]) -> str:
    """Deterministically infer role archetype from title/track text and core skills."""
    lowered = text.lower()
    skill_set = set(skills)

    if re.search(r"\b(?:full[\s-]?stack)\b", lowered):
        return "fullstack"
    if re.search(r"\b(?:android|ios|flutter|react\s+native|mobile\s+engineer)\b", lowered):
        return "mobile"
    if re.search(r"\b(?:devops|sre|site\s+reliability|infrastructure\s+engineer)\b", lowered):
        return "devops"
    if re.search(r"\b(?:data\s+engineer|ml\s+engineer|machine\s+learning|ai\s+engineer|data\s+scientist)\b", lowered):
        return "data_ml"
    if re.search(r"\b(?:front[\s-]?end|ui\s+engineer|react\s+developer|angular\s+developer)\b", lowered):
        return "frontend"
    if re.search(r"\b(?:back[\s-]?end|server[\s-]?side|api\s+engineer|distributed\s+systems)\b", lowered):
        return "backend"

    has_backend = bool(skill_set & {"Python", "Go", "Java", "FastAPI", "Django", "Spring Boot", "Apache Kafka"})
    has_frontend = bool(skill_set & {"React", "Angular", "Vue.js", "Next.js", "Tailwind CSS"})
    if has_backend and has_frontend:
        return "fullstack"
    if has_frontend and not has_backend:
        return "frontend"
    if has_backend and not has_frontend:
        return "backend"
    return "general"


def _archetype_compatible(jd_arch: str, resume_arch: str) -> bool:
    if jd_arch == "general" or resume_arch == "general":
        return True
    if jd_arch == resume_arch:
        return True
    if resume_arch == "fullstack" and jd_arch in {"backend", "frontend", "fullstack"}:
        return True
    return False


def _evaluate_experience_fit(job: Job, vault: FactVault, cfg: Settings) -> str:
    if vault.total_exp_years <= 0:
        return "exact"
    exp_min = job.exp_min_years
    exp_max = job.exp_max_years
    if exp_min is None and exp_max is None:
        return "exact"
    low = exp_min if exp_min is not None else 0.0
    high = exp_max if exp_max is not None else 99.0
    if low - cfg.exp_fit_lower_grace_years <= vault.total_exp_years <= high + cfg.exp_fit_upper_grace_years:
        return "exact"
    if (
        (low - cfg.exp_fit_stretch_years <= vault.total_exp_years < low - cfg.exp_fit_lower_grace_years)
        or (vault.total_exp_years > high + cfg.exp_fit_upper_grace_years)
    ):
        return "stretch"
    return "under"


def _evaluate_logistics(job: Job, vault: FactVault) -> bool:
    eff_notice = effective_candidate_notice_days(vault)
    notice_ok = True if job.max_notice_days is None else (eff_notice <= job.max_notice_days)
    if not notice_ok:
        return False

    if not job.normalized_city or job.normalized_city == "Remote (India)" or job.work_mode == "remote":
        return True
    if vault.willing_to_relocate:
        return True
    preferred = list(vault.preferred_cities_json) + ([vault.current_city] if vault.current_city else [])
    if not preferred:
        return True
    return any(cities_compatible(job.normalized_city, c) for c in preferred)


def _compute_tier(
    has_zero_core_lang_match: bool,
    archetype_ok: bool,
    missing_primary: list[str],
    missing_secondary: list[str],
    primary_match_ratio: float,
    exp_fit: str,
    logistics_ok: bool,
    coverage_pct: float,
    cfg: Settings,
) -> str:
    if (
        has_zero_core_lang_match
        or exp_fit == "under"
        or coverage_pct < cfg.tier_b_coverage_pct
        or primary_match_ratio < cfg.tier_c_min_primary_ratio
    ):
        return "C"
    if (
        archetype_ok
        and len(missing_primary) == 0
        and exp_fit == "exact"
        and logistics_ok
        and coverage_pct >= cfg.tier_s_coverage_pct
    ):
        return "S"
    if (
        (len(missing_primary) == 0 or primary_match_ratio >= cfg.tier_a_primary_ratio)
        and exp_fit in {"exact", "stretch"}
        and len(missing_secondary) <= cfg.tier_a_max_missing_secondary
        and coverage_pct >= cfg.tier_a_coverage_pct
    ):
        return "A"
    if (
        (len(missing_primary) <= cfg.tier_b_max_missing_primary or primary_match_ratio >= cfg.tier_b_primary_ratio)
        and exp_fit in {"exact", "stretch"}
        and coverage_pct >= cfg.tier_b_coverage_pct
    ):
        return "B"
    return "C"


def score_job_against_resumes(
    session: Session,
    job: Job,
    requirement_lines: list[str],
    vault: FactVault,
    embedder: EmbedderProtocol,
    settings: Settings | None = None,
    semantic_threshold: float | None = None,
) -> list[JobResumeScore]:
    """Evaluate a job against all active resumes using Combined Option 1 + Option 3."""
    cfg = settings or Settings()
    threshold = semantic_threshold if semantic_threshold is not None else cfg.semantic_threshold
    # Remove stale scores before recomputing cleanly
    stale_scores = session.exec(select(JobResumeScore).where(JobResumeScore.job_id == job.id)).all()
    for stale in stale_scores:
        session.delete(stale)
    session.flush()

    resumes = list(
        session.exec(
            select(Resume).where(Resume.is_active.is_(True)).order_by(Resume.id.asc())
        ).all()
    )
    if not resumes:
        return []

    bundles: list[_ResumeBundle] = []
    for resume in resumes:
        bullets = list(
            session.exec(
                select(ResumeBullet)
                .where(ResumeBullet.resume_id == resume.id)
                .order_by(ResumeBullet.bullet_order.asc())
            ).all()
        )
        valid_bullets = [b for b in bullets if b.embedding_blob]
        if valid_bullets:
            matrix = np.vstack([blob_to_vector(b.embedding_blob) for b in valid_bullets])
        else:
            matrix = np.zeros((0, 0), dtype=np.float32)

        skills_set = set(resume.track_skills_json)
        for b in bullets:
            skills_set.update(b.extracted_skills_json)

        track_text = f"{resume.track_name} {' '.join(resume.target_titles_json)}"
        bundles.append(
            _ResumeBundle(
                resume=resume,
                bullets=valid_bullets,
                bullet_matrix=matrix,
                skills_set=skills_set,
                archetype=detect_role_archetype(track_text, skills_set),
            )
        )

    req_vectors = embedder.embed_texts(requirement_lines) if requirement_lines else np.zeros((0, 0), dtype=np.float32)

    jd_arch = detect_role_archetype(job.title, job.primary_skills_json)
    exp_fit = _evaluate_experience_fit(job, vault, cfg)
    logistics_ok = _evaluate_logistics(job, vault)
    jd_core_langs = [s for s in job.primary_skills_json if s in CORE_LANGUAGES]

    per_resume_records: list[tuple[JobResumeScore, _ResumeBundle, tuple[Any, ...]]] = []

    for bundle in bundles:
        matched_primary = [s for s in job.primary_skills_json if s in bundle.skills_set]
        missing_primary = [s for s in job.primary_skills_json if s not in bundle.skills_set]
        missing_secondary = [s for s in job.secondary_skills_json if s not in bundle.skills_set]

        has_zero_core_lang_match = bool(jd_core_langs) and len(set(jd_core_langs) & bundle.skills_set) == 0
        archetype_ok = _archetype_compatible(jd_arch, bundle.archetype)

        proof_rows: list[dict[str, Any]] = []
        matched_reqs = 0
        if requirement_lines and bundle.bullet_matrix.size > 0 and req_vectors.size > 0:
            sim_matrix = req_vectors @ bundle.bullet_matrix.T
            for idx, req_line in enumerate(requirement_lines):
                row_sims = sim_matrix[idx]
                best_j = int(np.argmax(row_sims))
                best_sim = float(row_sims[best_j])
                is_match = best_sim >= threshold
                if is_match:
                    matched_reqs += 1
                proof_rows.append(
                    {
                        "jd_requirement": req_line,
                        "matched_bullet": bundle.bullets[best_j].bullet_text if is_match else None,
                        "section_name": bundle.bullets[best_j].section_name if is_match else None,
                        "similarity": round(best_sim, 4),
                        "status": "MATCHED" if is_match else "GAP",
                    }
                )
        else:
            for req_line in requirement_lines:
                proof_rows.append(
                    {
                        "jd_requirement": req_line,
                        "matched_bullet": None,
                        "section_name": None,
                        "similarity": 0.0,
                        "status": "GAP",
                    }
                )

        coverage_pct = (
            round(100.0 * matched_reqs / len(requirement_lines), 1)
            if requirement_lines
            else 0.0
        )

        primary_match_ratio = (
            len(matched_primary) / len(job.primary_skills_json)
            if job.primary_skills_json
            else 1.0
        )

        tier = _compute_tier(
            has_zero_core_lang_match=has_zero_core_lang_match,
            archetype_ok=archetype_ok,
            missing_primary=missing_primary,
            missing_secondary=missing_secondary,
            primary_match_ratio=primary_match_ratio,
            exp_fit=exp_fit,
            logistics_ok=logistics_ok,
            coverage_pct=coverage_pct,
            cfg=cfg,
        )

        score_row = JobResumeScore(
            job_id=int(job.id),
            resume_id=int(bundle.resume.id),
            tier=tier,
            is_winning_resume=False,
            semantic_bullet_coverage_pct=coverage_pct,
            matched_primary_skills_json=matched_primary,
            missing_primary_skills_json=missing_primary,
            missing_secondary_skills_json=missing_secondary,
            bullet_proof_json=proof_rows,
            cross_resume_alerts_json=[],
            scored_at=utc_now(),
        )
        rank_key = (
            _TIER_RANK[tier],
            coverage_pct,
            -len(missing_primary),
            len(matched_primary),
            -int(bundle.resume.id),
        )
        per_resume_records.append((score_row, bundle, rank_key))

    # Select winning resume and compute Cross-Resume Bullet Alerts for GAP items
    winner_score, winner_bundle, _ = max(per_resume_records, key=lambda item: item[2])
    winner_score.is_winning_resume = True

    if requirement_lines and req_vectors.size > 0 and len(bundles) > 1:
        alerts: list[dict[str, Any]] = []
        for idx, proof in enumerate(winner_score.bullet_proof_json):
            if proof["status"] != "GAP":
                continue
            req_vec = req_vectors[idx]
            best_alert: dict[str, Any] | None = None
            best_alert_sim = threshold - 1e-6

            for other_bundle in bundles:
                if other_bundle.resume.id == winner_bundle.resume.id:
                    continue
                if other_bundle.bullet_matrix.size == 0:
                    continue
                sims = other_bundle.bullet_matrix @ req_vec
                top_idx = int(np.argmax(sims))
                top_sim = float(sims[top_idx])
                if top_sim >= threshold and top_sim > best_alert_sim:
                    best_alert_sim = top_sim
                    best_alert = {
                        "jd_requirement": proof["jd_requirement"],
                        "other_resume_id": int(other_bundle.resume.id),
                        "other_resume_track": other_bundle.resume.track_name,
                        "other_resume_pdf": other_bundle.resume.pdf_filename,
                        "matching_bullet": other_bundle.bullets[top_idx].bullet_text,
                        "similarity": round(top_sim, 4),
                    }
            if best_alert is not None:
                alerts.append(best_alert)

        winner_score.cross_resume_alerts_json = alerts

    saved_scores: list[JobResumeScore] = []
    for score_row, _, _ in per_resume_records:
        session.add(score_row)
        saved_scores.append(score_row)

    session.flush()
    return saved_scores

