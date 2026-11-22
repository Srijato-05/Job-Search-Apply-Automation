"""Central collector coordinator handling dispatch, ATS ingestion, pruning, and telemetry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from app.collectors.ats_workday import _build_workday_cxs_base_url, fetch_workday_jobs
from app.collectors.base import BaseCollector, CollectorResult
from app.collectors.jobspy_collector import JobSpyCollector
from app.collectors.pruner import prune_closed_ats_jobs
from app.config import Settings
from app.db.models import CollectorRun, Company, Job, JobSource, utc_now
from app.pipeline.orchestrator import IngestionResult, RawJobInput, ingest_job
from app.resumes.embedder import EmbedderProtocol
from app.schemas.collectors import (
    CollectorHealthResponse,
    CollectorProgressResponse,
    SourceHealthItem,
)
from app.schemas.watchlist import WatchlistVerifyItem, WatchlistVerifyResponse

logger = logging.getLogger(__name__)

_WATCHLIST_SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "watchlist_seed.json"


@dataclass
class CollectionProgress:
    """In-memory live progress state for background or on-demand collection sweeps."""

    running: bool = False
    target: Optional[str] = None
    phase: str = "idle"
    completed: int = 0
    total: int = 0
    current_item: Optional[str] = None
    fetched_so_far: int = 0
    new_so_far: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def begin(self, target: str, total: int, phase: str = "ats") -> None:
        self.running = True
        self.target = target
        self.phase = phase
        self.completed = 0
        self.total = total
        self.current_item = None
        self.fetched_so_far = 0
        self.new_so_far = 0
        self.started_at = utc_now()
        self.finished_at = None

    def advance(self, item: str, fetched: int = 0, new: int = 0) -> None:
        self.completed += 1
        self.current_item = item
        self.fetched_so_far += fetched
        self.new_so_far += new

    def finish(self) -> None:
        self.running = False
        self.phase = "idle"
        self.current_item = None
        self.finished_at = utc_now()

    def snapshot(self) -> CollectorProgressResponse:
        return CollectorProgressResponse(
            running=self.running,
            target=self.target,
            phase=self.phase,
            completed=self.completed,
            total=self.total,
            current_item=self.current_item,
            fetched_so_far=self.fetched_so_far,
            new_so_far=self.new_so_far,
            started_at=self.started_at,
            finished_at=self.finished_at,
        )


def recover_stale_runs(session: Session) -> int:
    """Mark any collector_runs stuck in 'running' (e.g. from crash/restart) as 'interrupted'."""
    stale = list(
        session.exec(select(CollectorRun).where(CollectorRun.status == "running")).all()
    )
    now = utc_now()
    for run in stale:
        run.status = "interrupted"
        run.finished_at = now
        run.error_message = run.error_message or "Interrupted by server shutdown or restart"
        session.add(run)
    if stale:
        session.commit()
    return len(stale)


def _get_known_external_ids(session: Session, company_slug: str) -> set[str]:
    """Return known external_job_ids for a company so detail fetches can be incremental."""
    rows = session.exec(
        select(JobSource.external_job_id)
        .join(Job, Job.id == JobSource.job_id)  # type: ignore[arg-type]
        .where(
            Job.company_slug == company_slug,
            JobSource.external_job_id.is_not(None),  # type: ignore[attr-defined]
        )
    ).all()
    return {str(r) for r in rows if r}


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
            elif status_code == 404:
                msg = f"HTTP 404 (ATS board/endpoint not found) for {company.slug}: {http_err}"
                logger.warning(msg)
                res = CollectorResult(status="invalid_config", error_message=msg)
                collector.record_run_finish(session, run_record, res)
                return res
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

    async def _fetch_company_raw_with_retry(
        self,
        company: Company,
        client: httpx.AsyncClient,
        known_external_ids: Optional[set[str]] = None,
        force_refresh_details: bool = False,
        retry_delays: tuple[float, ...] = (1.0, 3.0),
    ) -> list[RawJobInput]:
        """Fetch raw ATS jobs with short retries strictly on transient 5xx/timeouts.

        Never retries 404 (invalid_config) or 429/403 (circuit breaker).
        """
        attempt = 0
        while True:
            try:
                return await self._fetch_company_raw(
                    company,
                    client,
                    known_external_ids=known_external_ids,
                    force_refresh_details=force_refresh_details,
                )
            except httpx.HTTPStatusError as http_err:
                code = http_err.response.status_code
                if code >= 500 and attempt < len(retry_delays):
                    delay = retry_delays[attempt]
                    logger.warning(
                        f"Transient HTTP {code} for {company.slug}; retrying in {delay}s (attempt {attempt + 1}/{len(retry_delays)})."
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as net_err:
                if attempt < len(retry_delays):
                    delay = retry_delays[attempt]
                    logger.warning(
                        f"Transient network error for {company.slug} ({net_err}); retrying in {delay}s (attempt {attempt + 1}/{len(retry_delays)})."
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise

    async def _fetch_company_raw(
        self,
        company: Company,
        client: httpx.AsyncClient,
        known_external_ids: Optional[set[str]] = None,
        force_refresh_details: bool = False,
    ) -> list[RawJobInput]:
        """Dispatch HTTP fetch to the appropriate ATS connector."""
        ats_type = (company.ats_type or "").lower().strip()
        cfg = company.ats_config_json or {}
        if ats_type == "greenhouse":
            return await fetch_greenhouse_jobs(client, cfg.get("board_token") or company.slug, company.display_name)
        if ats_type == "lever":
            return await fetch_lever_jobs(client, cfg.get("company_name") or company.slug, company.display_name)
        if ats_type == "ashby":
            return await fetch_ashby_jobs(client, cfg.get("company_name") or company.slug, company.display_name)
        if ats_type == "smartrecruiters":
            return await fetch_smartrecruiters_jobs(
                client,
                cfg.get("company_id") or company.slug,
                company.display_name,
                known_external_ids=known_external_ids,
                force_refresh_details=force_refresh_details,
            )
        if ats_type == "workday":
            return await fetch_workday_jobs(
                client,
                cfg.get("tenant") or company.slug,
                cfg.get("site") or "careers",
                company.display_name,
                instance=cfg.get("instance"),
                known_external_ids=known_external_ids,
                force_refresh_details=force_refresh_details,
            )
        raise ValueError(f"Unsupported ATS type '{ats_type}' for {company.display_name}")

    async def collect_all_watched(
        self,
        session: Session,
        embedder: EmbedderProtocol,
        force: bool = False,
        resume_window_minutes: int = 30,
        force_refresh_details: bool = False,
        progress: Optional[CollectionProgress] = None,
    ) -> list[CollectorResult]:
        """Fetch watched ATS feeds concurrently (bounded by Semaphore), then ingest/prune safely.

        Supports resumable sweep checkpoints: when `force=False`, companies already successfully
        polled within the last `resume_window_minutes` are skipped so an interrupted sweep
        picks up where it left off.
        """
        watched = list(
            session.exec(
                select(Company).where(
                    Company.is_watched.is_(True),
                    Company.is_blacklisted.is_(False),
                    Company.ats_type.is_not(None),  # type: ignore[attr-defined]
                )
            ).all()
        )
        if not watched:
            return []

        if progress is not None:
            progress.begin(target="ats", total=len(watched), phase="ats")

        sem = asyncio.Semaphore(max(1, self.settings.collector_max_concurrency))
        timeout = max(5.0, float(self.settings.ats_http_timeout_sec))
        now = utc_now()
        resume_cutoff = now - timedelta(minutes=resume_window_minutes)

        # Pre-check cooldowns, resumable checkpoints, and known IDs sequentially on DB session
        eligible: list[tuple[Company, BaseCollector, CollectorRun, set[str]]] = []
        results: list[CollectorResult] = []
        for comp in watched:
            ats_type = (comp.ats_type or "").lower().strip()
            collector = BaseCollector(source_name=f"ats_{ats_type}", settings=self.settings)

            if not force:
                cooldown_until = collector.get_active_cooldown(session, company_slug=comp.slug)
                if cooldown_until:
                    results.append(
                        CollectorResult(
                            status="cooldown",
                            error_message=f"Company '{comp.display_name}' is in circuit-breaker cooldown until {cooldown_until.isoformat()}.",
                            cooldown_until=cooldown_until,
                        )
                    )
                    if progress is not None:
                        progress.advance(comp.display_name)
                    continue

                # Resumable sweep checkpoint: skip recently succeeded companies
                if (
                    resume_window_minutes > 0
                    and comp.health_status == "ok"
                    and comp.last_polled_at is not None
                ):
                    polled_at = comp.last_polled_at
                    if polled_at.tzinfo is None:
                        polled_at = polled_at.replace(tzinfo=now.tzinfo)
                    if polled_at >= resume_cutoff:
                        results.append(
                            CollectorResult(
                                status="skipped_recent",
                                error_message=f"Already polled within last {resume_window_minutes}m (checkpoint).",
                            )
                        )
                        if progress is not None:
                            progress.advance(comp.display_name)
                        continue

            known_ids = _get_known_external_ids(session, comp.slug)
            run_record = collector.record_run_start(session, company_slug=comp.slug)
            eligible.append((comp, collector, run_record, known_ids))

        async def _bounded_fetch(comp: Company, known_ids: set[str], client: httpx.AsyncClient):
            async with sem:
                try:
                    return (
                        comp,
                        await self._fetch_company_raw_with_retry(
                            comp,
                            client,
                            known_external_ids=known_ids,
                            force_refresh_details=force_refresh_details,
                        ),
                        None,
                    )
                except Exception as exc:
                    return comp, None, exc

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            fetched_outcomes = await asyncio.gather(
                *(_bounded_fetch(comp, known_ids, client) for comp, _, _, known_ids in eligible)
            )

        # Ingest, prune, and record telemetry sequentially on the SQLite session
        for (comp, collector, run_record, _), (_, raw_jobs, err) in zip(eligible, fetched_outcomes):
            if err is not None:
                if isinstance(err, httpx.HTTPStatusError):
                    code = err.response.status_code
                    if code in (429, 403):
                        tripped = collector.trip_circuit_breaker(
                            session=session,
                            reason=f"HTTP {code} on {comp.slug}: {err}",
                            company_slug=comp.slug,
                            existing_run=run_record,
                        )
                        results.append(
                            CollectorResult(
                                status="cooldown",
                                error_message=f"HTTP {code} triggered cooldown: {err}",
                                cooldown_until=tripped.cooldown_until,
                            )
                        )
                        if progress is not None:
                            progress.advance(comp.display_name)
                        continue
                    if code == 404:
                        res = CollectorResult(
                            status="invalid_config",
                            error_message=f"HTTP 404 (ATS board/endpoint not found) for {comp.slug}: {err}",
                        )
                        collector.record_run_finish(session, run_record, res)
                        results.append(res)
                        if progress is not None:
                            progress.advance(comp.display_name)
                        continue
                res = CollectorResult(status="error", error_message=str(err))
                collector.record_run_finish(session, run_record, res)
                results.append(res)
                if progress is not None:
                    progress.advance(comp.display_name)
                continue

            jobs_list = raw_jobs or []
            new_count = 0
            active_ext_ids: set[str] = set()
            active_urls: set[str] = set()
            for raw_job in jobs_list:
                if comp.slug:
                    raw_job.portal_metadata["company_slug"] = comp.slug
                if raw_job.external_job_id:
                    active_ext_ids.add(raw_job.external_job_id)
                if raw_job.job_url:
                    active_urls.add(raw_job.job_url)
                try:
                    ingest_res = ingest_job(
                        session=session,
                        raw=raw_job,
                        embedder=embedder,
                        settings=self.settings,
                    )
                    if ingest_res.action in ("new_role", "sibling_role", "created_new", "created_sibling"):
                        new_count += 1
                except Exception as ingest_err:
                    logger.error(f"Failed to ingest job '{raw_job.title}': {ingest_err}")

            closed_count = (
                prune_closed_ats_jobs(
                    session=session,
                    company_slug=comp.slug,
                    active_external_ids=active_ext_ids,
                    active_urls=active_urls,
                )
                if jobs_list
                else 0
            )
            final_res = CollectorResult(
                fetched_count=len(jobs_list),
                new_count=new_count,
                closed_count=closed_count,
                status="ok",
            )
            collector.record_run_finish(session, run_record, final_res)
            results.append(final_res)
            if progress is not None:
                progress.advance(comp.display_name, fetched=len(jobs_list), new=new_count)

        if progress is not None:
            progress.finish()

        return results

    async def verify_watchlist_boards(
        self,
        session: Session,
        client: Optional[httpx.AsyncClient] = None,
    ) -> WatchlistVerifyResponse:
        """Lightweight concurrent probe of all watched ATS board tokens without ingestion."""
        watched = list(
            session.exec(
                select(Company).where(
                    Company.is_watched.is_(True),
                    Company.is_blacklisted.is_(False),
                    Company.ats_type.is_not(None),  # type: ignore[attr-defined]
                )
            ).all()
        )
        sem = asyncio.Semaphore(max(1, self.settings.collector_max_concurrency))
        timeout = min(10.0, float(self.settings.ats_http_timeout_sec))

        async def _probe(comp: Company, http_client: httpx.AsyncClient) -> WatchlistVerifyItem:
            ats_type = (comp.ats_type or "").lower().strip()
            cfg = comp.ats_config_json or {}
            async with sem:
                try:
                    if ats_type == "greenhouse":
                        token = cfg.get("board_token") or comp.slug
                        resp = await http_client.get(
                            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false",
                            timeout=timeout,
                        )
                    elif ats_type == "lever":
                        token = cfg.get("company_name") or comp.slug
                        resp = await http_client.get(
                            f"https://api.lever.co/v0/postings/{token}?mode=json&limit=1",
                            timeout=timeout,
                        )
                    elif ats_type == "ashby":
                        token = cfg.get("company_name") or comp.slug
                        resp = await http_client.get(
                            f"https://api.ashbyhq.com/posting-api/job-board/{token}",
                            timeout=timeout,
                        )
                    elif ats_type == "smartrecruiters":
                        cid = cfg.get("company_id") or comp.slug
                        resp = await http_client.get(
                            f"https://api.smartrecruiters.com/v1/companies/{cid}/postings?limit=1",
                            timeout=timeout,
                        )
                    elif ats_type == "workday":
                        base = _build_workday_cxs_base_url(
                            cfg.get("tenant") or comp.slug,
                            cfg.get("site") or "careers",
                            cfg.get("instance"),
                        )
                        resp = await http_client.post(
                            f"{base}/jobs",
                            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                            timeout=timeout,
                        )
                    else:
                        return WatchlistVerifyItem(
                            slug=comp.slug,
                            display_name=comp.display_name,
                            ats_type=ats_type,
                            status="invalid_config",
                            detail=f"Unsupported ATS type '{ats_type}'",
                        )

                    code = resp.status_code
                    if code == 200:
                        status_str = "ok"
                        detail = None
                    elif code == 404:
                        status_str = "invalid_config"
                        detail = "HTTP 404: Board token or endpoint not found"
                    elif code in (429, 403):
                        status_str = "cooldown"
                        detail = f"HTTP {code}: Rate limited or blocked"
                    else:
                        status_str = "error"
                        detail = f"HTTP {code}"
                    return WatchlistVerifyItem(
                        slug=comp.slug,
                        display_name=comp.display_name,
                        ats_type=ats_type,
                        status=status_str,
                        http_status=code,
                        detail=detail,
                    )
                except Exception as exc:
                    return WatchlistVerifyItem(
                        slug=comp.slug,
                        display_name=comp.display_name,
                        ats_type=ats_type,
                        status="error",
                        detail=str(exc),
                    )

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
            close_client = True
        try:
            items = list(await asyncio.gather(*(_probe(c, client) for c in watched)))
        finally:
            if close_client:
                await client.aclose()

        # Persist updated health_status back to SQLite
        comp_by_slug = {c.slug: c for c in watched}
        for item in items:
            comp_row = comp_by_slug.get(item.slug)
            if comp_row is not None:
                comp_row.health_status = item.status
                session.add(comp_row)
        session.commit()

        return WatchlistVerifyResponse(
            total_checked=len(items),
            valid_count=sum(1 for i in items if i.status == "ok"),
            invalid_count=sum(1 for i in items if i.status == "invalid_config"),
            cooldown_count=sum(1 for i in items if i.status == "cooldown"),
            error_count=sum(1 for i in items if i.status == "error"),
            results=items,
        )

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
                elif status in ("error", "failed", "invalid_config"):
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

