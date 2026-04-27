"""
api/routes/app_controller.py — Factory for per-application controllers.

Each application (tutela_en_linea, justicia_xxi_web, cierres_tyba) gets the same
endpoints: scrape, conversations, folder-config. Only the APP_NAME, path, and tags differ.
"""

from __future__ import annotations

import uuid

import httpx
from litestar import Controller, get, post, put, delete
from litestar.params import Parameter
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import NotFoundException
from pydantic import BaseModel, Field

from api.config import AGENT_HOST, AGENT_PORT, load_config
from domain.database import async_session
from domain.repository import get_conversations, count_conversations
from domain import folder_config_repository as fc_repo
from domain import specialist_folder_repository as sf_repo
from domain.dispatcher import dispatch_level
from domain.schemas import (
    PaginatedResponse, FolderConfigCreate, FolderConfigUpdate, FolderConfigOut,
    SpecialistFolderSet, SpecialistFolderUpdate, SpecialistFolderOut,
    DispatchResult, DispatchResultItem,
)

AGENT_URL = f"http://{AGENT_HOST}:{AGENT_PORT}"


class ScrapeRequest(BaseModel):
    folder: str = Field(examples=["Bandeja de entrada"])
    extraction_mode: str = Field(default="latest", examples=["latest"])


def _pagination(page: int | None, per_page: int | None) -> tuple[int, int]:
    cfg = load_config()
    p = page or cfg["default_page"]
    pp = per_page or cfg["default_per_page"]
    pp = min(pp, cfg["max_per_page"])
    return p, pp


def create_app_controller(
    app_name: str,
    path: str,
    tags: list[str],
) -> type[Controller]:
    """Create a Litestar Controller class scoped to a specific application."""

    class AppController(Controller):

        @post(
            "/unread-conversations",
            summary=f"Scrape unread conversations ({tags[0]})",
            description=(
                "Triggers the browser agent to scrape unread emails from an Outlook folder "
                "and saves new conversations to PostgreSQL (duplicates are skipped).\n\n"
                "**Request body:**\n"
                "- **folder**: Exact Outlook folder name to scrape (e.g. `SPECIALIST (S00)`, `Bandeja de entrada`)\n"
                "- **extraction_mode**: Which email(s) to extract from each conversation thread:\n"
                "  - `latest` — Only the newest/most recent reply (default)\n"
                "  - `oldest` — Only the first/original message\n"
                "  - `full` — All messages in the thread, separated by a divider\n"
                "\n"
                "**Response:**\n"
                "- **new_saved**: How many new conversations were inserted (0 if all were duplicates)\n"
                "- **total_in_db**: Total conversations stored for this app + folder\n"
                "- **scraped_conversations**: How many rows the agent found in Outlook\n"
                "- **scroll_exhausted**: Whether the agent reached the end of the email list"
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
                        "application": app_name,
                        "folder": data.folder,
                        "unread_only": True,
                        "extraction_mode": data.extraction_mode,
                    },
                )
            agent_result = response.json()
            new_saved = agent_result.get("new_saved", 0)

            async with async_session() as db:
                total = await count_conversations(db, app_name, data.folder)

            return {
                "status": "ok",
                "application": app_name,
                "folder": data.folder,
                "new_saved": new_saved,
                "total_in_db": total,
                "scraped_conversations": agent_result.get("scraped_conversations", 0),
                "scroll_exhausted": agent_result.get("scroll_exhausted", False),
            }

        @get(
            "/conversations",
            summary=f"Get stored conversations ({tags[0]})",
            description=(
                "Returns previously scraped conversations from the database. No scraping is triggered. "
                "The application is determined by the endpoint path.\n\n"
                "**Query params:**\n"
                "- **folder** *(optional)*: Outlook folder name to narrow results to a specific folder\n"
                "- **id** *(optional)*: Comma-separated internal UUIDs to fetch specific conversations\n"
                "- **conversation_id** *(optional)*: Comma-separated Exchange conversation IDs. Partial match supported — you can send the first portion without URL-encoding special characters like `+` or `=`\n"
                "- **page**: Page number, 1-based (default from config)\n"
                "- **per_page**: Results per page (default from config)\n"
                "- **include**: Comma-separated heavy fields to opt-in: `body`, `date`, `conversation_id`, `created_at`. Excluded by default to keep responses light\n"
                "- **filter**: Comma-separated field presence checks. `tags` = has tags, `!body` = body is empty. Useful for finding conversations missing extraction"
            ),
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
            include_set = {f.strip() for f in include.split(",") if f.strip()} if include else set()
            filters = [f.strip() for f in filter.split(",") if f.strip()] if filter else None
            conv_ids = [c.strip() for c in conversation_id.split(",") if c.strip()] if conversation_id else None
            id_uuids = [uuid.UUID(i.strip()) for i in id.split(",") if i.strip()] if id else None
            async with async_session() as db:
                total_unfiltered = await count_conversations(db, app_name, folder)
                total = await count_conversations(db, app_name, folder, filters=filters, conversation_ids=conv_ids, ids=id_uuids) if (filters or conv_ids or id_uuids) else total_unfiltered
                rows = await get_conversations(db, app_name, folder, limit=pp, offset=offset, filters=filters, conversation_ids=conv_ids, ids=id_uuids)

            return PaginatedResponse.build(
                rows, total, p, pp, include=include_set,
                filters=filters, total_unfiltered=total_unfiltered,
            ).model_dump(exclude_none=True)

        # --- Folder Config ---

        @get(
            "/folder-config",
            summary=f"List folder configs ({tags[0]})",
            description=(
                "Returns all folder-to-level mappings configured for this application.\n\n"
                "**Query params:**\n"
                "- **active_only**: If true (default), only returns active configs. Set false to include disabled ones"
            ),
            status_code=HTTP_200_OK,
        )
        async def list_folder_configs(
            self,
            active_only: bool = Parameter(query="active_only", default=True),
        ) -> dict:
            async with async_session() as db:
                rows = await fc_repo.get_folder_configs(db, application=app_name, active_only=active_only)
            return {
                "status": "ok",
                "total": len(rows),
                "folder_configs": [FolderConfigOut.from_row(r).model_dump() for r in rows],
            }

        @post(
            "/folder-config",
            summary=f"Create folder config ({tags[0]})",
            description=(
                "Maps an Outlook folder to a support level for the dispatcher. "
                "The application is set automatically from the endpoint.\n\n"
                "**Request body:**\n"
                "- **folder_name**: Exact name of the Outlook folder as it appears in the mailbox (e.g. `SPECIALIST (S00)`, `SOPORTE BASICO`)\n"
                "- **level**: Support level number. Determines which specialist pool handles emails from this folder. "
                "If the application only has level 1 configured, all dispatch goes to level 1"
            ),
            status_code=HTTP_201_CREATED,
        )
        async def create_folder_config(self, data: FolderConfigCreate) -> dict:
            async with async_session() as db:
                row = await fc_repo.create_folder_config(
                    db, folder_name=data.folder_name, level=data.level,
                    application=app_name,
                )
            return {"status": "ok", "folder_config": FolderConfigOut.from_row(row).model_dump()}

        @put(
            "/folder-config/{config_id:str}",
            summary=f"Update folder config ({tags[0]})",
            description=(
                "Update any field of an existing folder config. Only send the fields you want to change.\n\n"
                "**Path param:**\n"
                "- **config_id**: UUID of the folder config to update\n\n"
                "**Request body (all optional):**\n"
                "- **folder_name**: New Outlook folder name\n"
                "- **level**: New support level\n"
                "- **active**: Set to false to disable this mapping without deleting it"
            ),
            status_code=HTTP_200_OK,
        )
        async def update_folder_config(self, config_id: str, data: FolderConfigUpdate) -> dict:
            fields = data.model_dump(exclude_unset=True)
            async with async_session() as db:
                row = await fc_repo.update_folder_config(db, uuid.UUID(config_id), **fields)
            if not row:
                raise NotFoundException(detail=f"FolderConfig '{config_id}' not found")
            return {"status": "ok", "folder_config": FolderConfigOut.from_row(row).model_dump()}

        @delete(
            "/folder-config/{config_id:str}",
            summary=f"Delete folder config ({tags[0]})",
            description=(
                "Permanently removes a folder-to-level mapping.\n\n"
                "**Path param:**\n"
                "- **config_id**: UUID of the folder config to delete"
            ),
            status_code=HTTP_200_OK,
        )
        async def delete_folder_config(self, config_id: str) -> dict:
            async with async_session() as db:
                deleted = await fc_repo.delete_folder_config(db, uuid.UUID(config_id))
            if not deleted:
                raise NotFoundException(detail=f"FolderConfig '{config_id}' not found")
            return {"status": "ok", "message": "Deleted"}

        # --- Specialist Folders ---

        @get(
            "/specialists-folder",
            summary=f"List specialist folder mappings ({tags[0]})",
            description=(
                "Returns which Outlook folder each specialist handles in this application.\n\n"
                "**Query params:**\n"
                "- **active_only**: If true (default), only returns active mappings"
            ),
            status_code=HTTP_200_OK,
        )
        async def list_specialist_folders(
            self,
            active_only: bool = Parameter(query="active_only", default=True),
        ) -> dict:
            async with async_session() as db:
                rows = await sf_repo.get_specialist_folders(db, application_code=app_name, active_only=active_only)
            return {
                "status": "ok",
                "total": len(rows),
                "specialist_folders": [SpecialistFolderOut.from_row(r).model_dump() for r in rows],
            }

        @post(
            "/specialists-folder",
            summary=f"Set specialist folder mappings ({tags[0]})",
            description=(
                "Assigns an Outlook folder to one or more specialists in this application. "
                "Accepts a JSON array. If a specialist already has a folder configured, it will be updated.\n\n"
                "**Request body (array of objects):**\n"
                "- **especialist_code**: Code of the specialist (must exist in the specialists table)\n"
                "- **folder_name**: Exact Outlook folder name this specialist handles "
                "(e.g. the personal subfolder assigned to them in the mailbox)"
            ),
            status_code=HTTP_201_CREATED,
        )
        async def set_specialist_folders(self, data: list[SpecialistFolderSet]) -> dict:
            created = []
            async with async_session() as db:
                for item in data:
                    row = await sf_repo.upsert_specialist_folder(
                        db,
                        application_code=app_name,
                        especialist_code=item.especialist_code,
                        folder_name=item.folder_name,
                    )
                    created.append(SpecialistFolderOut.from_row(row).model_dump())
            return {
                "status": "ok",
                "total": len(created),
                "specialist_folders": created,
            }

        @put(
            "/specialists-folder/{record_id:str}",
            summary=f"Update specialist folder mapping ({tags[0]})",
            description=(
                "Update an existing specialist-folder mapping. Only send the fields you want to change.\n\n"
                "**Path param:**\n"
                "- **record_id**: UUID of the mapping to update\n\n"
                "**Request body (all optional):**\n"
                "- **folder_name**: New Outlook folder name\n"
                "- **active**: Set false to disable this mapping"
            ),
            status_code=HTTP_200_OK,
        )
        async def update_specialist_folder(self, record_id: str, data: SpecialistFolderUpdate) -> dict:
            fields = data.model_dump(exclude_unset=True)
            async with async_session() as db:
                row = await sf_repo.update_specialist_folder(db, uuid.UUID(record_id), **fields)
            if not row:
                raise NotFoundException(detail=f"SpecialistFolder '{record_id}' not found")
            return {"status": "ok", "specialist_folder": SpecialistFolderOut.from_row(row).model_dump()}

        @delete(
            "/specialists-folder/{record_id:str}",
            summary=f"Delete specialist folder mapping ({tags[0]})",
            description=(
                "Permanently removes a specialist-folder mapping.\n\n"
                "**Path param:**\n"
                "- **record_id**: UUID of the mapping to delete"
            ),
            status_code=HTTP_200_OK,
        )
        async def delete_specialist_folder(self, record_id: str) -> dict:
            async with async_session() as db:
                deleted = await sf_repo.delete_specialist_folder(db, uuid.UUID(record_id))
            if not deleted:
                raise NotFoundException(detail=f"SpecialistFolder '{record_id}' not found")
            return {"status": "ok", "message": "Deleted"}

        # --- Assign Specialists ---

        @post(
            "/assign-specialists/{level:int}",
            summary=f"Assign specialists by level ({tags[0]})",
            description=(
                "Assigns conversations to specialists for a specific support level.\n\n"
                "The system looks up which Outlook folders are mapped to the given level "
                "in the folder_config table (e.g. `SOPORTE BASICO` → level 1, "
                "`SOPORTE AVANZADO` → level 2), fetches all conversations from those folders, "
                "and distributes unassigned ones among active specialists.\n\n"
                "**Path param:**\n"
                "- **level**: Support level to assign (e.g. `1` for basic, `2` for advanced). "
                "Must match a level configured in folder_config for this application\n\n"
                "**How it works:**\n"
                "1. Reads folder_config to find which folders belong to the requested level\n"
                "2. Fetches all conversations from those folders\n"
                "3. Builds the eligible specialist pool from active work_windows at the current date/time\n"
                "4. Assigns conversations one-by-one (progressive drip): the specialist with the most negative balance gets the next case\n"
                "5. Already-assigned conversations are skipped automatically\n\n"
                "**Response:**\n"
                "- **total_assigned**: Number of conversations assigned in this run\n"
                "- **queued**: Conversations that could not be assigned (no active specialist pool)\n"
                "- **folders_used**: Folder names that were resolved from folder_config for this level\n"
                "- **assignments**: List of each assignment (conversation_id, especialist_code, level, work_window_id)"
            ),
            status_code=HTTP_200_OK,
        )
        async def assign_specialists(self, level: int) -> dict:
            async with async_session() as db:
                result = await dispatch_level(db, app_name, level)

            return result

    AppController.path = path
    AppController.tags = tags
    AppController.__name__ = f"{app_name}_controller"
    AppController.__qualname__ = f"{app_name}_controller"

    return AppController
