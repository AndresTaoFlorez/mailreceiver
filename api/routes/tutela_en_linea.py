from __future__ import annotations

import httpx
from litestar import Controller, get, post
from litestar.params import Parameter
from litestar.status_codes import HTTP_200_OK
from pydantic import BaseModel, Field

from api.config import AGENT_HOST, AGENT_PORT, load_config
from domain.database import async_session
from domain.repository import get_conversations, count_conversations
from domain.schemas import PaginatedResponse

AGENT_URL = f"http://{AGENT_HOST}:{AGENT_PORT}"
APP_NAME = "tutela_en_linea"


class ScrapeRequest(BaseModel):
    folder: str = Field(
        description="Outlook folder name",
        examples=["Bandeja de entrada", "DIEGO TUTELA (S24)"],
    )
    page: int | None = Field(default=None, ge=1, description="Page number (default from config)")
    per_page: int | None = Field(default=None, ge=1, description="Items per page (default from config)")


def _pagination(page: int | None, per_page: int | None) -> tuple[int, int]:
    cfg = load_config()
    p = page or cfg["default_page"]
    pp = per_page or cfg["default_per_page"]
    pp = min(pp, cfg["max_per_page"])
    return p, pp


class TutelaEnLineaController(Controller):
    path = "/tutela-en-linea"
    tags = ["Tutela en Linea"]

    @post(
        "/unread-conversations",
        summary="Scrape unread conversations and save to DB",
        description=(
            "Scrapes unread conversations from Outlook, saves new ones to PostgreSQL "
            "(duplicates skipped by conversation_id), returns paginated results."
        ),
        status_code=HTTP_200_OK,
    )
    async def scrape_unread_conversations(self, data: ScrapeRequest) -> dict:
        from api.app import agent_manager
        await agent_manager.ensure_running()

        async with httpx.AsyncClient(timeout=360.0) as client:
            response = await client.post(
                f"{AGENT_URL}/process",
                json={
                    "application": APP_NAME,
                    "folder": data.folder,
                    "unread_only": True,
                },
            )
        agent_result = response.json()
        new_saved = agent_result.get("new_saved", 0)

        page, per_page = _pagination(data.page, data.per_page)
        offset = (page - 1) * per_page
        async with async_session() as db:
            total = await count_conversations(db, APP_NAME, data.folder)
            rows = await get_conversations(db, APP_NAME, data.folder, limit=per_page, offset=offset)

        return PaginatedResponse.build(rows, total, page, per_page, new_saved).model_dump()

    @get(
        "/conversations",
        summary="Get stored conversations (paginated)",
        description="Returns previously scraped conversations from the database. No scraping is triggered.",
        status_code=HTTP_200_OK,
    )
    async def get_stored_conversations(
        self,
        folder: str = Parameter(query="folder", description="Outlook folder name"),
        page: int | None = Parameter(query="page", default=None, ge=1),
        per_page: int | None = Parameter(query="per_page", default=None, ge=1),
    ) -> dict:
        p, pp = _pagination(page, per_page)
        offset = (p - 1) * pp
        async with async_session() as db:
            total = await count_conversations(db, APP_NAME, folder)
            rows = await get_conversations(db, APP_NAME, folder, limit=pp, offset=offset)

        return PaginatedResponse.build(rows, total, p, pp).model_dump()
