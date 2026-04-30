"""
presentation/watcher.py — Background watcher per application.

Runs a continuous async loop that:
  1. Scrapes unread conversations from all configured level folders
  2. Runs dispatch for each configured level
  3. Sleeps for `interval_seconds` and repeats

One watcher task per application. Start/stop via API endpoints.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from api.infrastructure.database import async_session
from api.infrastructure import folder_config_repository as fc_repo
from api.application.dispatcher import dispatch_level
from api.application.ticket_service import create_tickets_for_app
from api.shared.logger import get_logger

logger = get_logger("watcher")


class AppWatcher:
    def __init__(self, app_name: str, agent_url: str, missaquest_url: str = "", create_tickets: bool = False) -> None:
        self.app_name = app_name
        self.agent_url = agent_url
        self.missaquest_url = missaquest_url
        self.create_tickets = create_tickets
        self._task: asyncio.Task | None = None
        self._running = False
        self.interval_seconds: int = 300
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.runs: int = 0

    def start(self, interval_seconds: int = 300) -> None:
        if self._running:
            logger.info("Watcher for '%s' already running", self.app_name)
            return
        self.interval_seconds = interval_seconds
        self._running = True
        self._task = asyncio.create_task(self._loop(), name=f"watcher_{self.app_name}")
        logger.info("Watcher started for '%s' (interval=%ds)", self.app_name, interval_seconds)

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        logger.info("Watcher stopped for '%s'", self.app_name)

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {
            "app": self.app_name,
            "running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "runs": self.runs,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
        }

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._run_cycle()
                self.last_error = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.error("Watcher cycle error for '%s': %s", self.app_name, e)

            await asyncio.sleep(self.interval_seconds)

    async def _run_cycle(self) -> None:
        self.last_run_at = datetime.now(timezone.utc)
        self.runs += 1
        logger.info("Watcher cycle #%d for '%s'", self.runs, self.app_name)

        # 1. Get configured level folders
        async with async_session() as db:
            level_folders = await fc_repo.get_folder_configs(
                db, application=self.app_name, active_only=True, analyst_only=False,
            )

        if not level_folders:
            logger.warning("Watcher: no level folders configured for '%s'", self.app_name)
            return

        levels = sorted({fc.level for fc in level_folders if fc.level is not None})

        # 2. Scrape each folder via the agent
        for fc in level_folders:
            try:
                async with httpx.AsyncClient(timeout=360.0) as client:
                    resp = await client.post(
                        f"{self.agent_url}/process",
                        json={
                            "application": self.app_name,
                            "folder": fc.folder_name,
                            "unread_only": True,
                            "extraction_mode": "latest",
                            "level": fc.level,
                        },
                    )
                result = resp.json()
                logger.info(
                    "Watcher scraped '%s' → new_saved=%s",
                    fc.folder_name, result.get("new_saved", 0),
                )
            except Exception as e:
                logger.error("Watcher scrape error for folder '%s': %s", fc.folder_name, e)

        # 3. Dispatch each level
        for level in levels:
            try:
                async with async_session() as db:
                    result = await dispatch_level(db, self.app_name, level)

                redirects = result.get("redirects", [])
                logger.info(
                    "Watcher dispatch level=%d → assigned=%d redirected=%d queued=%d",
                    level, result.get("total_assigned", 0),
                    len(redirects), result.get("queued", 0),
                )

                # Move redirected emails in Outlook
                if redirects:
                    move_payload = [
                        {
                            "conversation_id": r["conversation_id"],
                            "source_folder": r["source_folder"],
                            "target_folder": r["target_folder"],
                        }
                        for r in redirects
                    ]
                    try:
                        async with httpx.AsyncClient(timeout=600.0) as client:
                            await client.post(
                                f"{self.agent_url}/move",
                                json={"application": self.app_name, "moves": move_payload},
                            )
                    except Exception as e:
                        logger.error("Watcher move error: %s", e)

            except Exception as e:
                logger.error("Watcher dispatch error level=%d: %s", level, e)

        # 4. Create tickets for newly assigned conversations
        if self.create_tickets and self.missaquest_url:
            try:
                async with async_session() as db:
                    result = await create_tickets_for_app(
                        db, self.app_name, self.missaquest_url,
                    )
                logger.info(
                    "Watcher tickets app=%s created=%d failed=%d",
                    self.app_name,
                    result.get("tickets_created", 0),
                    result.get("tickets_failed", 0),
                )
            except Exception as e:
                logger.error("Watcher ticket creation error app=%s: %s", self.app_name, e)


class WatcherManager:
    """Manages one AppWatcher per application."""

    def __init__(self, agent_url: str, missaquest_url: str = "") -> None:
        self._agent_url = agent_url
        self._missaquest_url = missaquest_url
        self._watchers: dict[str, AppWatcher] = {}

    def get(self, app_name: str, create_tickets: bool = False) -> AppWatcher:
        if app_name not in self._watchers:
            self._watchers[app_name] = AppWatcher(
                app_name, self._agent_url,
                missaquest_url=self._missaquest_url,
                create_tickets=create_tickets,
            )
        return self._watchers[app_name]

    def stop_all(self) -> None:
        for w in self._watchers.values():
            w.stop()
