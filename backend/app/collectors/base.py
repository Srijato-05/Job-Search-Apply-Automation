"""Base collector class with circuit breaker, rate limiting, and telemetry logging."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.config import Settings
from app.db.models import CollectorRun, Company, utc_now

logger = logging.getLogger(__name__)


@dataclass
class CollectorResult:
    """Outcome metrics of a collector execution run."""

    fetched_count: int = 0
    new_count: int = 0
    closed_count: int = 0
    status: str = "ok"
    error_message: Optional[str] = None
    cooldown_until: Optional[datetime] = None


class BaseCollector:
    """Base class for all ATS and JobSpy collectors with circuit breaker guards."""

    def __init__(self, source_name: str, settings: Optional[Settings] = None):
        self.source_name = source_name
        self.settings = settings or Settings()

    def get_active_cooldown(
        self, session: Session, company_slug: Optional[str] = None
    ) -> Optional[datetime]:
        """Check if this source or company is currently in circuit-breaker cooldown."""
        now = utc_now()
        stmt = (
            select(CollectorRun)
            .where(
                CollectorRun.source_name == self.source_name,
                CollectorRun.cooldown_until.is_not(None),  # type: ignore[attr-defined]
                CollectorRun.cooldown_until > now,  # type: ignore[operator]
            )
        )
        if company_slug:
            stmt = stmt.where(CollectorRun.company_slug == company_slug)

        stmt = stmt.order_by(CollectorRun.id.desc())  # type: ignore[attr-defined]
        active_cooldown = session.exec(stmt).first()
        if active_cooldown and active_cooldown.cooldown_until:
            return active_cooldown.cooldown_until
        return None

    def trip_circuit_breaker(
        self,
        session: Session,
        reason: str,
        cooldown_hours: Optional[int] = None,
        company_slug: Optional[str] = None,
        existing_run: Optional[CollectorRun] = None,
    ) -> CollectorRun:
        """Trip circuit breaker on 429/403/CAPTCHA, setting cooldown_until."""
        hours = cooldown_hours or self.settings.circuit_breaker_cooldown_hours
        cooldown_target = utc_now() + timedelta(hours=hours)

        logger.warning(
            f"Circuit breaker tripped for {self.source_name} (slug={company_slug}): "
            f"{reason}. Cooldown until {cooldown_target.isoformat()}."
        )

        run = existing_run or CollectorRun(
            source_name=self.source_name,
            company_slug=company_slug,
            started_at=utc_now(),
        )
        run.status = "cooldown"
        run.cooldown_until = cooldown_target
        run.error_message = reason
        run.finished_at = utc_now()
        session.add(run)

        if company_slug:
            company = session.exec(
                select(Company).where(Company.slug == company_slug)
            ).first()
            if company:
                company.health_status = "cooldown"
                session.add(company)

        session.commit()
        session.refresh(run)
        return run

    def record_run_start(
        self, session: Session, company_slug: Optional[str] = None
    ) -> CollectorRun:
        """Initialize a new collector run record."""
        run = CollectorRun(
            source_name=self.source_name,
            company_slug=company_slug,
            status="running",
            started_at=utc_now(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    def record_run_finish(
        self,
        session: Session,
        run: CollectorRun,
        result: CollectorResult,
    ) -> CollectorRun:
        """Update run record with completion stats."""
        run.status = result.status
        run.fetched_count = result.fetched_count
        run.new_count = result.new_count
        run.closed_count = result.closed_count
        run.error_message = result.error_message
        run.cooldown_until = result.cooldown_until
        run.finished_at = utc_now()
        session.add(run)

        # Update company last_polled_at and health status
        if run.company_slug:
            company = session.exec(
                select(Company).where(Company.slug == run.company_slug)
            ).first()
            if company:
                company.last_polled_at = run.finished_at
                company.health_status = "ok" if result.status == "ok" else result.status
                session.add(company)

        session.commit()
        session.refresh(run)
        return run

