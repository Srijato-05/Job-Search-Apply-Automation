"""FastAPI dependency providers for settings, DB sessions, and embeddings."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlmodel import Session

from app.config import Settings
from app.resumes.embedder import EmbedderProtocol


def get_settings(request: Request) -> Settings:
    """Return active application settings."""
    return request.app.state.settings


def get_engine(request: Request) -> Engine:
    """Return active SQLite SQLAlchemy engine."""
    return request.app.state.engine


def get_embedder(request: Request) -> EmbedderProtocol:
    """Return active embedding service (FastEmbed or test double)."""
    return request.app.state.embedder


def get_session(engine: Engine = Depends(get_engine)) -> Generator[Session, None, None]:
    """Yield a scoped SQLModel database session."""
    with Session(engine) as session:
        yield session

