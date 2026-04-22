from __future__ import annotations

from litestar import Request, post
from pydantic import BaseModel, Field

from api.config import get_app_credentials
from agent.browser.base_step import StepContext
from agent.browser.pipeline import StepPipeline
from agent.browser.steps import build_login_pipeline, build_scrape_pipeline
from domain.database import async_session
from domain.repository import save_conversations
from domain.schemas import ScrapedEmail, ScrapeResult
from shared.logger import get_logger

logger = get_logger("agent")


class ProcessRequest(BaseModel):
    application: str = Field(description="Application key from config")
    folder: str = Field(description="Outlook folder name")
    unread_only: bool = Field(default=False, description="Filter unread conversations only")


@post("/process")
async def process_handler(data: ProcessRequest, request: Request) -> dict:
    manager = request.app.state.session_manager

    creds = get_app_credentials(data.application)

    # Get or create an isolated browser session for this application
    session, lock = await manager.get(data.application)

    if not session.is_alive:
        return {"status": "error", "message": f"Browser session for '{data.application}' not active"}

    async with lock:
        page = await session.get_page()

        # Login
        login_ctx = StepContext(
            page=page,
            shared={
                "outlook_user": creds["outlook_user"],
                "outlook_password": creds["outlook_password"],
            },
        )
        login_results = await StepPipeline(build_login_pipeline()).run(login_ctx)

        if any(r.get("status") == "failed" for r in login_results.values()):
            return {"status": "error", "message": "Login failed", "steps": login_results}

        # Scrape
        scrape_ctx = StepContext(
            page=page,
            shared={"folder": data.folder, "unread_only": data.unread_only},
        )
        scrape_results = await StepPipeline(build_scrape_pipeline()).run(scrape_ctx)

        if any(r.get("status") == "failed" for r in scrape_results.values()):
            return {"status": "error", "message": "Scrape failed", "steps": scrape_results}

    raw_conversations = scrape_ctx.shared.get("conversations", [])
    conversations = [ScrapedEmail(**e) for e in raw_conversations]

    # Persist to PostgreSQL (skip duplicates by conversation_id)
    inserted = 0
    async with async_session() as db:
        inserted = await save_conversations(db, conversations, data.application, data.folder)

    result = ScrapeResult(
        status="ok",
        application=data.application,
        folder=data.folder,
        expected_unread_messages=scrape_ctx.shared.get("expected_unread"),
        scraped_conversations=scrape_ctx.shared.get("unread_count", 0),
        scroll_exhausted=scrape_ctx.shared.get("scroll_exhausted", False),
        complete=scrape_ctx.shared.get("complete", False),
        conversations=conversations,
        new_saved=inserted,
    )
    return result.model_dump()
