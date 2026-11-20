"""Tests for multi-resume PDF upload/download/cascade-delete and real FastEmbed ONNX vectors."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.models import ResumeBullet
from app.resumes.embedder import FastEmbedService, cosine_similarity


def test_resume_upload_parse_download_patch_reparse_and_delete(
    client: TestClient,
    auth_headers: dict[str, str],
    app_with_mock_embedder,
    sample_backend_pdf: Path,
    sample_fullstack_pdf: Path,
) -> None:
    pdf_bytes = sample_backend_pdf.read_bytes()

    # Upload Backend PDF
    upload_resp = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={
            "track_name": "Backend Track",
            "target_titles": '["Backend Engineer", "SDE 2 Backend"]',
            "search_locations": "Bangalore, Hyderabad",
            "cover_template": "Applying to {{company}} for {{role_title}}.",
        },
        files={"file": ("Backend_Python_Go.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    detail = upload_resp.json()
    resume_id = detail["id"]
    assert detail["track_name"] == "Backend Track"
    assert detail["search_locations_json"] == ["Bengaluru", "Hyderabad"]
    assert detail["bullet_count"] >= 3
    assert any("Kafka" in b["bullet_text"] for b in detail["bullets"])
    assert all(b["has_embedding"] for b in detail["bullets"])
    assert {"Python", "Go", "FastAPI", "PostgreSQL", "Apache Kafka"}.issubset(
        set(detail["track_skills_json"])
    )

    # Upload second resume (FullStack)
    upload_fs = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "FullStack Track", "target_titles": "Full Stack Engineer"},
        files={"file": ("FullStack_React_Node.pdf", sample_fullstack_pdf.read_bytes(), "application/pdf")},
    )
    assert upload_fs.status_code == 201

    # List resumes returns both
    listed = client.get("/api/v1/resumes", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    # Download binary PDF matches byte-for-byte
    dl_resp = client.get(f"/api/v1/resumes/{resume_id}/file", headers=auth_headers)
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"].startswith("application/pdf")
    assert dl_resp.content == pdf_bytes

    # Patch track metadata
    patch_resp = client.patch(
        f"/api/v1/resumes/{resume_id}",
        headers=auth_headers,
        json={"track_name": "Core Backend Track", "is_active": True},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["track_name"] == "Core Backend Track"

    # Reparse keeps bullets clean
    reparse_resp = client.post(f"/api/v1/resumes/{resume_id}/reparse", headers=auth_headers)
    assert reparse_resp.status_code == 200
    assert reparse_resp.json()["bullet_count"] == detail["bullet_count"]

    # Reject non-PDF uploads
    bad_upload = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        data={"track_name": "Invalid"},
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert bad_upload.status_code == 422

    # Delete cascades bullets and deletes unreferenced file on disk
    resumes_dir = app_with_mock_embedder.state.settings.resumes_dir
    assert len(list(resumes_dir.glob("*Backend_Python_Go.pdf"))) == 1
    del_resp = client.delete(f"/api/v1/resumes/{resume_id}", headers=auth_headers)
    assert del_resp.status_code == 204
    assert len(list(resumes_dir.glob("*Backend_Python_Go.pdf"))) == 0

    with Session(app_with_mock_embedder.state.engine) as session:
        remaining = session.exec(
            select(ResumeBullet).where(ResumeBullet.resume_id == resume_id)
        ).all()
        assert remaining == []


def test_real_fastembed_bge_small_semantic_alignment(
    real_fastembed_service: FastEmbedService,
) -> None:
    """Verify ONNX Runtime loads BAAI/bge-small-en-v1.5 on Windows and ranks backend bullets accurately."""
    jd_req = "Design and scale event-driven Kafka consumer pipelines in Python and FastAPI."
    backend_bullet = "Architected async Apache Kafka event consumers in Python and FastAPI processing 2M events/day."
    frontend_bullet = "Styled responsive landing pages using Tailwind CSS animations and Figma prototypes."

    vectors = real_fastembed_service.embed_texts([jd_req, backend_bullet, frontend_bullet])
    assert vectors.shape == (3, 384)

    sim_backend = cosine_similarity(vectors[0], vectors[1])
    sim_frontend = cosine_similarity(vectors[0], vectors[2])

    assert sim_backend > 0.72
    assert sim_backend > sim_frontend + 0.15

