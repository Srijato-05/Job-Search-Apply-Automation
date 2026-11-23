"""WAL-safe ZIP Backup Export and validated Restore for SQLite + Resume PDFs."""

from __future__ import annotations

import io
import json
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile

from sqlalchemy import Engine

from app.db.database import create_sqlite_snapshot, init_db
from app.db.models import utc_now

_SQLITE_MAGIC = b"SQLite format 3\x00"


def export_backup_zip(db_path: Path, resumes_dir: Path, backups_dir: Path) -> bytes:
    """Create a WAL-consistent ZIP archive containing jobs.db, resumes/*.pdf, and manifest.json."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    resumes_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = create_sqlite_snapshot(db_path, backups_dir, keep_last=5)
    if snapshot_path is None or not snapshot_path.exists():
        raise FileNotFoundError(f"Database file not found at {db_path}")

    pdf_files = sorted(resumes_dir.glob("*.pdf"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(snapshot_path, arcname="jobs.db")
        for pdf in pdf_files:
            zf.write(pdf, arcname=f"resumes/{pdf.name}")
        manifest = {
            "version": "0.1.0",
            "exported_at": utc_now().isoformat(),
            "resumes_count": len(pdf_files),
            "resume_filenames": [p.name for p in pdf_files],
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buf.getvalue()


def _is_safe_zip_member(name: str) -> bool:
    """Block Zip Slip path traversal and absolute paths."""
    if not name or name.startswith("/") or name.startswith("\\"):
        return False
    if ":" in name:
        return False
    parts = PurePosixPath(name.replace("\\", "/")).parts
    return ".." not in parts


def restore_backup_zip(
    zip_bytes: bytes,
    db_path: Path,
    resumes_dir: Path,
    backups_dir: Path,
    engine: Engine,
) -> dict[str, object]:
    """Validate and restore a ZIP backup with pre-restore safety snapshot and engine disposal."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive.") from exc

    with zf:
        names = zf.namelist()
        for name in names:
            if not _is_safe_zip_member(name):
                raise ValueError(f"Unsafe archive entry path blocked: '{name}'")

        if "jobs.db" not in names:
            raise ValueError("Backup archive is missing required 'jobs.db' entry.")

        db_bytes = zf.read("jobs.db")
        if len(db_bytes) < len(_SQLITE_MAGIC) or not db_bytes.startswith(_SQLITE_MAGIC):
            raise ValueError("Archive 'jobs.db' is not a valid SQLite database.")

        # Validate SQLite integrity on a temp file before replacing live DB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(db_bytes)

        try:
            check_conn = sqlite3.connect(str(tmp_path))
            try:
                res = check_conn.execute("PRAGMA quick_check;").fetchone()
                if not res or res[0] != "ok":
                    raise ValueError(f"SQLite integrity check failed: {res}")
            finally:
                check_conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

        # Create automatic pre-restore safety snapshot of current DB
        safety_path = create_sqlite_snapshot(db_path, backups_dir, keep_last=5)

        # Dispose SQLAlchemy pool so Windows releases file locks on jobs.db / -wal / -shm
        engine.dispose()

        db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            sidecar.unlink(missing_ok=True)

        db_path.write_bytes(db_bytes)

        # Restore PDFs under resumes/
        resumes_dir.mkdir(parents=True, exist_ok=True)
        restored_pdfs = 0
        for name in names:
            normalized = name.replace("\\", "/")
            if normalized.startswith("resumes/") and not normalized.endswith("/"):
                filename = PurePosixPath(normalized).name
                if filename.lower().endswith(".pdf"):
                    (resumes_dir / filename).write_bytes(zf.read(name))
                    restored_pdfs += 1

    # Re-verify schema / FTS5 / composite indexes on restored DB
    init_db(engine)

    return {
        "status": "restored",
        "restored_db_bytes": len(db_bytes),
        "restored_resumes_count": restored_pdfs,
        "safety_snapshot_path": str(safety_path) if safety_path else None,
        "message": f"Restored database ({len(db_bytes)} bytes) and {restored_pdfs} resume PDF(s).",
    }

