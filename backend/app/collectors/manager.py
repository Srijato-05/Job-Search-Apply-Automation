"""Central collector coordinator handling dispatch, ATS ingestion, pruning, and telemetry."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import httpx
from sqlmodel import Session, select

from app.collectors.ats_ashby import fetch_ashby_jobs
from app.collectors.ats_greenhouse import fetch_greenhouse_jobs
from app.collectors.ats_lever import fetch_lever_jobs
from app.collectors.ats_smartrecruiters import fetch_smartrecruiters_jobs
from app.collectors.ats_workday import fetch_workday_jobs
from app.collectors.base import BaseCollector, CollectorResult
from app.collectors.jobspy_collector import JobSpyCollector
from app.collectors.pruner import prune_closed_ats_jobs
from app.config import Settings
from app.db.models import CollectorRun, Company, utc_now
from app.pipeline.orchestrator import IngestionResult, RawJobInput, ingest_job
from app.resumes.embedder import EmbedderProtocol
from app.schemas.collectors import CollectorHealthResponse, SourceHealthItem

logger = logging.getLogger(__name__)

_WATCHLIST_SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "watchlist_seed.json"


def seed_watchlist(session: Session) -> tuple[int, int, int]:
    """Seed or synchronize default India Tech Watchlist from seed JSON.

    Returns (seeded_count, updated_count, total_count).
    """
    if not _WATCHLIST_SEED_FILE.exists():
        logger.warning(f"Watchlist seed file not found at {_WATCHLIST_SEED_FILE}")
        return 0, 0, 0

    seed_data = json.loads(_WATCHLIST_SEED_FILE.read_text(encoding="utf-8"))
    seeded = 0
    updated = 0

    for item in seed_data:
        slug = item["slug"]
        existing = session.exec(select(Company).where(Company.slug == slug)).first()
        if existing is None:
            comp = Company(
                slug=slug,
                display_name=item.get("display_name", slug),
                employer_type=item.get("employer_type", "direct_product"),
                ats_type=item.get("ats_type"),
                ats_config_json=item.get("ats_config_json", {}),
                is_watched=item.get("is_watched", True),
                is_blacklisted=item.get("is_blacklisted", False),
                health_status="ok",
            )
            session.add(comp)
            seeded += 1
        else:
            # Sync any updated configs
            existing.display_name = item.get("display_name", existing.display_name)
            existing.employer_type = item.get("employer_type", existing.employer_type)
            existing.ats_type = item.get("ats_type", existing.ats_type)
            if item.get("ats_config_json"):
                existing.ats_config_json = item["ats_config_json"]
            session.add(existing)
            updated += 1

    session.commit()
    total = session.exec(select(Company)).all()
    return seeded, updated, len(total)


class CollectorManager:
    """Coordinates execution across all ATS feeds, JobSpy aggregators, and pruners."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.jobspy = JobSpyCollector(settings=self.settings)

    async def collect_company(
        self,
        session: Session,
        embedder: EmbedderProtocol,
        company: Company,
        client: Optional[httpx.AsyncClient] = None,
        force: bool = False,
    ) -> CollectorResult:
        """Fetch, ingest, and prune jobs for a single company ATS feed."""
        ats_type = (company.ats_type or "").lower().strip()
        collector_source = f"ats_{ats_type}"
        collector = BaseCollector(source_name=collector_source, settings=self.settings)

        # 1. Cooldown check
        if not force:
            cooldown_until = collector.get_active_cooldown(session, company_slug=company.slug)
            if cooldown_until:
                msg = f"Company '{company.display_name}' is in circuit-breaker cooldown until {cooldown_until.isoformat()}."
                logger.info(msg)
                return CollectorResult(
                    status="cooldown",
                    error_message=msg,
                    cooldown_until=cooldown_until,
                )

        run_record = collector.record_run_start(session, company_slug=company.slug)
        cfg = company.ats_config_json or {}

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
            close_client = True

        raw_jobs: list[RawJobInput] = []
        try:
            if ats_type == "greenhouse":
                token = cfg.get("board_token") or company.slug
                raw_jobs = await fetch_greenhouse_jobs(client, token, company.display_name)
            elif ats_type == "lever":
                token = cfg.get("company_name") or company.slug
                raw_jobs = await fetch_lever_jobs(client, token, company.display_name)
            elif ats_type == "ashby":
                token = cfg.get("company_name") or company.slug
                raw_jobs = await fetch_ashby_jobs(client, token, company.display_name)
            elif ats_type == "smartrecruiters":
                cid = cfg.get("company_id") or company.slug
                raw_jobs = await fetch_smartrecruiters_jobs(client, cid, company.display_name)
            elif ats_type == "workday":
                tenant = cfg.get("tenant") or company.slug
                site = cfg.get("site") or "careers"
                inst = cfg.get("instance")
                raw_jobs = await fetch_workday_jobs(client, tenant, site, company.display_name, instance=inst)
            else:
                msg = f"Unsupported ATS type '{ats_type}' for {company.display_name}"
                res = CollectorResult(status="skipped", error_message=msg)
                collector.record_run_finish(session, run_record, res)
                return res

        except httpx.HTTPStatusError as http_err:
            status_code = http_err.response.status_code
            if status_code in (429, 403):
                # Trip circuit breaker for this company
                tripped_run = collector.trip_circuit_breaker(
                    session=session,
                    reason=f"HTTP {status_code} on {company.slug}: {http_err}",
                    company_slug=company.slug,
                    existing_run=run_record,
                )
                return CollectorResult(
                    status="cooldown",
                    error_message=f"HTTP {status_code} triggered cooldown: {http_err}",
                    cooldown_until=tripped_run.cooldown_until,
                )
            else:
                logger.error(f"HTTP error polling {company.slug}: {http_err}")
                res = CollectorResult(status="error", error_message=str(http_err))
                collector.record_run_finish(session, run_record, res)
                return res

        except Exception as e:
            logger.exception(f"Unexpected error polling {company.slug}: {e}")
            res = CollectorResult(status="error", error_message=str(e))
            collector.record_run_finish(session, run_record, res)
            return res

        finally:
            if close_client and client:
                await client.aclose()

        # Ingest fetched jobs through 5-Gate Pipeline
        new_count = 0
        active_ext_ids: set[str] = set()
        active_urls: set[str] = set()

        for raw_job in raw_jobs:
            if company.slug:
                raw_job.portal_metadata["company_slug"] = company.slug
            if raw_job.external_job_id:
                active_ext_ids.add(raw_job.external_job_id)
            if raw_job.job_url:
                active_urls.add(raw_job.job_url)

            try:
                ingest_res: IngestionResult = ingest_job(
                    session=session,
                    raw=raw_job,
                    embedder=embedder,
                    settings=self.settings,
                )
                if ingest_res.action in ("new_role", "sibling_role", "created_new", "created_sibling"):
                    new_count += 1
            except Exception as ingest_err:
                logger.error(f"Failed to ingest job '{raw_job.title}': {ingest_err}")

        # Run closed-job pruner
        closed_count = 0
        if raw_jobs:
            closed_count = prune_closed_ats_jobs(
                session=session,
                company_slug=company.slug,
                active_external_ids=active_ext_ids,
                active_urls=active_urls,
            )

        final_res = CollectorResult(
            fetched_count=len(raw_jobs),
            new_count=new_count,
            closed_count=closed_count,
            status="ok",
        )
        collector.record_run_finish(session, run_record, final_res)
        return final_res

    async def collect_all_watched(
        self,
        session: Session,
        embedder: EmbedderProtocol,
        force: bool = False,
    ) -> list[CollectorResult]:
        """Iterate all watched companies and execute ATS polling sequentially with polite pauses."""
        watched = session.exec(
            select(Company).where(
                Company.is_watched.is_(True),
                Company.is_blacklisted.is_(False),
                Company.ats_type.is_not(None),  # type: ignore[attr-defined]
            )
        ).all()

        results: list[CollectorResult] = []
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            for comp in watched:
                res = await self.collect_company(
                    session=session,
                    embedder=embedder,
                    company=comp,
                    client=client,
                    force=force,
                )
                results.append(res)
                # Polite interval between companies
                await asyncio.sleep(1.0)

        return results

    def get_health_overview(self, session: Session) -> CollectorHealthResponse:
        """Compute system-wide health and cooldown status for all sources."""
        companies = session.exec(
            select(Company).where(Company.ats_type.is_not(None))  # type: ignore[attr-defined]
        ).all()

        sources_out: list[SourceHealthItem] = []
        healthy_count = 0
        cooldown_count = 0
        error_count = 0

        # ATS Companies
        for c in companies:
            # Query last run
            last_run = session.exec(
                select(CollectorRun)
                .where(CollectorRun.company_slug == c.slug)
                .order_by(CollectorRun.id.desc())  # type: ignore[attr-defined]
            ).first()

            now = utc_now()
            in_cooldown = (
                last_run is not None
                and last_run.cooldown_until is not None
                and last_run.cooldown_until > now
            )

            status = "never_run"
            if in_cooldown:
                status = "cooldown"
                cooldown_count += 1
            elif last_run is not None:
                status = last_run.status
                if status == "ok":
                    healthy_count += 1
                elif status in ("error", "failed"):
                    error_count += 1
            else:
                healthy_count += 1

            sources_out.append(
                SourceHealthItem(
                    source_key=f"ats:{c.slug}",
                    source_type="ats",
                    display_name=c.display_name,
                    ats_type=c.ats_type,
                    status=status,
                    last_polled_at=c.last_polled_at,
                    cooldown_until=last_run.cooldown_until if last_run else None,
                    last_fetched_count=last_run.fetched_count if last_run else 0,
                    last_new_count=last_run.new_count if last_run else 0,
                    last_error=last_run.error_message if last_run else None,
                )
            )

        # JobSpy status
        jobspy_run = session.exec(
            select(CollectorRun)
            .where(CollectorRun.source_name == "jobspy")
            .order_by(CollectorRun.id.desc())  # type: ignore[attr-defined]
        ).first()

        jobspy_status = "ok"
        jobspy_cooldown: Optional[datetime] = None
        if jobspy_run:
            if jobspy_run.cooldown_until and jobspy_run.cooldown_until > utc_now():
                jobspy_status = "cooldown"
                jobspy_cooldown = jobspy_run.cooldown_until
                cooldown_count += 1
            elif jobspy_run.status == "error":
                jobspy_status = "error"
                error_count += 1
            else:
                healthy_count += 1
        else:
            jobspy_status = "never_run"
            healthy_count += 1

        sources_out.append(
            SourceHealthItem(
                source_key="jobspy:aggregator",
                source_type="jobspy",
                display_name="JobSpy (Naukri / LinkedIn / Indeed / Glassdoor)",
                ats_type=None,
                status=jobspy_status,
                last_polled_at=jobspy_run.finished_at if jobspy_run else None,
                cooldown_until=jobspy_cooldown,
                last_fetched_count=jobspy_run.fetched_count if jobspy_run else 0,
                last_new_count=jobspy_run.new_count if jobspy_run else 0,
                last_error=jobspy_run.error_message if jobspy_run else None,
            )
        )

        return CollectorHealthResponse(
            total_sources=len(sources_out),
            healthy_sources=healthy_count,
            cooldown_sources=cooldown_count,
            error_sources=error_count,
            sources=sources_out,
        )

