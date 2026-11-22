"""JobSpy multi-portal collector with polite jitter, query rotation, and credential safety."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Optional

from sqlmodel import Session, select

from app.collectors.base import BaseCollector, CollectorResult
from app.config import Settings
from app.db.models import JobSource, Resume
from app.pipeline.orchestrator import IngestionResult, RawJobInput, ingest_job
from app.resumes.embedder import EmbedderProtocol

logger = logging.getLogger(__name__)

try:
    from jobspy import scrape_jobs  # type: ignore[import-untyped]
    JOBSPY_AVAILABLE = True
except ImportError:
    scrape_jobs = None
    JOBSPY_AVAILABLE = False


class JobSpyCollector(BaseCollector):
    """Orchestrates polite scraping across Naukri, LinkedIn, Indeed, Glassdoor, and Google."""

    def __init__(self, settings: Optional[Settings] = None):
        super().__init__(source_name="jobspy", settings=settings)

    async def run(
        self,
        session: Session,
        embedder: EmbedderProtocol,
        sites: Optional[list[str]] = None,
        search_terms: Optional[list[str]] = None,
        locations: Optional[list[str]] = None,
        results_per_site: int = 15,
        hours_old: int = 24,
    ) -> CollectorResult:
        """Run JobSpy search queries politely with random jitter and deduplication."""
        if not JOBSPY_AVAILABLE or scrape_jobs is None:
            msg = "python-jobspy is not installed. Run 'pip install python-jobspy' in the virtualenv to enable Tier 1 aggregators."
            logger.warning(msg)
            return CollectorResult(
                fetched_count=0,
                new_count=0,
                closed_count=0,
                status="skipped",
                error_message=msg,
            )

        # Check circuit-breaker cooldown
        cooldown_until = self.get_active_cooldown(session)
        if cooldown_until:
            msg = f"JobSpy is currently in cooldown until {cooldown_until.isoformat()}"
            logger.info(msg)
            return CollectorResult(
                fetched_count=0,
                new_count=0,
                closed_count=0,
                status="cooldown",
                error_message=msg,
                cooldown_until=cooldown_until,
            )

        run_record = self.record_run_start(session)

        # Target sites (defaults from Settings, including Naukri)
        target_sites = sites or self.settings.jobspy_sites_list

        # Derive search queries and locations from active resumes if not explicitly provided
        terms: list[str] = search_terms or []
        locs: list[str] = locations or []

        if not terms or not locs:
            active_resumes = session.exec(select(Resume).where(Resume.is_active.is_(True))).all()
            for r in active_resumes:
                if not terms and r.target_titles_json:
                    terms.extend(r.target_titles_json)
                if not locs and r.search_locations_json:
                    locs.extend(r.search_locations_json)

        if not terms:
            terms = ["Software Engineer", "Backend Developer", "Full Stack Developer"]
        if not locs:
            locs = ["Bengaluru, India", "Hyderabad, India", "Pune, India"]

        total_fetched = 0
        total_new = 0
        caught_error: Optional[str] = None

        try:
            for term in terms[:3]:  # Bounded query terms per run
                for loc in locs[:2]:  # Bounded locations per run
                    # Polite jitter before initiating scraper
                    jitter = random.uniform(
                        self.settings.jobspy_min_delay_sec,
                        self.settings.jobspy_max_delay_sec,
                    )
                    await asyncio.sleep(jitter)

                    logger.info(f"Running JobSpy: term='{term}', location='{loc}', sites={target_sites}")

                    try:
                        # scrape_jobs is synchronous, execute in thread pool to avoid blocking asyncio loop
                        df = await asyncio.to_thread(
                            scrape_jobs,
                            site_name=target_sites,
                            search_term=term,
                            location=loc,
                            results_wanted=results_per_site,
                            hours_old=hours_old,
                            country_indeed="india",
                        )
                    except Exception as scrape_err:
                        err_str = str(scrape_err).lower()
                        if "429" in err_str or "rate limit" in err_str or "challenge" in err_str or "captcha" in err_str:
                            self.trip_circuit_breaker(
                                session,
                                reason=f"JobSpy triggered rate limit/challenge: {scrape_err}",
                            )
                            return CollectorResult(
                                fetched_count=total_fetched,
                                new_count=total_new,
                                status="cooldown",
                                error_message=f"Rate limit triggered: {scrape_err}",
                            )
                        logger.error(f"JobSpy query failed for '{term}' at '{loc}': {scrape_err}")
                        continue

                    if df is None or getattr(df, "empty", True):
                        continue

                    # Process scraped rows
                    for _, row in df.iterrows():
                        job_url = str(row.get("job_url", "")).strip()
                        if not job_url:
                            continue

                        total_fetched += 1

                        # Dedup check against existing sources
                        existing_src = session.exec(
                            select(JobSource).where(JobSource.job_url == job_url)
                        ).first()
                        if existing_src:
                            continue

                        raw_input = RawJobInput(
                            title=str(row.get("title", "")).strip(),
                            company_name=str(row.get("company", "")).strip(),
                            description_raw=str(row.get("description", "")).strip(),
                            location_raw=str(row.get("location", "")).strip(),
                            portal_name=str(row.get("site", "jobspy")).lower(),
                            external_job_id=str(row.get("id", "")) or None,
                            job_url=job_url,
                            apply_url=str(row.get("job_url_direct", "")).strip() or job_url,
                        )

                        if not raw_input.title or not raw_input.company_name or not raw_input.description_raw:
                            continue

                        res: IngestionResult = ingest_job(
                            session=session,
                            raw=raw_input,
                            embedder=embedder,
                            settings=self.settings,
                        )
                        if res.action in ("new_role", "sibling_role", "created_new", "created_sibling"):
                            total_new += 1

        except Exception as e:
            caught_error = str(e)
            logger.exception(f"JobSpy batch collection failed: {e}")

        status = "error" if caught_error and total_fetched == 0 else "ok"
        result = CollectorResult(
            fetched_count=total_fetched,
            new_count=total_new,
            closed_count=0,
            status=status,
            error_message=caught_error,
        )
        self.record_run_finish(session, run_record, result)
        return result

