"""SQLite WAL engine setup, FTS5 triggers, and full-text search helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event, text
from sqlmodel import Session, SQLModel, create_engine

# Ensure every SQLModel table is registered before create_all.
from app.db import models as _models  # noqa: F401

_FTS5_SCHEMA_STATEMENTS = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
        title,
        company_name,
        role_subtag,
        boilerplate_stripped_text,
        normalized_city,
        content='jobs',
        content_rowid='id'
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS jobs_fts_ai AFTER INSERT ON jobs BEGIN
        INSERT INTO jobs_fts(
            rowid, title, company_name, role_subtag, boilerplate_stripped_text, normalized_city
        )
        VALUES (
            new.id, new.title, new.company_name, new.role_subtag,
            new.boilerplate_stripped_text, new.normalized_city
        );
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS jobs_fts_ad AFTER DELETE ON jobs BEGIN
        INSERT INTO jobs_fts(
            jobs_fts, rowid, title, company_name, role_subtag,
            boilerplate_stripped_text, normalized_city
        )
        VALUES (
            'delete', old.id, old.title, old.company_name, old.role_subtag,
            old.boilerplate_stripped_text, old.normalized_city
        );
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS jobs_fts_au AFTER UPDATE ON jobs BEGIN
        INSERT INTO jobs_fts(
            jobs_fts, rowid, title, company_name, role_subtag,
            boilerplate_stripped_text, normalized_city
        )
        VALUES (
            'delete', old.id, old.title, old.company_name, old.role_subtag,
            old.boilerplate_stripped_text, old.normalized_city
        );
        INSERT INTO jobs_fts(
            rowid, title, company_name, role_subtag, boilerplate_stripped_text, normalized_city
        )
        VALUES (
            new.id, new.title, new.company_name, new.role_subtag,
            new.boilerplate_stripped_text, new.normalized_city
        );
    END;
    """,
)


def create_db_engine(db_path: Path) -> Engine:
    """Create a SQLite engine configured with WAL mode and foreign keys."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()

    return engine


_COMPOSITE_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_jobs_company_status ON jobs (company_slug, status);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_identity_lookup ON jobs (company_slug, normalized_title, normalized_city);",
    "CREATE INDEX IF NOT EXISTS idx_collector_runs_lookup ON collector_runs (source_name, company_slug, id DESC);",
    "CREATE INDEX IF NOT EXISTS idx_job_sources_job_portal ON job_sources (job_id, portal_name);",
)


def init_db(engine: Engine) -> None:
    """Create all ORM tables, composite indexes, and FTS5 virtual table triggers."""
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        for stmt in _FTS5_SCHEMA_STATEMENTS:
            conn.execute(text(stmt))
        for idx_stmt in _COMPOSITE_INDEX_STATEMENTS:
            conn.execute(text(idx_stmt))


def create_sqlite_snapshot(db_path: Path, backups_dir: Path, keep_last: int = 5) -> Optional[Path]:
    """Create a WAL-safe online SQLite snapshot using sqlite3.Connection.backup()."""
    import sqlite3
    from datetime import datetime, timezone

    if not db_path.exists():
        return None
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backups_dir / f"jobs_snapshot_{stamp}.db"

    src_conn = sqlite3.connect(str(db_path))
    dst_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    # Rotate old snapshots, keeping only the newest `keep_last`
    snapshots = sorted(backups_dir.glob("jobs_snapshot_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[keep_last:]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def search_jobs_fts(session: Session, query: str, limit: int = 50) -> list[int]:
    """Run an offline SQLite FTS5 boolean query and return matching job IDs by BM25."""
    cleaned = query.strip()
    if not cleaned:
        return []
    rows = session.exec(
        text(
            "SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :query "
            "ORDER BY bm25(jobs_fts) LIMIT :limit"
        ),
        params={"query": cleaned, "limit": limit},
    ).all()
    return [int(row[0]) for row in rows]

