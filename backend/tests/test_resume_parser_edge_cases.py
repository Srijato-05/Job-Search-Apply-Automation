"""Direct unit tests for Resume PDF Parser: multi-section, multi-page, wrapped bullets & edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.resumes.parser import _detect_section, _looks_like_job_header, parse_resume_pdf


def _make_pdf(path: Path, pages: list[list[str]]) -> Path:
    c = canvas.Canvas(str(path), pagesize=letter)
    for page_idx, lines in enumerate(pages):
        if page_idx > 0:
            c.showPage()
        c.setFont("Helvetica", 10)
        y = 750
        for line in lines:
            c.drawString(50, y, line)
            y -= 16
    c.save()
    return path


def test_parse_multi_section_multi_page_wrapped_bullets_and_prose_fallback(tmp_path: Path) -> None:
    """Verify section attribution, soft-wrapped bullets, job-header separation, and prose capture."""
    pdf_path = _make_pdf(
        tmp_path / "MultiPage_Resume.pdf",
        pages=[
            [
                "Aarav Sharma",
                "Professional Summary",
                "Senior distributed systems engineer building low-latency APIs across cloud-native platforms in Bengaluru.",
                "Work Experience",
                "Razorpay | Senior Backend Engineer | Jan 2023 - Present",
                "• Architected idempotent UPI settlement microservices in Go and Python",
                "handling over 5000 requests per second across Kubernetes clusters.",
                "- Cut Redis cache miss rate by 38% across high-throughput checkout paths.",
                "Acme Labs | Backend Developer | Mar 2020 - Dec 2022",
                "* Built FastAPI and PostgreSQL data pipelines with Docker and Terraform.",
            ],
            [
                "Personal Projects",
                "1. Built an open-source distributed cron scheduler using Apache Kafka and Rust.",
                "Technical Skills",
                "Python, Go, FastAPI, PostgreSQL, Redis, Apache Kafka, Kubernetes, Docker, Terraform",
                "Education",
                "B.Tech Computer Science, VTU (2016 - 2020)",
            ],
        ],
    )

    parsed = parse_resume_pdf(pdf_path)
    assert "Razorpay" in parsed.raw_text
    assert "Apache Kafka" in parsed.raw_text

    # Canonical sections properly tagged
    summary_bullets = [b for b in parsed.bullets if b.section_name == "summary"]
    exp_bullets = [b for b in parsed.bullets if b.section_name == "experience"]
    proj_bullets = [b for b in parsed.bullets if b.section_name == "projects"]

    assert len(summary_bullets) == 1
    assert "distributed systems engineer" in summary_bullets[0].bullet_text
    assert len(exp_bullets) >= 3
    # Wrapped line joined into bullet and all 3 expected bullets captured
    exp_text = " ".join(b.bullet_text for b in exp_bullets)
    assert "5000 requests per second across Kubernetes clusters." in exp_text
    assert "Cut Redis cache miss rate by 38%" in exp_text
    assert "Built FastAPI and PostgreSQL data pipelines" in exp_text
    assert len(proj_bullets) == 1
    assert "Apache Kafka" in proj_bullets[0].extracted_skills
    assert {"Python", "Go", "FastAPI", "PostgreSQL", "Redis", "Apache Kafka", "Kubernetes", "Docker", "Terraform"}.issubset(
        set(parsed.skills)
    )


def test_section_and_job_header_helpers_and_missing_file(tmp_path: Path) -> None:
    """Verify section/job-header heuristics and clean failure on nonexistent PDF paths."""
    assert _detect_section("Experience:") == "experience"
    assert _detect_section("TECH STACK") == "skills"
    assert _detect_section("Publications") == "certifications"
    assert _detect_section("A" * 70) is None

    assert _looks_like_job_header("Razorpay | SDE II | 2022 - Present") is True
    assert _looks_like_job_header("2021 - 2023") is True
    assert _looks_like_job_header("Built scalable microservices in Python.") is False

    # Short <15 char bullet is filtered out cleanly
    short_pdf = _make_pdf(
        tmp_path / "Short_Bullets.pdf",
        pages=[["Experience", "• Short", "• Engineered resilient Python event consumers with FastAPI and Redis."]],
    )
    parsed_short = parse_resume_pdf(short_pdf)
    assert len(parsed_short.bullets) == 1

    with pytest.raises(FileNotFoundError):
        parse_resume_pdf(tmp_path / "does_not_exist.pdf")

