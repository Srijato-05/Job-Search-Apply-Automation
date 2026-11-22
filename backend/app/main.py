"""FastAPI application factory with loopback token security and restricted CORS."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac
import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.api.collectors import router as collectors_router
from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router
from app.api.vault import router as vault_router
from app.api.watchlist import router as watchlist_router
from app.collectors.jobspy_collector import JOBSPY_AVAILABLE
from app.collectors.manager import CollectionProgress, recover_stale_runs, seed_watchlist
from app.collectors.scheduler import CollectorScheduler
from app.config import Settings, ensure_data_dirs, get_or_create_local_token
from app.db.database import create_db_engine, init_db
from app.db.models import Company
from app.resumes.embedder import EmbedderProtocol, FastEmbedService

logger = logging.getLogger(__name__)


def _configure_rotating_log(cfg: Settings) -> None:
    """Attach a 5 MB x 3 rotating file handler at data/app.log (20 MB hard cap)."""
    log_path = cfg.data_dir / "app.log"
    root_logger = logging.getLogger()
    for h in root_logger.handlers:
        if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_path.resolve()):
            return
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))


def create_app(
    settings: Optional[Settings] = None,
    embedder: Optional[EmbedderProtocol] = None,
) -> FastAPI:
    """Construct and configure the JobAutomation FastAPI application."""
    cfg = settings or Settings()
    ensure_data_dirs(cfg)
    _configure_rotating_log(cfg)
    local_token = get_or_create_local_token(cfg.data_dir)
    engine = create_db_engine(cfg.db_path)
    init_db(engine)

    embedder_service = embedder or FastEmbedService(
        model_name=cfg.embedding_model_name,
        cache_dir=cfg.fastembed_cache_dir,
        dim=cfg.embedding_dim,
    )

    # Seed default India tech watchlist & recover any interrupted runs from prior crash
    with Session(engine) as session:
        seed_watchlist(session)
        recovered = recover_stale_runs(session)
        if recovered:
            logger.warning(f"Recovered {recovered} stale collector_runs marked as 'interrupted'.")
        watched_count = len(
            session.exec(select(Company).where(Company.is_watched.is_(True))).all()
        )

    collection_progress = CollectionProgress()
    collection_lock = asyncio.Lock()
    scheduler = CollectorScheduler(
        settings=cfg,
        embedder=embedder_service,
        interval_hours=cfg.collector_interval_hours,
        engine=engine,
        progress=collection_progress,
        lock=collection_lock,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info(
            "JobAutomation Local Backend ready | URL: http://%s:%s/docs | "
            "Watched ATS: %d | Scheduler: %s (%dh) | JobSpy: %s | Log: %s",
            cfg.local_host,
            cfg.local_port,
            watched_count,
            "ON" if cfg.enable_background_scheduler else "OFF",
            cfg.collector_interval_hours,
            "installed" if JOBSPY_AVAILABLE else "not installed",
            cfg.data_dir / "app.log",
        )
        if cfg.enable_background_scheduler:
            scheduler.start(embedder=embedder_service)
        try:
            yield
        finally:
            scheduler.stop()

    app = FastAPI(
        title="JobAutomation Local Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = cfg
    app.state.local_token = local_token
    app.state.engine = engine
    app.state.embedder = embedder_service
    app.state.scheduler = scheduler
    app.state.collection_progress = collection_progress
    app.state.collection_lock = collection_lock

    @app.middleware("http")
    async def verify_local_token(request: Request, call_next):
        if request.method != "OPTIONS" and request.url.path.startswith("/api/v1"):
            provided = request.headers.get("X-Local-Token", "")
            if not hmac.compare_digest(provided, app.state.local_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing X-Local-Token"},
                )
        return await call_next(request)

    # Added after verify_local_token so CORSMiddleware wraps outermost and handles preflights/headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins_list,
        allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Local-Token"],
    )

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    app.include_router(vault_router, prefix="/api/v1")
    app.include_router(resumes_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(watchlist_router, prefix="/api/v1")
    app.include_router(collectors_router, prefix="/api/v1")

    return app


app: Optional[FastAPI] = (
    None if os.environ.get("JOB_AUTOMATION_SKIP_DEFAULT_APP") == "1" else create_app()
)
