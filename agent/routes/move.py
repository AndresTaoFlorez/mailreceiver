from __future__ import annotations

from litestar import Request, post
from pydantic import BaseModel, Field

from api.presentation.config import get_app_credentials
from agent.browser.base_step import StepContext
from agent.browser.pipeline import StepPipeline
from agent.browser.steps import build_login_pipeline, build_move_pipeline
from api.shared.logger import get_logger

logger = get_logger("agent")


class MoveItem(BaseModel):
    conversation_id: str = Field(description="Outlook thread id (data-convid)")
    source_folder: str = Field(description="Current folder the email is in")
    target_folder: str = Field(description="Exact analyst folder name to move to")


class MoveRequest(BaseModel):
    application: str = Field(description="Application key from config")
    moves: list[MoveItem] = Field(description="List of emails to move")


@post("/move")
async def move_handler(data: MoveRequest, request: Request) -> dict:
    if not data.moves:
        return {"status": "ok", "moves_done": 0, "moves_failed": 0}

    manager = request.app.state.session_manager
    creds = get_app_credentials(data.application)

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

        # Move
        move_ctx = StepContext(
            page=page,
            shared={
                "moves": [m.model_dump() for m in data.moves],
            },
        )
        move_results = await StepPipeline(build_move_pipeline()).run(move_ctx)

    return {
        "status": "ok",
        "application": data.application,
        "total": len(data.moves),
        "moves_done": move_ctx.shared.get("moves_done", 0),
        "moves_failed": move_ctx.shared.get("moves_failed", 0),
        "steps": move_results,
    }
