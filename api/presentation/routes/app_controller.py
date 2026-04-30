"""
api/routes/app_controller.py — Factory for per-application controllers.

Each application gets the same endpoints: scrape, conversations, folder-config,
specialists-folder, assign, assignments. Only the app_name, path, and tags differ.
"""

from __future__ import annotations

import math
import uuid
from functools import partial

import httpx
from litestar import Controller, get, post, put, delete
from litestar.params import Parameter
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import NotFoundException
from pydantic import BaseModel, Field

from api.presentation.config import AGENT_HOST, AGENT_PORT, MISSAQUEST_URL, load_config
from api.shared.logger import get_logger

logger = get_logger("app_controller")
from api.infrastructure.database import async_session
from api.infrastructure import folder_config_repository as fc_repo
from api.infrastructure import assignment_repository as assign_repo
from api.infrastructure import especialist_repository as esp_repo
from api.infrastructure.email_repository import get_conversations, count_conversations
from api.application.dispatcher import dispatch_level
from api.application.ticket_service import create_tickets_for_app
from api.domain.schemas import FolderConfigCreate, FolderConfigUpdate
from api.domain.mappers import (
    ok, ok_list, ok_page,
    map_email, map_folder_config, map_assignment,
)

AGENT_URL = f"http://{AGENT_HOST}:{AGENT_PORT}"


class ScrapeRequest(BaseModel):
    folder: str | None = Field(default=None)
    extraction_mode: str = Field(default="latest", examples=["latest"])


def _pagination(page: int | None, per_page: int | None) -> tuple[int, int]:
    cfg = load_config()
    p = page or cfg["default_page"]
    pp = per_page or cfg["default_per_page"]
    pp = min(pp, cfg["max_per_page"])
    return p, pp


def _parse_csv(value: str | None) -> list[str] | None:
    """Parse comma-separated string into list, or None."""
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def create_app_controller(
    app_name: str,
    path: str,
    tags: list[str],
    assign_specialists: bool = False,
    watcher: bool = False,
    create_tickets: bool = False,
) -> type[Controller]:
    """Create a Litestar Controller class scoped to a specific application."""

    class AppController(Controller):

        @post(
            "/unread-conversations",
            summary=f"Scrape unread conversations ({tags[0]})",
            status_code=HTTP_200_OK,
        )
        async def scrape_unread_conversations(self, data: ScrapeRequest) -> dict:
            from api.presentation.app import agent_manager
            await agent_manager.ensure_running()

            if data.folder:
                async with async_session() as db:
                    level = await fc_repo.get_level_for_folder(db, data.folder, app_name)
                folders_to_scrape = [(data.folder, level)]
            else:
                async with async_session() as db:
                    configs = await fc_repo.get_folder_configs(db, application=app_name, active_only=True, analyst_only=False)
                if not configs:
                    return {
                        "status": "error",
                        "message": f"No folder configs found for '{app_name}'. "
                                   "Create them via POST /{app}/folder-config or provide a folder name.",
                    }
                folders_to_scrape = [(c.folder_name, c.level) for c in configs]

            total_new_saved = 0
            total_scraped = 0
            all_scroll_exhausted = True
            folders_scraped = []

            for folder, level in folders_to_scrape:
                async with httpx.AsyncClient(timeout=360.0) as client:
                    response = await client.post(
                        f"{AGENT_URL}/process",
                        json={
                            "application": app_name,
                            "folder": folder,
                            "unread_only": True,
                            "extraction_mode": data.extraction_mode,
                            "level": level,
                        },
                    )
                agent_result = response.json()
                new_saved = agent_result.get("new_saved", 0)
                scraped = agent_result.get("scraped_conversations", 0)
                scroll_exhausted = agent_result.get("scroll_exhausted", False)

                total_new_saved += new_saved
                total_scraped += scraped
                if not scroll_exhausted:
                    all_scroll_exhausted = False

                folders_scraped.append({
                    "folder": folder, "level": level,
                    "new_saved": new_saved, "scraped_conversations": scraped,
                    "scroll_exhausted": scroll_exhausted,
                })

            async with async_session() as db:
                total_in_db = await count_conversations(db, app_name)

            result = ok(
                application=app_name, new_saved=total_new_saved,
                total_in_db=total_in_db, scraped_conversations=total_scraped,
                scroll_exhausted=all_scroll_exhausted,
            )
            if len(folders_scraped) == 1:
                result["folder"] = folders_scraped[0]["folder"]
                result["level"] = folders_scraped[0]["level"]
            else:
                result["folders_scraped"] = folders_scraped

            return result

        @get(
            "/conversations",
            summary=f"Get stored conversations ({tags[0]})",
            status_code=HTTP_200_OK,
        )
        async def get_stored_conversations(
            self,
            folder: str | None = Parameter(query="folder", default=None),
            id: str | None = Parameter(query="id", default=None),
            conversation_id: str | None = Parameter(query="conversation_id", default=None),
            page: int | None = Parameter(query="page", default=None, ge=1),
            per_page: int | None = Parameter(query="per_page", default=None, ge=1),
            include: str | None = Parameter(query="include", default=None),
            filter: str | None = Parameter(query="filter", default=None),
        ) -> dict:
            p, pp = _pagination(page, per_page)
            offset = (p - 1) * pp
            include_set = set(_parse_csv(include) or [])
            filters = _parse_csv(filter)
            conv_ids = _parse_csv(conversation_id)
            id_uuids = [uuid.UUID(i) for i in (_parse_csv(id) or [])] or None

            async with async_session() as db:
                total_unfiltered = await count_conversations(db, app_name, folder)
                total = await count_conversations(
                    db, app_name, folder, filters=filters, conversation_ids=conv_ids, ids=id_uuids,
                ) if (filters or conv_ids or id_uuids) else total_unfiltered
                rows = await get_conversations(
                    db, app_name, folder, limit=pp, offset=offset,
                    filters=filters, conversation_ids=conv_ids, ids=id_uuids,
                )

            email_mapper = partial(map_email, include=include_set)
            result = ok_page("conversations", rows, total, p, pp, email_mapper)
            if filters:
                result["summary"] = {
                    "filters_applied": filters,
                    "total_unfiltered": total_unfiltered,
                    "total_filtered": total,
                    "showing": len(rows),
                }
            return result

        # --- Folder Config (level folders + analyst folders) ---

        @get("/folder-config", summary=f"List folder configs ({tags[0]})", status_code=HTTP_200_OK)
        async def list_folder_configs(
            self,
            active_only: bool = Parameter(query="active_only", default=True),
        ) -> dict:
            async with async_session() as db:
                level_folders = await fc_repo.get_folder_configs(
                    db, application=app_name, active_only=active_only, analyst_only=False,
                )
                analyst_folders = await fc_repo.get_folder_configs(
                    db, application=app_name, active_only=active_only, analyst_only=True,
                )
            return ok(
                application=app_name,
                level_folders=[map_folder_config(r) for r in level_folders],
                analyst_folders=[map_folder_config(r) for r in analyst_folders],
            )

        @post("/folder-config", summary=f"Create folder config ({tags[0]})", status_code=HTTP_201_CREATED)
        async def create_folder_config(self, data: FolderConfigCreate) -> dict:
            especialist_id = None
            if data.especialist_code:
                async with async_session() as db:
                    from api.infrastructure import especialist_repository as esp_repo
                    esp = await esp_repo.get_especialist_by_code(db, data.especialist_code)
                    if not esp:
                        return {"status": "error", "message": f"Especialist '{data.especialist_code}' not found"}
                    especialist_id = esp.id
                    row = await fc_repo.create_folder_config(
                        db, folder_name=data.folder_name, level=data.level,
                        application=app_name, especialist_id=especialist_id,
                    )
                    await db.commit()
            else:
                async with async_session() as db:
                    row = await fc_repo.create_folder_config(
                        db, folder_name=data.folder_name, level=data.level, application=app_name,
                    )
                    await db.commit()
            return ok(folder_config=map_folder_config(row))

        @put("/folder-config/{config_id:str}", summary=f"Update folder config ({tags[0]})", status_code=HTTP_200_OK)
        async def update_folder_config(self, config_id: str, data: FolderConfigUpdate) -> dict:
            fields = data.model_dump(exclude_unset=True)
            async with async_session() as db:
                row = await fc_repo.update_folder_config(db, uuid.UUID(config_id), **fields)
                if not row:
                    raise NotFoundException(detail=f"FolderConfig '{config_id}' not found")
                await db.commit()
            return ok(folder_config=map_folder_config(row))

        @delete("/folder-config/{config_id:str}", summary=f"Delete folder config ({tags[0]})", status_code=HTTP_200_OK)
        async def delete_folder_config(self, config_id: str) -> dict:
            async with async_session() as db:
                deleted = await fc_repo.delete_folder_config(db, uuid.UUID(config_id))
                if not deleted:
                    raise NotFoundException(detail=f"FolderConfig '{config_id}' not found")
                await db.commit()
            return ok(message="Deleted")

        # --- Assign Specialists ---

        @post("/assign-specialists/{level:int}", summary=f"Assign specialists by level ({tags[0]})", status_code=HTTP_200_OK)
        async def assign_specialists(self, level: int) -> dict:
            async with async_session() as db:
                result = await dispatch_level(db, app_name, level)

            # If there are already-assigned conversations to redirect, move them
            # in Outlook via the agent (right-click → Move → target folder)
            redirects = result.get("redirects", [])
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
                        move_resp = await client.post(
                            f"{AGENT_URL}/move",
                            json={"application": app_name, "moves": move_payload},
                        )
                    result["move_result"] = move_resp.json()
                except Exception as exc:
                    logger.warning("Could not call agent /move: %s", exc)
                    result["move_result"] = {"status": "error", "message": str(exc)}

            return result

        # --- Assignments ---

        @get("/assignments", summary=f"List assignments with specialist and conversation details ({tags[0]})", status_code=HTTP_200_OK)
        async def list_assignments(
            self,
            specialist_code: str | None = Parameter(query="specialist_code", default=None),
            level: int | None = Parameter(query="level", default=None),
            day: str | None = Parameter(query="day", default=None, description="YYYY-MM-DD"),
            hour_from: int | None = Parameter(query="hour_from", default=None, ge=0, le=23),
            hour_to: int | None = Parameter(query="hour_to", default=None, ge=0, le=23),
            date_from: str | None = Parameter(query="date_from", default=None),
            date_to: str | None = Parameter(query="date_to", default=None),
            page: int = Parameter(query="page", default=1, ge=1),
            per_page: int = Parameter(query="per_page", default=50, ge=1, le=500),
        ) -> dict:
            from datetime import date as date_type, datetime, timezone
            def _parse_date(v):
                return date_type.fromisoformat(v) if v else None
            def _parse_dt(v):
                if not v:
                    return None
                dt = datetime.fromisoformat(v)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

            offset = (page - 1) * per_page
            async with async_session() as db:
                rows = await assign_repo.get_assignments_rich(
                    db, application_code=app_name, especialist_code=specialist_code,
                    level=level, day=_parse_date(day), hour_from=hour_from, hour_to=hour_to,
                    date_from=_parse_dt(date_from), date_to=_parse_dt(date_to),
                    limit=per_page, offset=offset,
                )
                total = await assign_repo.count_assignments(
                    db, application_code=app_name, especialist_code=specialist_code,
                    level=level, day=_parse_date(day), hour_from=hour_from, hour_to=hour_to,
                    date_from=_parse_dt(date_from), date_to=_parse_dt(date_to),
                )
            from api.domain.mappers import map_assignment_rich
            return ok_page("assignments", rows, total, page, per_page, map_assignment_rich)

        # --- Tickets ---

        @post("/create-tickets", summary=f"Create Ivanti tickets for unassigned cases ({tags[0]})", status_code=HTTP_200_OK)
        async def create_tickets_endpoint(self) -> dict:
            async with async_session() as db:
                return await create_tickets_for_app(db, app_name, MISSAQUEST_URL)

        # --- Watcher ---

        @post("/watcher/start", summary=f"Start background watcher ({tags[0]})", status_code=HTTP_200_OK)
        async def start_watcher(
            self,
            interval_seconds: int = Parameter(query="interval_seconds", default=300, ge=60),
        ) -> dict:
            from api.presentation.app import watcher_manager, agent_manager
            await agent_manager.ensure_running()
            watcher_manager.get(app_name, create_tickets=create_tickets).start(interval_seconds=interval_seconds)
            return watcher_manager.get(app_name).status()

        @post("/watcher/stop", summary=f"Stop background watcher ({tags[0]})", status_code=HTTP_200_OK)
        async def stop_watcher(self) -> dict:
            from api.presentation.app import watcher_manager
            watcher_manager.get(app_name).stop()
            return watcher_manager.get(app_name).status()

        @get("/watcher/status", summary=f"Watcher status ({tags[0]})", status_code=HTTP_200_OK)
        async def watcher_status(self) -> dict:
            from api.presentation.app import watcher_manager
            return watcher_manager.get(app_name).status()

    if not assign_specialists:
        del AppController.assign_specialists

    if not create_tickets:
        del AppController.create_tickets_endpoint

    if not watcher:
        del AppController.start_watcher
        del AppController.stop_watcher
        del AppController.watcher_status

    AppController.path = path
    AppController.tags = tags
    AppController.__name__ = f"{app_name}_controller"
    AppController.__qualname__ = f"{app_name}_controller"

    return AppController
