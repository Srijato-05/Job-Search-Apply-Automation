"""Chaos, Network Failure, Crash-Recovery & Extreme Edge-Case Tests for Backend."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.collectors import jobspy_collector
from app.collectors.jobspy_collector import JobSpyCollector
from app.collectors.manager import CollectionProgress, CollectorManager, recover_stale_runs
from app.collectors.scheduler import CollectorScheduler
from app.config import Settings
from app.db.models import CollectorRun, Company, Job, utc_now
from app.pipeline.orchestrator import RawJobInput
from tests.conftest import DeterministicTestEmbedder


def _memory_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_network_failures_exhausted_retries_and_partial_batch_isolation(tmp_path: Path) -> None:
    """ConnectError, ReadTimeout, malformed JSON & exhausted 503 must isolate errors without dropping healthy companies."""
    with _memory_session() as session:
        c_timeout = Company(
            slug="timeout-co",
            display_name="Timeout Co",
            ats_type="greenhouse",
            ats_config_json={"board_token": "timeout"},
            is_watched=True,
        )
        c_connect = Company(
            slug="connect-err-co",
            display_name="ConnectErr Co",
            ats_type="lever",
            ats_config_json={"company_name": "connecterr"},
            is_watched=True,
        )
        c_bad_json = Company(
            slug="bad-json-co",
            display_name="BadJson Co",
            ats_type="ashby",
            ats_config_json={"company_name": "badjson"},
            is_watched=True,
        )
        c_persistent_502 = Company(
            slug="bad-gw-co",
            display_name="BadGateway Co",
            ats_type="smartrecruiters",
            ats_config_json={"company_id": "badgw"},
            is_watched=True,
        )
        c_healthy = Company(
            slug="healthy-co",
            display_name="Healthy Co",
            ats_type="greenhouse",
            ats_config_json={"board_token": "healthy"},
            is_watched=True,
        )
        session.add_all([c_timeout, c_connect, c_bad_json, c_persistent_502, c_healthy])
        session.commit()

        attempts = {"timeout": 0, "connect": 0, "502": 0}

        async def _fake_fetch(company: Company, client, known_external_ids=None, force_refresh_details=False):
            if company.slug == "timeout-co":
                attempts["timeout"] += 1
                raise httpx.ReadTimeout("Timed out reading from remote ATS")
            if company.slug == "connect-err-co":
                attempts["connect"] += 1
                raise httpx.ConnectError("DNS lookup failed")
            if company.slug == "bad-json-co":
                raise json.JSONDecodeError("Expecting value", "<html>oops</html>", 0)
            if company.slug == "bad-gw-co":
                attempts["502"] += 1
                req = httpx.Request("GET", "https://api.smartrecruiters.com/badgw")
                raise httpx.HTTPStatusError("502 Bad Gateway", request=req, response=httpx.Response(502, request=req))
            return [
                RawJobInput(
                    title="Backend Engineer",
                    company_name="Healthy Co",
                    description_raw="Build Python and FastAPI microservices in Bengaluru.",
                    location_raw="Bengaluru, India",
                    portal_name="greenhouse",
                    external_job_id="ok-1",
                    job_url="https://boards.greenhouse.io/healthy/jobs/1",
                )
            ]

        async def _fast_sleep(_sec: float) -> None:
            return None

        progress = CollectionProgress()
        manager = CollectorManager(settings=Settings(data_dir=tmp_path))

        async def _run():
            with patch.object(manager, "_fetch_company_raw", side_effect=_fake_fetch), patch(
                "app.collectors.manager.asyncio.sleep", side_effect=_fast_sleep
            ):
                return await manager.collect_all_watched(
                    session,
                    DeterministicTestEmbedder(),
                    force=True,
                    resume_window_minutes=0,
                    progress=progress,
                )

        results = asyncio.run(_run())
        assert len(results) == 5
        assert sum(1 for r in results if r.status == "error") == 4
        assert sum(1 for r in results if r.status == "ok") == 1
        # 1 initial try + 2 retries = 3 total attempts for transient network/5xx errors
        assert attempts["timeout"] == 3
        assert attempts["connect"] == 3
        assert attempts["502"] == 3
        # Healthy company still saved cleanly & progress cleanly finished
        assert session.exec(select(Job).where(Job.company_slug == "healthy-co")).first() is not None
        assert progress.running is False
        assert progress.phase == "idle"


def test_partial_job_ingest_crash_continues_remaining_jobs(tmp_path: Path) -> None:
    """If one RawJobInput raises during ingest_job, collect_company continues processing remaining jobs."""
    with _memory_session() as session:
        comp = Company(
            slug="partial-co",
            display_name="Partial Co",
            ats_type="greenhouse",
            ats_config_json={"board_token": "partial"},
            is_watched=True,
        )
        session.add(comp)
        session.commit()
        session.refresh(comp)

        req = httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/partial/jobs")
        mock_payload = {
            "jobs": [
                {
                    "id": 1,
                    "title": "Broken Role",
                    "location": {"name": "Bengaluru, India"},
                    "content": "Broken job triggers crash",
                    "absolute_url": "https://boards.greenhouse.io/partial/jobs/1",
                },
                {
                    "id": 2,
                    "title": "Healthy Backend Role",
                    "location": {"name": "Bengaluru, India"},
                    "content": "Python and FastAPI backend services.",
                    "absolute_url": "https://boards.greenhouse.io/partial/jobs/2",
                },
            ]
        }

        async def _fake_get(*_args, **_kwargs):
            return httpx.Response(status_code=200, json=mock_payload, request=req)

        client = httpx.AsyncClient()

        from app.pipeline.orchestrator import ingest_job as real_ingest

        def _flaky_ingest(session, raw, embedder, settings=None, semantic_threshold=None):
            if raw.external_job_id == "1":
                raise RuntimeError("Simulated DB serialization hiccup on job #1")
            return real_ingest(session, raw, embedder, settings=settings, semantic_threshold=semantic_threshold)

        async def _run():
            manager = CollectorManager(settings=Settings(data_dir=tmp_path))
            with patch.object(client, "get", side_effect=_fake_get), patch(
                "app.collectors.manager.ingest_job", side_effect=_flaky_ingest
            ):
                try:
                    return await manager.collect_company(session, DeterministicTestEmbedder(), comp, client=client)
                finally:
                    await client.aclose()

        res = asyncio.run(_run())
        assert res.status == "ok"
        assert res.fetched_count == 2
        assert res.new_count == 1
        assert len(list(session.exec(select(Job).where(Job.company_slug == "partial-co")).all())) == 1


def test_stale_run_recovery_and_scheduler_cancellation_and_lock_skip(tmp_path: Path) -> None:
    """Crash leaves multiple 'running' rows -> recover_stale_runs marks all 'interrupted'; scheduler stops cleanly."""
    with _memory_session() as session:
        session.add_all(
            [
                CollectorRun(source_name="ats_greenhouse", company_slug="a", status="running", started_at=utc_now() - timedelta(hours=2)),
                CollectorRun(source_name="jobspy", company_slug=None, status="running", started_at=utc_now() - timedelta(minutes=45)),
                CollectorRun(source_name="ats_lever", company_slug="b", status="ok", started_at=utc_now() - timedelta(hours=3)),
            ]
        )
        session.commit()

        recovered = recover_stale_runs(session)
        assert recovered == 2
        interrupted = list(session.exec(select(CollectorRun).where(CollectorRun.status == "interrupted")).all())
        assert len(interrupted) == 2
        assert all(r.finished_at is not None for r in interrupted)

    async def _run_scheduler_cancel():
        lock = asyncio.Lock()
        sched = CollectorScheduler(
            settings=Settings(data_dir=tmp_path),
            embedder=DeterministicTestEmbedder(),
            interval_hours=1,
            lock=lock,
        )
        # Hold lock -> scheduler tick should skip collection without deadlocking, then cancel cleanly
        await lock.acquire()
        with patch.object(sched.manager, "collect_all_watched") as mock_collect:
            sched.start()
            await asyncio.sleep(0.05)
            sched.stop()
            await asyncio.gather(sched._task, return_exceptions=True)  # type: ignore[arg-type]
            mock_collect.assert_not_called()
        lock.release()
        assert sched.is_running() is False

    asyncio.run(_run_scheduler_cancel())


def test_jobspy_unavailable_empty_and_partial_query_failure_resilience(tmp_path: Path) -> None:
    """Verify JobSpy handles missing dependency, empty/None DataFrames, and transient per-query exceptions."""
    with _memory_session() as session:
        c = JobSpyCollector(settings=Settings(data_dir=tmp_path, jobspy_min_delay_sec=0.0, jobspy_max_delay_sec=0.0))

        # 1. Dependency missing -> status="skipped"
        with patch.object(jobspy_collector, "JOBSPY_AVAILABLE", False):
            res_skip = asyncio.run(c.run(session, DeterministicTestEmbedder()))
        assert res_skip.status == "skipped"

        # 2. First query raises ConnectionError (not rate-limit), second returns empty DataFrame
        async def _no_sleep(_sec):
            return None

        call_i = {"n": 0}

        def _flaky_scrape(**_kwargs):
            call_i["n"] += 1
            if call_i["n"] == 1:
                raise ConnectionError("Temporary connection reset")
            return pd.DataFrame()

        with patch.object(jobspy_collector, "JOBSPY_AVAILABLE", True), patch.object(
            jobspy_collector, "scrape_jobs", side_effect=_flaky_scrape
        ), patch("app.collectors.jobspy_collector.asyncio.sleep", side_effect=_no_sleep):
            res_ok = asyncio.run(
                c.run(
                    session,
                    DeterministicTestEmbedder(),
                    search_terms=["Backend Engineer", "SDE 2"],
                    locations=["Bengaluru"],
                )
            )
        assert res_ok.status == "ok"
        assert call_i["n"] == 2
        assert res_ok.fetched_count == 0


def test_corrupted_truncated_pdf_upload_cleanup_and_bad_json_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Empty, non-PDF, truncated PDF, or malformed target_titles return 422 and leave 0 orphan PDFs."""
    resumes_dir = client.app.state.settings.resumes_dir

    # Empty file
    assert (
        client.post(
            "/api/v1/resumes",
            headers=auth_headers,
            data={"track_name": "Backend"},
            files={"file": ("empty.pdf", b"", "application/pdf")},
        ).status_code
        == 422
    )

    # Truncated / corrupt %PDF- payload -> must return 422 AND clean up disk file!
    assert (
        client.post(
            "/api/v1/resumes",
            headers=auth_headers,
            data={"track_name": "Backend"},
            files={"file": ("corrupt.pdf", b"%PDF-1.4\n%%truncated-garbage", "application/pdf")},
        ).status_code
        == 422
    )
    assert list(resumes_dir.glob("*.pdf")) == []

    # Invalid JSON in target_titles
    assert (
        client.post(
            "/api/v1/resumes",
            headers=auth_headers,
            data={"track_name": "Backend", "target_titles": "[broken json"},
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        ).status_code
        == 422
    )


def test_huge_jd_unicode_xss_malformed_fts_pagination_and_self_diff(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path
) -> None:
    """Stress-test 60KB JDs, Unicode/XSS content, broken FTS5 syntax, pagination bounds, diff edge cases & safety snapshot."""
    huge_text = ("<script>alert('xss')</script> Python FastAPI Kafka Bengaluru ₹35 LPA. " * 900)
    r_ing = client.post(
        "/api/v1/jobs/ingest",
        headers=auth_headers,
        json={
            "title": "Senior Backend Engineer 🚀",
            "company_name": "Razorpay भारत",
            "description_raw": huge_text,
            "location_raw": "बेंगलुरु / Bengaluru",
            "portal_name": "greenhouse",
            "job_url": "https://boards.greenhouse.io/razorpay/jobs/999001",
        },
    )
    assert r_ing.status_code == 201
    job_id = r_ing.json()[0]["job_id"]

    # Malformed FTS5 queries never 500
    for bad_fts in ['"UnclosedQuote Python', "AND OR (((", ")))", 'Python" OR ""']:
        r_fts = client.get(f"/api/v1/jobs?fts_query={bad_fts}", headers=auth_headers)
        assert r_fts.status_code == 200, f"FTS query crashed on: {bad_fts}"

    # Pagination past end + sorting modes
    for sort_mode in ("tier", "freshness", "semantic"):
        r_page = client.get(f"/api/v1/jobs?sort={sort_mode}&limit=1&offset=0", headers=auth_headers)
        assert r_page.status_code == 200
        assert len(r_page.json()["items"]) == 1

    r_past = client.get("/api/v1/jobs?offset=999", headers=auth_headers)
    assert r_past.status_code == 200
    assert r_past.json()["total"] == 1
    assert r_past.json()["items"] == []

    # Diff edge cases: self-diff = 100%, missing sibling = 404
    r_self_diff = client.get(f"/api/v1/jobs/{job_id}/diff/{job_id}", headers=auth_headers)
    assert r_self_diff.status_code == 200
    assert r_self_diff.json()["similarity_pct"] == 100.0
    assert r_self_diff.json()["added_lines"] == []
    assert r_self_diff.json()["removed_lines"] == []

    assert client.get(f"/api/v1/jobs/{job_id}/diff/999999", headers=auth_headers).status_code == 404
    assert client.get("/api/v1/jobs/999999", headers=auth_headers).status_code == 404

    # Backup export + restore creates safety snapshot in backups_dir
    zip_bytes = client.get("/api/v1/backup/export", headers=auth_headers).content
    r_rest = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("safety.zip", zip_bytes, "application/zip")},
    )
    assert r_rest.status_code == 200
    assert r_rest.json()["safety_snapshot_path"] is not None
    assert Path(r_rest.json()["safety_snapshot_path"]).exists()

