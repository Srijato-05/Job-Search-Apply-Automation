"""Tests for SQLite WAL, 10-table schema, FTS5 boolean search, token auth, and CORS."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlmodel import Session

from app.db.database import search_jobs_fts
from app.db.models import Job


def test_sqlite_wal_foreign_keys_and_all_10_tables(app_with_mock_embedder) -> None:
    engine = app_with_mock_embedder.state.engine
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
        fk_enabled = conn.execute(text("PRAGMA foreign_keys;")).scalar()

    assert str(journal_mode).lower() == "wal"
    assert fk_enabled == 1

    table_names = set(inspect(engine).get_table_names())
    expected_tables = {
        "fact_vault",
        "learned_qa_rules",
        "resumes",
        "resume_bullets",
        "companies",
        "jobs",
        "job_sources",
        "job_resume_scores",
        "applications",
        "collector_runs",
        "jobs_fts",
    }
    assert expected_tables.issubset(table_names)


def test_fts5_triggers_insert_update_delete_and_boolean_query(app_with_mock_embedder) -> None:
    engine = app_with_mock_embedder.state.engine
    with Session(engine) as session:
        job_match = Job(
            title="Senior Backend Engineer",
            company_name="Razorpay",
            company_slug="razorpay",
            normalized_title="senior backend engineer",
            role_subtag="Payments • FastAPI / Kafka",
            normalized_city="Bengaluru",
            boilerplate_stripped_text="Build high throughput FastAPI microservices and Kafka pipelines.",
        )
        job_night_shift = Job(
            title="Backend Support Engineer",
            company_name="SupportCorp",
            company_slug="supportcorp",
            normalized_title="backend support engineer",
            role_subtag="Ops • FastAPI / Redis",
            normalized_city="Bengaluru",
            boilerplate_stripped_text="FastAPI and Redis support role requiring night shift coverage.",
        )
        session.add(job_match)
        session.add(job_night_shift)
        session.commit()
        session.refresh(job_match)
        session.refresh(job_night_shift)

        # Boolean query matching FastAPI AND (Kafka OR Redis) NOT "night shift"
        ids = search_jobs_fts(session, 'FastAPI AND (Kafka OR Redis) NOT "night shift"')
        assert ids == [job_match.id]

        # Update trigger check
        job_match.role_subtag = "Storage • Rust / gRPC"
        job_match.boilerplate_stripped_text = "Build Rust and gRPC distributed storage engines."
        session.add(job_match)
        session.commit()
        assert search_jobs_fts(session, "Kafka") == []
        assert search_jobs_fts(session, "gRPC") == [job_match.id]

        # Delete trigger check
        session.delete(job_match)
        session.commit()
        assert search_jobs_fts(session, "gRPC") == []


def test_local_token_auth_and_cors_enforcement(client: TestClient, auth_headers: dict[str, str]) -> None:
    # Health endpoint is accessible without token
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # Missing or invalid token rejected on /api/v1/*
    assert client.get("/api/v1/vault").status_code == 401
    assert client.get("/api/v1/vault", headers={"X-Local-Token": "wrong-token"}).status_code == 401

    # Valid token succeeds
    ok_resp = client.get("/api/v1/vault", headers=auth_headers)
    assert ok_resp.status_code == 200

    # Allowed local UI and chrome-extension origins receive CORS header
    allowed_ui = client.options(
        "/api/v1/vault",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Local-Token",
        },
    )
    assert allowed_ui.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"

    ext_origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    allowed_ext = client.options(
        "/api/v1/vault",
        headers={
            "Origin": ext_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed_ext.headers.get("access-control-allow-origin") == ext_origin

    # Arbitrary untrusted internet origin does NOT get CORS allow header
    untrusted = client.options(
        "/api/v1/vault",
        headers={
            "Origin": "https://evil-site.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert untrusted.headers.get("access-control-allow-origin") is None

