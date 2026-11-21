"""Closed-job pruner detecting vanished postings from direct ATS feeds."""

from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, select

from app.db.models import Job, JobSource

logger = logging.getLogger(__name__)


def prune_closed_ats_jobs(
    session: Session,
    company_slug: str,
    active_external_ids: set[str],
    active_urls: set[str],
) -> int:
    """Identify active jobs for an ATS company that vanished from the latest feed.

    Marks their status as 'closed' in the database and returns the count of closed jobs.
    """
    if not active_external_ids and not active_urls:
        logger.warning(f"Pruner received empty active set for {company_slug}; skipping to prevent mass closure.")
        return 0

    active_jobs = session.exec(
        select(Job).where(
            Job.company_slug == company_slug,
            Job.status == "active",
        )
    ).all()

    closed_count = 0
    for job in active_jobs:
        # Check all sources linked to this job
        sources = session.exec(
            select(JobSource).where(JobSource.job_id == job.id)
        ).all()

        is_present = False

        # If job req_id matches any active external id
        if job.req_id and job.req_id in active_external_ids:
            is_present = True

        for src in sources:
            if src.external_job_id and src.external_job_id in active_external_ids:
                is_present = True
                break
            if src.job_url and src.job_url in active_urls:
                is_present = True
                break

        if not is_present:
            job.status = "closed"
            session.add(job)
            closed_count += 1
            logger.info(f"Marked vanished job #{job.id} ({job.title} at {job.company_name}) as closed.")

    if closed_count > 0:
        session.commit()

    return closed_count

