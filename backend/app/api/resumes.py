"""API routes for Multi-Resume PDF Registry, bullet extraction, and vectorization."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_embedder, get_session, get_settings
from app.config import Settings
from app.db.models import Resume, ResumeBullet, utc_now
from app.resumes.embedder import EmbedderProtocol, vector_to_blob
from app.resumes.parser import parse_resume_pdf
from app.schemas.resumes import (
    ResumeBulletResponse,
    ResumeDetailResponse,
    ResumeSummaryResponse,
    ResumeUpdatePayload,
)
from app.vault.taxonomy import normalize_city, normalize_skill_list

router = APIRouter(prefix="/resumes", tags=["resumes"])

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _parse_str_list(raw: str) -> list[str]:
    """Parse either a JSON string array or a comma-separated list."""
    cleaned = raw.strip()
    if not cleaned:
        return []
    if cleaned.startswith("["):
        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON list")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in cleaned.split(",") if part.strip()]


def _safe_filename(original_name: str) -> str:
    base = Path(original_name or "resume.pdf").name
    sanitized = _SAFE_NAME_RE.sub("_", base).strip("._")
    if not sanitized.lower().endswith(".pdf"):
        sanitized = f"{sanitized or 'resume'}.pdf"
    return sanitized


def _build_summary(resume: Resume, bullet_count: int) -> ResumeSummaryResponse:
    return ResumeSummaryResponse(
        id=int(resume.id),
        track_name=resume.track_name,
        pdf_filename=resume.pdf_filename,
        pdf_sha256=resume.pdf_sha256,
        target_titles_json=resume.target_titles_json,
        search_locations_json=resume.search_locations_json,
        track_skills_json=resume.track_skills_json,
        cover_template=resume.cover_template,
        is_active=resume.is_active,
        bullet_count=bullet_count,
        created_at=resume.created_at,
        updated_at=resume.updated_at,
    )


def _build_detail(resume: Resume, bullets: list[ResumeBullet]) -> ResumeDetailResponse:
    bullet_dtos = [
        ResumeBulletResponse(
            id=int(b.id),
            section_name=b.section_name,
            bullet_order=b.bullet_order,
            bullet_text=b.bullet_text,
            extracted_skills_json=b.extracted_skills_json,
            has_embedding=bool(b.embedding_blob),
        )
        for b in bullets
    ]
    return ResumeDetailResponse(
        id=int(resume.id),
        track_name=resume.track_name,
        pdf_filename=resume.pdf_filename,
        pdf_sha256=resume.pdf_sha256,
        target_titles_json=resume.target_titles_json,
        search_locations_json=resume.search_locations_json,
        track_skills_json=resume.track_skills_json,
        cover_template=resume.cover_template,
        is_active=resume.is_active,
        bullet_count=len(bullet_dtos),
        created_at=resume.created_at,
        updated_at=resume.updated_at,
        raw_text=resume.raw_text,
        bullets=bullet_dtos,
    )


def _store_parsed_bullets(
    session: Session,
    resume_id: int,
    pdf_path: Path,
    embedder: EmbedderProtocol,
) -> tuple[str, list[str], list[ResumeBullet]]:
    parsed = parse_resume_pdf(pdf_path)
    bullet_texts = [b.bullet_text for b in parsed.bullets]
    vectors = embedder.embed_texts(bullet_texts)

    created_bullets: list[ResumeBullet] = []
    for idx, bullet in enumerate(parsed.bullets):
        emb_blob = vector_to_blob(vectors[idx]) if len(vectors) > idx else None
        row = ResumeBullet(
            resume_id=resume_id,
            section_name=bullet.section_name,
            bullet_order=bullet.bullet_order,
            bullet_text=bullet.bullet_text,
            extracted_skills_json=bullet.extracted_skills,
            embedding_blob=emb_blob,
        )
        session.add(row)
        created_bullets.append(row)

    return parsed.raw_text, parsed.skills, created_bullets


@router.get("", response_model=list[ResumeSummaryResponse])
def list_resumes(session: Session = Depends(get_session)) -> list[ResumeSummaryResponse]:
    """List all registered resume tracks with bullet counts."""
    resumes = list(session.exec(select(Resume).order_by(Resume.id.asc())).all())
    counts_rows = session.exec(
        select(ResumeBullet.resume_id, func.count(ResumeBullet.id)).group_by(ResumeBullet.resume_id)
    ).all()
    counts = {int(rid): int(cnt) for rid, cnt in counts_rows}
    return [_build_summary(r, counts.get(int(r.id), 0)) for r in resumes]


@router.post("", response_model=ResumeDetailResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    track_name: str = Form(...),
    target_titles: str = Form("[]"),
    search_locations: str = Form("[]"),
    cover_template: str = Form(""),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    embedder: EmbedderProtocol = Depends(get_embedder),
) -> ResumeDetailResponse:
    """Upload a Resume PDF, extract verbatim bullets, normalize skills, and embed vectors."""
    if not track_name.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="track_name is required")

    try:
        parsed_titles = _parse_str_list(target_titles)
        parsed_locations = [normalize_city(loc) for loc in _parse_str_list(search_locations) if loc.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    pdf_bytes = await file.read()
    if not pdf_bytes or not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded file must be a valid non-empty PDF.",
        )

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    safe_name = _safe_filename(file.filename or "resume.pdf")
    settings.resumes_dir.mkdir(parents=True, exist_ok=True)
    disk_path = settings.resumes_dir / f"{sha256[:12]}_{safe_name}"
    wrote_new_file = not disk_path.exists()
    if wrote_new_file:
        disk_path.write_bytes(pdf_bytes)

    try:
        resume = Resume(
            track_name=track_name.strip(),
            pdf_filename=safe_name,
            pdf_path=str(disk_path),
            pdf_sha256=sha256,
            target_titles_json=parsed_titles,
            search_locations_json=parsed_locations,
            cover_template=cover_template,
        )
        session.add(resume)
        session.flush()

        raw_text, skills, bullets = _store_parsed_bullets(
            session=session,
            resume_id=int(resume.id),
            pdf_path=disk_path,
            embedder=embedder,
        )
        resume.raw_text = raw_text
        resume.track_skills_json = skills
        resume.updated_at = utc_now()
        session.add(resume)
        session.commit()
    except Exception as exc:
        session.rollback()
        if wrote_new_file and disk_path.exists():
            disk_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Failed to parse uploaded PDF: {exc}",
        ) from exc

    session.refresh(resume)
    for b in bullets:
        session.refresh(b)
    return _build_detail(resume, bullets)


@router.get("/{resume_id}", response_model=ResumeDetailResponse)
def get_resume_detail(
    resume_id: int,
    session: Session = Depends(get_session),
) -> ResumeDetailResponse:
    """Return full metadata, extracted raw text, and embedded bullets for a resume."""
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    bullets = list(
        session.exec(
            select(ResumeBullet)
            .where(ResumeBullet.resume_id == resume_id)
            .order_by(ResumeBullet.bullet_order.asc())
        ).all()
    )
    return _build_detail(resume, bullets)


@router.patch("/{resume_id}", response_model=ResumeSummaryResponse)
def update_resume(
    resume_id: int,
    payload: ResumeUpdatePayload,
    session: Session = Depends(get_session),
) -> ResumeSummaryResponse:
    """Update track metadata, target titles, locations, skills, or cover template."""
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    if payload.track_name is not None:
        resume.track_name = payload.track_name.strip()
    if payload.target_titles_json is not None:
        resume.target_titles_json = [t.strip() for t in payload.target_titles_json if t.strip()]
    if payload.search_locations_json is not None:
        resume.search_locations_json = [
            normalize_city(c) for c in payload.search_locations_json if c.strip()
        ]
    if payload.track_skills_json is not None:
        resume.track_skills_json = normalize_skill_list(payload.track_skills_json)
    if payload.cover_template is not None:
        resume.cover_template = payload.cover_template
    if payload.is_active is not None:
        resume.is_active = payload.is_active

    resume.updated_at = utc_now()
    session.add(resume)
    session.commit()
    session.refresh(resume)

    bullet_count = session.exec(
        select(func.count(ResumeBullet.id)).where(ResumeBullet.resume_id == resume_id)
    ).one()
    return _build_summary(resume, int(bullet_count))


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a resume track, cascade-delete bullets, and unlink unreferenced PDF files."""
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    pdf_path = Path(resume.pdf_path)
    other_refs = session.exec(
        select(func.count(Resume.id)).where(
            Resume.pdf_path == resume.pdf_path,
            Resume.id != resume_id,
        )
    ).one()

    session.delete(resume)
    session.commit()

    if int(other_refs) == 0 and pdf_path.exists():
        pdf_path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{resume_id}/file")
def download_resume_file(
    resume_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Stream the raw PDF binary for extension DataTransfer auto-attachment."""
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    pdf_path = Path(resume.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume PDF missing on disk")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=resume.pdf_filename,
    )


@router.post("/{resume_id}/reparse", response_model=ResumeDetailResponse)
def reparse_resume(
    resume_id: int,
    session: Session = Depends(get_session),
    embedder: EmbedderProtocol = Depends(get_embedder),
) -> ResumeDetailResponse:
    """Re-extract bullets and recompute FastEmbed vectors from the stored PDF."""
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    pdf_path = Path(resume.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume PDF missing on disk")

    existing_bullets = session.exec(
        select(ResumeBullet).where(ResumeBullet.resume_id == resume_id)
    ).all()
    for bullet in existing_bullets:
        session.delete(bullet)
    session.flush()

    raw_text, skills, bullets = _store_parsed_bullets(
        session=session,
        resume_id=resume_id,
        pdf_path=pdf_path,
        embedder=embedder,
    )
    resume.raw_text = raw_text
    resume.track_skills_json = skills
    resume.updated_at = utc_now()
    session.add(resume)
    session.commit()
    session.refresh(resume)
    for bullet in bullets:
        session.refresh(bullet)
    return _build_detail(resume, bullets)

