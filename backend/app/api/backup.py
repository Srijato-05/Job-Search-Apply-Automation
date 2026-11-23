"""1-Click ZIP Backup Export and Restore API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import Engine

from app.api.deps import get_engine, get_settings
from app.applications.backup import export_backup_zip, restore_backup_zip
from app.config import Settings
from app.db.models import utc_now
from app.schemas.applications import BackupRestoreResponse

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.get("/export")
def download_backup_zip(
    settings: Settings = Depends(get_settings),
) -> Response:
    """Bundle WAL-safe SQLite snapshot + all stored resume PDFs into a single ZIP download."""
    try:
        zip_bytes = export_backup_zip(
            db_path=settings.db_path,
            resumes_dir=settings.resumes_dir,
            backups_dir=settings.backups_dir,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    stamp = utc_now().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="jobautomation_backup_{stamp}.zip"'
        },
    )


@router.post("/restore", response_model=BackupRestoreResponse)
async def upload_and_restore_backup_zip(
    file: UploadFile = File(..., description="ZIP archive created by GET /api/v1/backup/export"),
    settings: Settings = Depends(get_settings),
    engine: Engine = Depends(get_engine),
) -> BackupRestoreResponse:
    """Validate uploaded ZIP archive and restore SQLite database + resume PDFs safely."""
    zip_bytes = await file.read()
    try:
        summary = restore_backup_zip(
            zip_bytes=zip_bytes,
            db_path=settings.db_path,
            resumes_dir=settings.resumes_dir,
            backups_dir=settings.backups_dir,
            engine=engine,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return BackupRestoreResponse(**summary)  # type: ignore[arg-type]

