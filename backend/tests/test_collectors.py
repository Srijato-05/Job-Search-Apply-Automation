"""Tests for Job Collectors, Watchlist, Circuit Breakers, ATS Connectors, and Pruner."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import numpy as np
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.collectors.ats_ashby import fetch_ashby_jobs
from app.collectors.ats_greenhouse import fetch_greenhouse_jobs
from app.collectors.ats_lever import fetch_lever_jobs
from app.collectors.ats_smartrecruiters import fetch_smartrecruiters_jobs
from app.collectors.ats_workday import fetch_workday_jobs
from app.collectors.base import BaseCollector
from app.collectors.location_filter import is_india_location
from app.collectors.manager import CollectorManager, seed_watchlist
from app.collectors.pruner import prune_closed_ats_jobs
from app.config import Settings
from app.db.models import CollectorRun, Company, FactVault, Job, JobSource, Resume, utc_now
from app.resumes.embedder import EmbedderProtocol


class MockEmbedder(EmbedderProtocol):
    """Zero-network deterministic embedder for unit tests."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        results = []
        for text in texts:
            val = float(len(text) % 50) / 100.0
            vec = np.full(self.dim, val, dtype=np.float32)
            results.append(vec)
        return np.vstack(results)


@pytest.fixture
def test_db_session() -> Session:
    """Isolated in-memory SQLite session with schema initialized."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Prepopulate default Fact Vault
        vault = FactVault(
            id=1,
            full_name="Arjun Sharma",
            email="arjun@example.com",
            current_city="Bengaluru",
            preferred_cities_json=["Bengaluru", "Hyderabad", "Pune"],
            work_modes_json=["in_office", "hybrid", "remote"],
            total_exp_years=4.5,
            relevant_exp_years=4.5,
            notice_period_days=30,
            expected_ctc_lpa=32.0,
            skill_years_json={"python": 4.5, "fastapi": 3.0, "sql": 4.0},
        )
        session.add(vault)

        # Prepopulate sample resume
        resume = Resume(
            id=1,
            track_name="Backend Core",
            pdf_filename="arjun_backend.pdf",
            pdf_path="dummy.pdf",
            pdf_sha256="dummy_sha",
            target_titles_json=["Backend Engineer", "Software Engineer"],
            search_locations_json=["Bengaluru, India"],
            track_skills_json=["Python", "FastAPI", "PostgreSQL", "Kafka"],
            raw_text="Experienced Backend Engineer building Python services.",
            is_active=True,
        )
        session.add(resume)
        session.commit()
        yield session


# ==========================================
# 1. Location Filtering Tests
# ==========================================
def test_location_filtering_accuracy():
    """Verify Indian location classifier and foreign exclusion."""
    assert is_india_location("Bengaluru, Karnataka, India")[0] is True
    assert is_india_location("Bengaluru, Karnataka, India")[1] == "Bengaluru"

    assert is_india_location("Cyber City, Gurugram")[0] is True
    assert is_india_location("Cyber City, Gurugram")[1] == "Gurugram"

    assert is_india_location("Hinjewadi, Pune, India")[0] is True
    assert is_india_location("Hinjewadi, Pune, India")[1] == "Pune"

    assert is_india_location("Remote (India)")[0] is True

    # Foreign exclusion
    assert is_india_location("San Francisco, CA, USA")[0] is False
    assert is_india_location("London, United Kingdom")[0] is False
    assert is_india_location("Berlin, Germany")[0] is False
    assert is_india_location("Toronto, Canada")[0] is False
    assert is_india_location("")[0] is False


# ==========================================
# 2. Watchlist Seeding & CRUD Tests
# ==========================================
def test_watchlist_seeding_and_crud(test_db_session: Session):
    """Verify seed_watchlist loads 60+ tech companies and handles updates."""
    seeded, updated, total = seed_watchlist(test_db_session)
    assert total >= 60
    assert seeded >= 60

    # Verify key companies are present
    rzp = test_db_session.exec(select(Company).where(Company.slug == "razorpay")).first()
    assert rzp is not None
    assert rzp.ats_type == "greenhouse"
    assert rzp.ats_config_json.get("board_token") == "razorpay"

    atlassian = test_db_session.exec(select(Company).where(Company.slug == "atlassian")).first()
    assert atlassian is not None
    assert atlassian.ats_type == "lever"

    walmart = test_db_session.exec(select(Company).where(Company.slug == "walmart-global-tech")).first()
    assert walmart is not None
    assert walmart.ats_type == "workday"

    # Re-seeding should update without duplicate insertion
    seeded2, updated2, total2 = seed_watchlist(test_db_session)
    assert seeded2 == 0
    assert total2 == total


# ==========================================
# 3. Direct ATS Connector Mocked Tests
# ==========================================
def test_greenhouse_connector_mock():
    """Mock Greenhouse API response and assert India extraction."""
    async def _run():
        mock_response_data = {
            "jobs": [
                {
                    "id": 101,
                    "title": "Backend Engineer - Payments",
                    "location": {"name": "Bengaluru, India"},
                    "content": "<p>Build high scale payment APIs using Python and Kafka.</p>",
                    "absolute_url": "https://boards.greenhouse.io/test/jobs/101",
                    "updated_at": "2026-11-20T10:00:00Z",
                },
                {
                    "id": 102,
                    "title": "Product Designer",
                    "location": {"name": "San Francisco, USA"},
                    "content": "<p>Figma expert in SF.</p>",
                    "absolute_url": "https://boards.greenhouse.io/test/jobs/102",
                    "updated_at": "2026-11-20T10:00:00Z",
                },
            ]
        }

        mock_resp = httpx.Response(
            status_code=200,
            json=mock_response_data,
            request=httpx.Request("GET", "https://boards-api.greenhouse.io"),
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        jobs = await fetch_greenhouse_jobs(client, "test_token", "Test Corp", filter_india_only=True)
        assert len(jobs) == 1
        assert jobs[0].external_job_id == "101"
        assert jobs[0].title == "Backend Engineer - Payments"
        assert "Bengaluru" in jobs[0].location_raw
        assert jobs[0].portal_name == "greenhouse"

    asyncio.run(_run())


def test_lever_connector_mock():
    """Mock Lever API response and assert India extraction."""
    async def _run():
        mock_postings = [
            {
                "id": "lev-901",
                "text": "Senior Platform Engineer",
                "createdAt": 1700000000,
                "hostedUrl": "https://jobs.lever.co/test/lev-901",
                "applyUrl": "https://jobs.lever.co/test/lev-901/apply",
                "categories": {
                    "location": "Bengaluru, Karnataka",
                    "team": "Infrastructure",
                    "commitment": "Full Time",
                },
                "descriptionPlain": "Kubernetes and Go microservices.",
                "additionalPlain": "Requirements: 4+ years experience.",
            },
            {
                "id": "lev-902",
                "text": "Account Executive",
                "createdAt": 1700000000,
                "hostedUrl": "https://jobs.lever.co/test/lev-902",
                "categories": {"location": "London, UK"},
                "descriptionPlain": "Sales lead in London.",
            },
        ]

        mock_resp = httpx.Response(
            status_code=200,
            json=mock_postings,
            request=httpx.Request("GET", "https://api.lever.co"),
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        jobs = await fetch_lever_jobs(client, "test_comp", "Lever Corp", filter_india_only=True)
        assert len(jobs) == 1
        assert jobs[0].external_job_id == "lev-901"
        assert jobs[0].title == "Senior Platform Engineer"
        assert "Kubernetes" in jobs[0].description_raw
        assert jobs[0].portal_name == "lever"

    asyncio.run(_run())


def test_ashby_connector_mock():
    """Mock Ashby API response."""
    async def _run():
        mock_data = {
            "jobs": [
                {
                    "id": "ash-55",
                    "title": "Full Stack Engineer",
                    "locationName": "Hyderabad, Telangana, India",
                    "jobUrl": "https://jobs.ashbyhq.com/test/ash-55",
                    "descriptionHtml": "<p>React and Node stack.</p>",
                    "publishedAt": "2026-11-20T08:00:00Z",
                }
            ]
        }

        mock_resp = httpx.Response(
            status_code=200,
            json=mock_data,
            request=httpx.Request("GET", "https://api.ashbyhq.com"),
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        jobs = await fetch_ashby_jobs(client, "ashby_corp", "Ashby Corp", filter_india_only=True)
        assert len(jobs) == 1
        assert jobs[0].external_job_id == "ash-55"
        assert "Hyderabad" in jobs[0].location_raw

    asyncio.run(_run())


def test_smartrecruiters_connector_mock():
    """Mock SmartRecruiters API response."""
    async def _run():
        mock_content = {
            "content": [
                {
                    "id": "sr-11",
                    "name": "Software Engineer II",
                    "location": {"city": "Pune", "region": "Maharashtra", "country": "in"},
                    "refNumber": "REF1234K",
                    "releasedDate": "2026-11-20T00:00:00Z",
                }
            ]
        }

        mock_resp = httpx.Response(
            status_code=200,
            json=mock_content,
            request=httpx.Request("GET", "https://api.smartrecruiters.com"),
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        jobs = await fetch_smartrecruiters_jobs(
            client, "sr_corp", "SR Corp", filter_india_only=True, fetch_details=False
        )
        assert len(jobs) == 1
        assert jobs[0].external_job_id == "sr-11"
        assert "Pune" in jobs[0].location_raw
        assert jobs[0].portal_metadata.get("ref_number") == "REF1234K"

    asyncio.run(_run())


def test_workday_cxs_limit_and_pagination():
    """Verify Workday CXS connector enforces limit <= 20 and pagination loop stop."""
    async def _run():
        payloads_received: list[dict[str, Any]] = []

        async def mock_post(url, json=None, headers=None, timeout=None):
            payloads_received.append(json or {})
            offset = json.get("offset", 0) if json else 0

            # Simulate 2 pages of results, total 30
            if offset == 0:
                postings = [
                    {
                        "title": f"Workday SDE {i}",
                        "externalPath": f"/job/Bengaluru-India/Workday-SDE_JR{1000 + i}",
                        "locationsText": "Bengaluru, Karnataka, India",
                        "bulletFields": [f"JR{1000 + i}"],
                    }
                    for i in range(20)
                ]
                return httpx.Response(
                    status_code=200,
                    json={"total": 30, "jobPostings": postings},
                    request=httpx.Request("POST", url),
                )
            else:
                postings = [
                    {
                        "title": f"Workday SDE {i}",
                        "externalPath": f"/job/Bengaluru-India/Workday-SDE_JR{1000 + i}",
                        "locationsText": "Bengaluru, Karnataka, India",
                        "bulletFields": [f"JR{1000 + i}"],
                    }
                    for i in range(20, 30)
                ]
                return httpx.Response(
                    status_code=200,
                    json={"total": 30, "jobPostings": postings},
                    request=httpx.Request("POST", url),
                )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = mock_post
        client.get.return_value = httpx.Response(
            status_code=200,
            json={"jobPostingInfo": {"jobDescription": "Workday job details"}},
            request=httpx.Request("GET", "https://workday.com/job"),
        )

        jobs = await fetch_workday_jobs(
            client=client,
            tenant="walmart",
            site="WalmartExternal",
            company_name="Walmart",
            filter_india_only=True,
        )

        # Asserts
        assert len(payloads_received) == 2
        for p in payloads_received:
            # Crucial Workday limit <= 20 assertion
            assert p.get("limit") <= 20

        assert len(jobs) == 30
        assert jobs[0].external_job_id.startswith("JR100")

    asyncio.run(_run())


# ==========================================
# 4. Circuit Breaker Tests
# ==========================================
def test_circuit_breaker_tripping_on_429(test_db_session: Session):
    """Assert HTTP 429 triggers cooldown and skips immediate re-run."""
    async def _run():
        settings = Settings(circuit_breaker_cooldown_hours=8)
        manager = CollectorManager(settings=settings)

        # Create dummy company
        comp = Company(
            slug="rate-limited-co",
            display_name="Rate Limited Co",
            ats_type="greenhouse",
            ats_config_json={"board_token": "limited"},
            is_watched=True,
        )
        test_db_session.add(comp)
        test_db_session.commit()
        test_db_session.refresh(comp)

        # Mock client that raises 429
        client = AsyncMock(spec=httpx.AsyncClient)
        req = httpx.Request("GET", "https://boards-api.greenhouse.io")
        resp_429 = httpx.Response(status_code=429, request=req)
        client.get.return_value = resp_429

        embedder = MockEmbedder()
        res = await manager.collect_company(
            session=test_db_session,
            embedder=embedder,
            company=comp,
            client=client,
            force=False,
        )

        assert res.status == "cooldown"
        assert "429" in (res.error_message or "")

        # Check database telemetry
        run = test_db_session.exec(
            select(CollectorRun).where(CollectorRun.company_slug == comp.slug)
        ).first()
        assert run is not None
        assert run.status == "cooldown"
        assert run.cooldown_until is not None
        assert run.cooldown_until > utc_now()

        # Second run without force must be skipped immediately
        res_second = await manager.collect_company(
            session=test_db_session,
            embedder=embedder,
            company=comp,
            client=client,
            force=False,
        )
        assert res_second.status == "cooldown"
        assert "in circuit-breaker cooldown" in (res_second.error_message or "")

    asyncio.run(_run())


# ==========================================
# 5. Closed-Job Pruner Tests
# ==========================================
def test_closed_job_pruner_mechanism(test_db_session: Session):
    """Verify vanished jobs are marked closed."""
    # Insert 2 active jobs for 'razorpay'
    job1 = Job(
        title="Backend SDE 1",
        company_name="Razorpay",
        company_slug="razorpay",
        status="active",
        req_id="RZP101",
    )
    job2 = Job(
        title="Frontend SDE 2",
        company_name="Razorpay",
        company_slug="razorpay",
        status="active",
        req_id="RZP102",
    )
    test_db_session.add(job1)
    test_db_session.add(job2)
    test_db_session.commit()
    test_db_session.refresh(job1)
    test_db_session.refresh(job2)

    src1 = JobSource(job_id=job1.id, portal_name="greenhouse", external_job_id="101", job_url="https://rzp.com/101")
    src2 = JobSource(job_id=job2.id, portal_name="greenhouse", external_job_id="102", job_url="https://rzp.com/102")
    test_db_session.add(src1)
    test_db_session.add(src2)
    test_db_session.commit()

    # Pruner called with only job 1 active
    closed = prune_closed_ats_jobs(
        session=test_db_session,
        company_slug="razorpay",
        active_external_ids={"101", "RZP101"},
        active_urls={"https://rzp.com/101"},
    )

    assert closed == 1
    test_db_session.refresh(job1)
    test_db_session.refresh(job2)

    assert job1.status == "active"
    assert job2.status == "closed"


# ==========================================
# 6. End-to-End Manager & Health Overview
# ==========================================
def test_manager_end_to_end_and_health(test_db_session: Session):
    """Test full collection through pipeline and health summary generation."""
    async def _run():
        settings = Settings()
        manager = CollectorManager(settings=settings)
        embedder = MockEmbedder()

        comp = Company(
            slug="cred-test",
            display_name="CRED",
            ats_type="greenhouse",
            ats_config_json={"board_token": "cred"},
            is_watched=True,
        )
        test_db_session.add(comp)
        test_db_session.commit()
        test_db_session.refresh(comp)

        # Mock Greenhouse returning 1 valid India job
        mock_data = {
            "jobs": [
                {
                    "id": 8801,
                    "title": "Backend Engineer",
                    "location": {"name": "Bengaluru, India"},
                    "content": "<p>Looking for Python backend developer with FastAPI, SQL and Kafka.</p>",
                    "absolute_url": "https://boards.greenhouse.io/cred/jobs/8801",
                }
            ]
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = httpx.Response(
            status_code=200,
            json=mock_data,
            request=httpx.Request("GET", "https://boards-api.greenhouse.io"),
        )

        res = await manager.collect_company(test_db_session, embedder, comp, client=client)
        assert res.status == "ok"
        assert res.fetched_count == 1
        assert res.new_count == 1

        # Check job saved in database
        saved_job = test_db_session.exec(
            select(Job).where(Job.company_slug == "cred-test")
        ).first()
        assert saved_job is not None
        assert saved_job.status == "active"
        assert "Bengaluru" in saved_job.normalized_city

        # Check health overview
        health = manager.get_health_overview(test_db_session)
        assert health.total_sources >= 1
        assert health.healthy_sources >= 1

    asyncio.run(_run())
