"""Deterministic PDF resume section and bullet point extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from app.vault.taxonomy import extract_skills_from_text

_BULLET_PREFIX = re.compile(r"^\s*(?:[•●▪▫◦‣⁃\-–—*]|\d+[.)])\s+")

_SECTION_HEADERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("summary", re.compile(r"^(?:professional\s+)?(?:summary|profile|objective|about\s+me)\s*:?$", re.I)),
    ("experience", re.compile(r"^(?:work\s+|professional\s+)?(?:experience|employment(?:\s+history)?|career\s+history)\s*:?$", re.I)),
    ("projects", re.compile(r"^(?:key\s+|personal\s+|academic\s+)?projects?\s*:?$", re.I)),
    ("skills", re.compile(r"^(?:technical\s+|core\s+)?(?:skills|technologies|tech\s+stack|competencies)\s*:?$", re.I)),
    ("education", re.compile(r"^education(?:al\s+qualifications?)?\s*:?$", re.I)),
    ("certifications", re.compile(r"^(?:certifications?|awards|achievements|publications)\s*:?$", re.I)),
)


@dataclass
class ExtractedBullet:
    """Single verbatim resume bullet or accomplishment sentence."""

    section_name: str
    bullet_order: int
    bullet_text: str
    extracted_skills: list[str] = field(default_factory=list)


@dataclass
class ParsedResume:
    """Complete deterministic extraction output from a Resume PDF."""

    raw_text: str
    bullets: list[ExtractedBullet]
    skills: list[str]


def _extract_raw_text(pdf_path: Path) -> str:
    """Extract text page-by-page using pdfplumber, falling back to pypdf if empty."""
    pages_text: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=False) or ""
            if text.strip():
                pages_text.append(text)

    combined = "\n".join(pages_text).strip()
    if combined:
        return combined

    reader = PdfReader(str(pdf_path))
    fallback_pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(p for p in fallback_pages if p.strip()).strip()


def _detect_section(line: str) -> str | None:
    """Return canonical section name if line looks like a resume heading."""
    cleaned = " ".join(line.strip().split())
    if not cleaned or len(cleaned) > 60:
        return None
    for section_name, pattern in _SECTION_HEADERS:
        if pattern.match(cleaned):
            return section_name
    return None


def _looks_like_job_header(line: str) -> bool:
    """Heuristic check so wrapped bullets don't merge into subsequent job title/date headers."""
    if "|" in line and any(yr in line for yr in ("201", "202", "Present", "Current")):
        return True
    if re.search(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})\s*[-–—]\s*(?:Present|Current|\d{4})", line, re.I):
        return True
    return False


def parse_resume_pdf(pdf_path: Path) -> ParsedResume:
    """Parse a PDF resume deterministically into raw text, verbatim bullets, and canonical skills."""
    raw_text = _extract_raw_text(pdf_path)
    lines = [ln.rstrip() for ln in raw_text.splitlines()]

    current_section = "header"
    bullets: list[ExtractedBullet] = []
    pending_bullet: str | None = None
    pending_section = "experience"

    def _flush_pending() -> None:
        nonlocal pending_bullet
        if pending_bullet:
            cleaned = " ".join(pending_bullet.split()).strip()
            if len(cleaned) >= 15:
                bullets.append(
                    ExtractedBullet(
                        section_name=pending_section,
                        bullet_order=len(bullets),
                        bullet_text=cleaned,
                        extracted_skills=extract_skills_from_text(cleaned),
                    )
                )
            pending_bullet = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            _flush_pending()
            continue

        section = _detect_section(stripped)
        if section is not None:
            _flush_pending()
            current_section = section
            continue

        if _BULLET_PREFIX.match(stripped):
            _flush_pending()
            pending_bullet = _BULLET_PREFIX.sub("", stripped, count=1).strip()
            pending_section = current_section if current_section != "header" else "experience"
            continue

        if pending_bullet is not None:
            if _looks_like_job_header(stripped):
                _flush_pending()
            else:
                # Merge soft-wrapped continuation lines into the active bullet.
                pending_bullet = f"{pending_bullet} {stripped}"
                continue

        # Capture substantial summary/experience sentences even when PDF bullets lack marker glyphs.
        if current_section in {"experience", "projects", "summary"} and not _looks_like_job_header(stripped):
            if len(stripped) >= 40 and " " in stripped:
                bullets.append(
                    ExtractedBullet(
                        section_name=current_section,
                        bullet_order=len(bullets),
                        bullet_text=" ".join(stripped.split()),
                        extracted_skills=extract_skills_from_text(stripped),
                    )
                )

    _flush_pending()
    skills = extract_skills_from_text(raw_text)
    return ParsedResume(raw_text=raw_text, bullets=bullets, skills=skills)

