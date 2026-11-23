"""Comprehensive Collector, JobSpy, Retry, Lock, Scheduler, and Watchlist API tests."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.collectors import jobspy_collector
from app.collectors.jobspy_collector import JobSpyCollector
from app.collectors.manager import CollectorManager
from app.config import Settings
from app.db.models import CollectorRun, Company, Job
from tests.conftest import DeterministicTestEmbedder


def test_collector_5xx_retry_and_concurrent_batch_handling(tmp_path) -> None:
    """Verify 5xx retry recovery, 403 circuit breaker, 404 invalid_config, and 200 success in one sweep."""
    from sqlmodel import SQLModel, create_engine
    from sqlmodel.pool import StaticPool

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        c_retry = Company(
            slug="retry-co",
            display_name="Retry Co",
            ats_type="greenhouse",
            ats_config_json={"board_token": "retry-co"},
            is_watched=True,
        )
        c_403 = Company(
            slug="blocked-co",
            display_name="Blocked Co",
            ats_type="lever",
            ats_config_json={"company_name": "blocked-co"},
            is_watched=True,
        )
        c_404 = Company(
            slug="missing-co",
            display_name="Missing Co",
            ats_type="ashby",
            ats_config_json={"company_name": "missing-co"},
            is_watched=True,
        )
        session.add_all([c_retry, c_403, c_404])
        session.commit()

        call_counts = {"retry": 0, "403": 0, "404": 0}

        async def _fake_fetch(company: Company, client, known_external_ids=None, force_refresh_details=False):
            if company.slug == "retry-co":
                call_counts["retry"] += 1
                if call_counts["retry"] < 2:
                    req = httpx.Request("GET", "https://boards-api.greenhouse.io/retry-co")
                    raise httpx.HTTPStatusError("503", request=req, response=httpx.Response(503, request=req))
                from app.pipeline.orchestrator import RawJobInput
                return [
                    RawJobInput(
                        title="Backend Engineer",
                        company_name="Retry Co",
                        description_raw="Build Python and FastAPI microservices in Bengaluru.",
                        location_raw="Bengaluru, India",
                        portal_name="greenhouse",
                        external_job_id="rc-1",
                        job_url="https://boards.greenhouse.io/retry-co/jobs/1",
                    )
                ]
            if company.slug == "blocked-co":
                call_counts["403"] += 1
                req = httpx.Request("GET", "https://api.lever.co/blocked-co")
                raise httpx.HTTPStatusError("403", request=req, response=httpx.Response(403, request=req))
            call_counts["404"] += 1
            req = httpx.Request("GET", "https://api.ashbyhq.com/missing-co")
            raise httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))

        async def _fast_sleep(_sec):
            return None

        async def _run():
            manager = CollectorManager(settings=Settings(data_dir=tmp_path))
            with patch.object(manager, "_fetch_company_raw", side_effect=_fake_fetch), patch(
                "app.collectors.manager.asyncio.sleep", side_effect=_fast_sleep
            ):
                results = await manager.collect_all_watched(
                    session, DeterministicTestEmbedder(), force=True, resume_window_minutes=0
                )
            return results

        res = asyncio.run(_run())
        statuses = {r.status for r in res}
        assert statuses == {"ok", "cooldown", "invalid_config"}
        assert call_counts["retry"] == 2
        assert call_counts["403"] == 1  # 403 must NOT retry
        assert call_counts["404"] == 1  # 404 must NOT retry

        assert session.exec(select(Job).where(Job.company_slug == "retry-co")).first() is not None


def test_jobspy_collector_mocked_multi_portal_and_rate_limit(tmp_path) -> None:
    """Verify JobSpyCollector ingests Naukri/LinkedIn/Indeed/Glassdoor rows, deduplicates, and trips breaker on 429."""
    from sqlmodel import SQLModel, create_engine
    from sqlmodel.pool import StaticPool

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    df = pd.DataFrame(
        [
            {
                "site": "naukri",
                "id": "nk-1",
                "title": "SDE II Backend",
                "company": "Swiggy",
                "location": "Bengaluru, India",
                "description": "Python FastAPI Kafka developer for Swiggy.",
                "job_url": "https://www.naukri.com/job/swiggy-1",
                "job_url_direct": "https://www.naukri.com/job/swiggy-1",
            },
            {
                "site": "glassdoor",
                "id": "gd-1",
                "title": "Backend Engineer",
                "company": "CRED",
                "location": "Bengaluru, India",
                "description": "Python PostgreSQL microservices at CRED.",
                "job_url": "https://www.glassdoor.co.in/job/cred-1",
                "job_url_direct": "",
            },
            {
                "site": "linkedin",
                "id": "li-missing-desc",
                "title": "Incomplete Row",
                "company": "NoDescCorp",
                "location": "Pune",
                "description": "",  # Should be skipped safely
                "job_url": "https://www.linkedin.com/jobs/view/000",
                "job_url_direct": "",
            },
        ]
    )

    async def _no_sleep(_sec):
        return None

    with Session(engine) as session:
        collector = JobSpyCollector(settings=Settings(data_dir=tmp_path, jobspy_min_delay_sec=0.0, jobspy_max_delay_sec=0.0))

        async def _run_ok():
            with patch.object(jobspy_collector, "JOBSPY_AVAILABLE", True), patch.object(
                jobspy_collector, "scrape_jobs", return_value=df
            ), patch("app.collectors.jobspy_collector.asyncio.sleep", side_effect=_no_sleep):
                return await collector.run(
                    session,
                    DeterministicTestEmbedder(),
                    sites=["naukri", "glassdoor", "linkedin"],
                    search_terms=["Backend Engineer"],
                    locations=["Bengaluru, India"],
                )

        res1 = asyncio.run(_run_ok())
        assert res1.status == "ok"
        assert res1.fetched_count == 3
        assert res1.new_count == 2

        # Second run with rate-limit/CAPTCHA exception -> trips circuit breaker
        async def _run_429():
            with patch.object(jobspy_collector, "JOBSPY_AVAILABLE", True), patch.object(
                jobspy_collector, "scrape_jobs", side_effect=RuntimeError("HTTP 429 CAPTCHA challenge")
            ), patch("app.collectors.jobspy_collector.asyncio.sleep", side_effect=_no_sleep):
                return await collector.run(
                    session,
                    DeterministicTestEmbedder(),
                    search_terms=["Backend Engineer"],
                    locations=["Bengaluru, India"],
                )

        res2 = asyncio.run(_run_429())
        assert res2.status == "cooldown"

        # Immediate third run blocked by active cooldown without calling scrape_jobs
        with patch.object(jobspy_collector, "JOBSPY_AVAILABLE", True), patch.object(
            jobspy_collector, "scrape_jobs", side_effect=AssertionError("Should not scrape during cooldown")
        ):
            res3 = asyncio.run(collector.run(session, DeterministicTestEmbedder()))
        assert res3.status == "cooldown"


def test_collector_409_overlap_lock_and_manual_scheduler_endpoints(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify 409 lock rejection when sweep active + manual scheduler /status, /start, /stop."""
    # Manual scheduler defaults to OFF in tests
    r_sched0 = client.get("/api/v1/collectors/scheduler", headers=auth_headers)
    assert r_sched0.status_code == 200
    assert r_sched0.json()["running"] is False

    # Start scheduler via HTTP endpoint without requiring an active ASGI event loop for create_task
    with patch.object(client.app.state.scheduler, "start", new_callable=MagicMock) as mock_start:
        r_start = client.post("/api/v1/collectors/scheduler/start", headers=auth_headers)
        assert r_start.status_code == 200
        assert mock_start.called

    r_stop = client.post("/api/v1/collectors/scheduler/stop", headers=auth_headers)
    assert r_stop.status_code == 200
    assert r_stop.json()["running"] is False

    # Simulate in-progress lock -> POST /collectors/run returns 409 Conflict
    client.app.state.collection_progress.begin(target="ats", total=10, phase="ats")
    try:
        r_conflict = client.post(
            "/api/v1/collectors/run",
            headers=auth_headers,
            json={"source": "ats"},
        )
        assert r_conflict.status_code == 409
    finally:
        client.app.state.collection_progress.finish()

    # Unknown company slug returns 404
    r_missing = client.post(
        "/api/v1/collectors/run",
        headers=auth_headers,
        json={"source": "nonexistent-company-slug-xyz"},
    )
    assert r_missing.status_code == 404


def test_watchlist_duplicate_conflict_and_verify_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify watchlist upsert on existing slug returns 201 and 404 for missing patch/delete."""
    payload = {
        "slug": "razorpay",  # already seeded
        "display_name": "Razorpay Dup",
        "ats_type": "greenhouse",
        "ats_config_json": {"board_token": "razorpay"},
    }
    r_dup = client.post("/api/v1/watchlist", headers=auth_headers, json=payload)
    assert r_dup.status_code == 201
    assert r_dup.json()["display_name"] == "Razorpay Dup"

    # Missing company patch/delete returns 404
    assert client.patch("/api/v1/watchlist/nope-slug", headers=auth_headers, json={"display_name": "X"}).status_code == 404
    assert client.delete("/api/v1/watchlist/nope-slug", headers=auth_headers).status_code == 404
