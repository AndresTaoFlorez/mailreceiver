from __future__ import annotations

from litestar import Litestar, Request, get, post
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED

from api import config
from api.agent_manager import AgentManager
from api.config import ensure_dirs
from api.database import init_db
from api.routes.tutela_en_linea import TutelaEnLineaController
from api.routes.justicia_xxi_web import JusticiaXxiWebController
from agent.browser import scraping_config

agent_manager = AgentManager()


# --- Config ---

@get("/config", tags=["config"])
async def get_config() -> dict:
    return config.load_config()


@post("/config", tags=["config"])
async def update_config(request: Request) -> dict:
    body = await request.json()
    updated = config.save_config(body)
    return {"status": "ok", "config": updated}


# --- Scraping config ---

@get("/scraping-config", tags=["config"])
async def get_scraping_config() -> dict:
    return scraping_config.load()


@post("/scraping-config", tags=["config"])
async def update_scraping_config(request: Request) -> dict:
    body = await request.json()
    updated = scraping_config.save(body)
    return {"status": "ok", "config": updated}


# --- Agent control ---

@get("/agent/status", tags=["agent"])
async def agent_status() -> dict:
    return await agent_manager.health()


@post("/agent/restart", tags=["agent"])
async def agent_restart() -> dict:
    agent_manager.restart()
    return {"status": "ok", "message": "Agent restarted", "pid": agent_manager.pid}


@post("/agent/stop", tags=["agent"])
async def agent_stop() -> dict:
    agent_manager.stop()
    return {"status": "ok", "message": "Agent stopped"}


@post("/agent/start", tags=["agent"])
async def agent_start() -> dict:
    agent_manager.start()
    return {"status": "ok", "message": "Agent started", "pid": agent_manager.pid}


# --- Debug ---

@post(
    "/debug",
    summary="Debug incoming request",
    description="Accepts any JSON payload and echoes back headers, body, and query params for inspection.",
    tags=["debug"],
)
async def debug(request: Request) -> dict:
    body = await request.json()
    return {
        "headers": dict(request.headers),
        "query": dict(request.query_params),
        "body": body,
    }


@get("/health")
async def health() -> dict:
    return {"status": "healthy"}


# --- Lifecycle ---

async def on_startup() -> None:
    ensure_dirs()
    await init_db()
    agent_manager.start()


async def on_shutdown() -> None:
    agent_manager.stop()


from litestar.openapi import OpenAPIConfig

app = Litestar(
    route_handlers=[
        get_config,
        update_config,
        get_scraping_config,
        update_scraping_config,
        agent_status,
        agent_restart,
        agent_stop,
        agent_start,
        debug,
        health,
        TutelaEnLineaController,
        JusticiaXxiWebController,
    ],
    on_startup=[on_startup],
    on_shutdown=[on_shutdown],
    openapi_config=OpenAPIConfig(title="Mail Receiver", version="1.0.0"),
)
