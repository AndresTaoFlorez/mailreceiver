from __future__ import annotations

import asyncio
import os

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from api.presentation.config import get as cfg
from api.shared.logger import get_logger

logger = get_logger("agent")

# HEADLESS env var overrides config.json — always True in Docker (no display server)
_HEADLESS_ENV = os.getenv("HEADLESS", "").lower()
_FORCE_HEADLESS: bool | None = True if _HEADLESS_ENV in ("1", "true", "yes") else (
    False if _HEADLESS_ENV in ("0", "false", "no") else None
)


class BrowserSession:
    """A single isolated browser instance (one Chromium process, one context, one page)."""

    def __init__(self, name: str = "default"):
        self.name = name
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        headless = _FORCE_HEADLESS if _FORCE_HEADLESS is not None else cfg("headless")
        # --no-sandbox is required in Docker/Linux (no user namespace support)
        args = ["--no-sandbox", "--disable-setuid-sandbox"] if headless else []
        logger.info("Starting browser session '%s' (headless=%s)", self.name, headless)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless, args=args)
        self._context = await self._browser.new_context(
            user_agent=cfg("user_agent"),
            viewport={"width": cfg("viewport_width"), "height": cfg("viewport_height")},
        )
        self._page = await self._context.new_page()
        logger.info("Browser session '%s' started", self.name)

    async def get_page(self) -> Page:
        if self._page is None:
            raise RuntimeError(f"BrowserSession '{self.name}' not started. Call start() first.")
        return self._page

    async def get_context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError(f"BrowserSession '{self.name}' not started. Call start() first.")
        return self._context

    @property
    def is_alive(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        logger.info("Browser session '%s' closed", self.name)


class SessionManager:
    """Manages one BrowserSession per application, created on demand."""

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def get(self, app_name: str) -> tuple[BrowserSession, asyncio.Lock]:
        """Return (session, lock) for the given application, starting the browser if needed."""
        async with self._global_lock:
            if app_name not in self._sessions:
                session = BrowserSession(name=app_name)
                await session.start()
                self._sessions[app_name] = session
                self._locks[app_name] = asyncio.Lock()
                logger.info("Created new browser session for '%s'", app_name)

            session = self._sessions[app_name]
            if not session.is_alive:
                logger.warning("Session '%s' died, restarting", app_name)
                await session.close()
                session = BrowserSession(name=app_name)
                await session.start()
                self._sessions[app_name] = session

            return self._sessions[app_name], self._locks[app_name]

    async def close_all(self) -> None:
        for name, session in self._sessions.items():
            logger.info("Closing session '%s'", name)
            await session.close()
        self._sessions.clear()
        self._locks.clear()

    async def close(self, app_name: str) -> None:
        async with self._global_lock:
            if app_name in self._sessions:
                await self._sessions[app_name].close()
                del self._sessions[app_name]
                del self._locks[app_name]

    @property
    def active_sessions(self) -> list[str]:
        return [name for name, s in self._sessions.items() if s.is_alive]
