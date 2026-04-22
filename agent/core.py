from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from litestar import Litestar, get

from agent.browser.session import SessionManager
from agent.routes.process import process_handler
from shared.logger import get_logger

logger = get_logger("agent")


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    app.state.session_manager = SessionManager()
    logger.info("Agent ready - session manager initialized")

    yield

    await app.state.session_manager.close_all()
    logger.info("Agent closed - all sessions terminated")


@get("/health")
async def agent_health() -> dict:
    return {"status": "healthy", "service": "mailwindow-agent"}


app = Litestar(
    route_handlers=[agent_health, process_handler],
    lifespan=[lifespan],
    debug=True,
)
