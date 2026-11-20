"""Gate 2: 4-Layer Role Identity Fingerprint, Sibling Role Isolation & JD Diff."""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
from sqlmodel import Session, select

from app.db.models import Job, JobSource
from app.pipeline.gate3_extractor import ExtractedJobSignals, extract_requirement_lines
from app.resumes.embedder import blob_to_vector, cosine_similarity
from app.vault.taxonomy import extract_skills_from_text


@dataclass
class IdentityResolution:
    """Resolution decision for an incoming job posting."""

    action: Literal["existing_source", "merge_same_role", "sibling_role", "new_role"]
    target_job: Optional[Job] = None
    sibling_parent_id: Optional[int] = None


def compute_description_hash(boilerplate_stripped_text: str) -> str:
    """Compute SHA-256 over normalized boilerplate-stripped text."""
    normalized = " ".join(boilerplate_stripped_text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_simhash64(text: str) -> int:
    """Compute a deterministic signed 64-bit SimHash compatible with SQLite INTEGER."""
    tokens = [tok for tok in text.lower().split() if len(tok) >= 2]
    if not tokens:
        return 0
    weights = [0] * 64
    for tok in tokens:
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big", signed=False)
        for bit in range(64):
            weights[bit] += 1 if (h >> bit) & 1 else -1

    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            fingerprint |= 1 << bit

    # Convert unsigned uint64 to SQLite signed int64
    if fingerprint >= (1 << 63):
        fingerprint -= 1 << 64
    return fingerprint


def _skill_jaccard(skills_a: list[str], skills_b: list[str]) -> float:
    set_a, set_b = set(skills_a), set(skills_b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def resolve_job_identity(
    session: Session,
    signals: ExtractedJobSignals,
    jd_vector: np.ndarray,
    portal_name: str,
    external_job_id: Optional[str],
    job_url: str,
    similarity_threshold: float = 0.88,
    stack_overlap_threshold: float = 0.70,
) -> IdentityResolution:
    """Resolve whether an incoming posting is an existing link, mirror/repost, sibling, or new role."""
    # 0. Exact JobSource lookup by URL or (portal_name, external_job_id)
    if job_url:
        src = session.exec(select(JobSource).where(JobSource.job_url == job_url)).first()
        if src is not None:
            job = session.get(Job, src.job_id)
            if job is not None:
                return IdentityResolution(action="existing_source", target_job=job)

    if external_job_id:
        src = session.exec(
            select(JobSource).where(
                JobSource.portal_name == portal_name,
                JobSource.external_job_id == external_job_id,
            )
        ).first()
        if src is not None:
            job = session.get(Job, src.job_id)
            if job is not None:
                return IdentityResolution(action="existing_source", target_job=job)

    # Layer 1: Same company + explicit req_id check
    if signals.req_id:
        same_req = session.exec(
            select(Job).where(
                Job.company_slug == signals.company_slug,
                Job.req_id == signals.req_id,
            )
        ).first()
        if same_req is not None:
            return IdentityResolution(action="merge_same_role", target_job=same_req)

    # Find candidates with same (company_slug, normalized_title, normalized_city)
    candidates = list(
        session.exec(
            select(Job).where(
                Job.company_slug == signals.company_slug,
                Job.normalized_title == signals.normalized_title,
                Job.normalized_city == signals.normalized_city,
            )
        ).all()
    )
    if not candidates:
        return IdentityResolution(action="new_role")

    incoming_hash = compute_description_hash(signals.boilerplate_stripped_text)
    sibling_anchor: Optional[Job] = None

    for cand in candidates:
        # Distinct explicit Requisition IDs are NEVER merged
        if signals.req_id and cand.req_id and signals.req_id != cand.req_id:
            if sibling_anchor is None:
                sibling_anchor = cand
            continue

        if cand.description_hash == incoming_hash:
            return IdentityResolution(action="merge_same_role", target_job=cand)

        if cand.jd_embedding_blob:
            cand_vec = blob_to_vector(cand.jd_embedding_blob)
            vec_sim = cosine_similarity(jd_vector, cand_vec)
            stack_overlap = _skill_jaccard(signals.primary_skills, cand.primary_skills_json)
            if vec_sim >= similarity_threshold and stack_overlap >= stack_overlap_threshold:
                return IdentityResolution(action="merge_same_role", target_job=cand)

        if sibling_anchor is None:
            sibling_anchor = cand

    if sibling_anchor is not None:
        return IdentityResolution(action="sibling_role", sibling_parent_id=int(sibling_anchor.id))

    return IdentityResolution(action="new_role")


def compute_jd_diff(job_a: Job, job_b: Job) -> dict[str, object]:
    """Compute a Side-by-Side requirement & skill diff between two boilerplate-stripped JDs."""
    lines_a = extract_requirement_lines(job_a.boilerplate_stripped_text or job_a.description_raw)
    lines_b = extract_requirement_lines(job_b.boilerplate_stripped_text or job_b.description_raw)

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    similarity_pct = round(matcher.ratio() * 100.0, 1)

    unchanged: list[str] = []
    removed: list[str] = []
    added: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged.extend(lines_a[i1:i2])
        elif tag == "delete":
            removed.extend(lines_a[i1:i2])
        elif tag == "insert":
            added.extend(lines_b[j1:j2])
        elif tag == "replace":
            removed.extend(lines_a[i1:i2])
            added.extend(lines_b[j1:j2])

    skills_a = set(job_a.primary_skills_json) or set(extract_skills_from_text(job_a.boilerplate_stripped_text))
    skills_b = set(job_b.primary_skills_json) or set(extract_skills_from_text(job_b.boilerplate_stripped_text))

    return {
        "job_a_id": int(job_a.id),
        "job_b_id": int(job_b.id),
        "job_a_subtag": job_a.role_subtag,
        "job_b_subtag": job_b.role_subtag,
        "similarity_pct": similarity_pct,
        "shared_skills": sorted(skills_a & skills_b),
        "only_in_job_a_skills": sorted(skills_a - skills_b),
        "only_in_job_b_skills": sorted(skills_b - skills_a),
        "unchanged_lines": unchanged,
        "removed_lines": removed,
        "added_lines": added,
    }

