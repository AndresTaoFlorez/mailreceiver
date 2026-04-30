from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

import os

from api.presentation.config import AGENT_HOST, AGENT_PORT
from api.shared.logger import get_logger

logger = get_logger("api")

AGENT_URL = f"http://{AGENT_HOST}:{AGENT_PORT}"
# When false the agent runs as a separate container/process (Docker).
# When true (default for local dev) the API spawns it as a subprocess.
_MANAGE_AGENT = os.getenv("MANAGE_AGENT", "true").lower() not in ("false", "0", "no")


class AgentManager:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        if not _MANAGE_AGENT:
            logger.info("MANAGE_AGENT=false — skipping agent subprocess start")
            return

        if self._process and self._process.poll() is None:
            logger.info("Agent already running (pid=%d)", self._process.pid)
            return

        logger.info("Starting agent on port %d", AGENT_PORT)
        self._process = subprocess.Popen(
            [
                sys.executable, "-m", "agent",
                "--host", AGENT_HOST,
                "--port", str(AGENT_PORT),
            ],
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        logger.info("Agent started (pid=%d)", self._process.pid)

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            logger.info("Stopping agent (pid=%d)", self._process.pid)
            self._process.terminate()
            self._process.wait(timeout=10)
            logger.info("Agent stopped")
        self._process = None

    def restart(self) -> None:
        self.stop()
        self.start()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        if self._process and self._process.poll() is None:
            return self._process.pid
        return None

    async def ensure_running(self) -> None:
        """Start the agent if it's not running. Wait until it responds to /health."""
        if self.is_running:
            return
        logger.warning("Agent is down, restarting automatically")
        self.start()
        # Wait up to 15s for the agent to respond
        import asyncio
        for _ in range(30):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{AGENT_URL}/health")
                    if resp.status_code == 200:
                        logger.info("Agent is back up (pid=%d)", self.pid)
                        return
            except Exception:
                pass
            await asyncio.sleep(0.5)
        logger.error("Agent failed to start after 15s")

    async def health(self) -> dict:
        if not self.is_running:
            return {"status": "down", "pid": None}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{AGENT_URL}/health")
                return {**resp.json(), "pid": self.pid}
        except Exception:
            return {"status": "unreachable", "pid": self.pid}
