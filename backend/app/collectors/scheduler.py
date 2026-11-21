"""Background scheduler service for periodic ATS polling and aggregator runs."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlmodel import Session

from app.collectors.manager import CollectorManager
from app.config import Settings
from app.db.database import create_db_engine
from app.resumes.embedder import EmbedderProtocol

logger = logging.getLogger(__name__)


class CollectorScheduler:
    """Lightweight, resilient async scheduler running inside the FastAPI lifecycle."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        embedder: Optional[EmbedderProtocol] = None,
        interval_hours: int = 4,
    ):
        self.settings = settings or Settings()
        self.embedder = embedder
        self.interval_seconds = interval_hours * 3600
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self.manager = CollectorManager(settings=self.settings)

    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self, embedder: Optional[EmbedderProtocol] = None) -> None:
        """Start the background periodic collector loop."""
        if self.is_running():
            logger.info("CollectorScheduler is already active.")
            return

        if embedder:
            self.embedder = embedder

        self._running = True
        self._task = asyncio.create_task(self._periodic_loop(), name="collector_scheduler")
        logger.info(f"CollectorScheduler started (interval={self.interval_seconds // 3600}h).")

    def stop(self) -> None:
        """Stop the background scheduler loop gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("CollectorScheduler cancelled.")

    async def _periodic_loop(self) -> None:
        """Continuous execution loop with interval sleep and error isolation."""
        engine = create_db_engine(self.settings.db_path)

        while self._running:
            try:
                logger.info("CollectorScheduler: commencing scheduled collection run...")
                if self.embedder is not None:
                    with Session(engine) as session:
                        await self.manager.collect_all_watched(
                            session=session,
                            embedder=self.embedder,
                            force=False,
                        )
                else:
                    logger.warning("CollectorScheduler: embedder service not ready, skipping cycle.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"CollectorScheduler run encountered error: {e}")

            # Sleep until next scheduled interval
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

