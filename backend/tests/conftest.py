"""Shared pytest fixtures: isolated DB/settings, real ReportLab PDFs, and FastEmbed."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

os.environ["JOB_AUTOMATION_SKIP_DEFAULT_APP"] = "1"

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.resumes.embedder import FastEmbedService, l2_normalize_matrix  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]


class DeterministicTestEmbedder:
    """Fast deterministic embedder for CRUD tests that don't invoke ONNX Runtime."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed_texts(self, texts):
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        rows = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for token in text.lower().split():
                idx = sum(ord(c) for c in token) % self.dim
                vec[idx] += 1.0
            rows.append(vec)
        return l2_normalize_matrix(np.vstack(rows))


def _write_resume_pdf(path: Path, lines: list[str]) -> Path:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 750
    c.setFont("Helvetica", 10)
    for line in lines:
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = 750
        c.drawString(50, y, line)
        y -= 16
    c.save()
    return path


@pytest.fixture()
def sample_backend_pdf(tmp_path: Path) -> Path:
    """Generate a realistic Backend Engineer resume PDF via ReportLab."""
    return _write_resume_pdf(
        tmp_path / "Backend_Python_Go.pdf",
        [
            "Aarav Sharma - Senior Backend Engineer | Bengaluru, India",
            "Summary",
            "Backend specialist building low-latency microservices in Python and Go.",
            "Experience",
            "Acme Fintech | Backend Engineer | Jan 2022 - Present",
            "• Architected async Apache Kafka event consumers in Python and FastAPI processing 2M events/day.",
            "• Cut PostgreSQL p99 latency by 42% using composite indexing and Redis read-through caching.",
            "• Containerized services with Docker and deployed to AWS EKS using GitHub Actions CI/CD.",
            "Skills",
            "Python, Go, FastAPI, PostgreSQL, Redis, Apache Kafka, Docker, Kubernetes, AWS",
        ],
    )


@pytest.fixture()
def sample_fullstack_pdf(tmp_path: Path) -> Path:
    """Generate a realistic Full-Stack Engineer resume PDF via ReportLab."""
    return _write_resume_pdf(
        tmp_path / "FullStack_React_Node.pdf",
        [
            "Aarav Sharma - Full-Stack Engineer | Bengaluru, India",
            "Experience",
            "Nova Web | Full-Stack Developer | Mar 2020 - Dec 2021",
            "• Developed responsive React and TypeScript analytics dashboards with Tailwind CSS.",
            "• Built GraphQL and Node.js Express APIs backed by MongoDB and PostgreSQL.",
            "• Implemented automated end-to-end UI test suites using Playwright and Vitest.",
            "Skills",
            "React, TypeScript, Node.js, Express.js, GraphQL, MongoDB, PostgreSQL, Tailwind CSS",
        ],
    )


@pytest.fixture()
def temp_settings(tmp_path: Path) -> Settings:
    """Isolated runtime Settings storing DB/resumes inside tmp_path and sharing ONNX cache."""
    return Settings(
        data_dir=tmp_path / "data",
        fastembed_cache_dir=_REPO_ROOT / ".fastembed_cache",
        enable_background_scheduler=False,
    )


@pytest.fixture()
def app_with_mock_embedder(temp_settings: Settings):
    """FastAPI app using fast deterministic embedder for DB/Vault/API tests."""
    return create_app(settings=temp_settings, embedder=DeterministicTestEmbedder())


@pytest.fixture()
def client(app_with_mock_embedder) -> TestClient:
    """Authorized TestClient carrying valid X-Local-Token."""
    return TestClient(app_with_mock_embedder)


@pytest.fixture()
def auth_headers(app_with_mock_embedder) -> dict[str, str]:
    """Valid X-Local-Token headers for API calls."""
    return {"X-Local-Token": app_with_mock_embedder.state.local_token}


@pytest.fixture(scope="session")
def real_fastembed_service() -> FastEmbedService:
    """Real FastEmbed BAAI/bge-small-en-v1.5 ONNX service cached in workspace."""
    return FastEmbedService(
        model_name="BAAI/bge-small-en-v1.5",
        cache_dir=_REPO_ROOT / ".fastembed_cache",
        dim=384,
    )

