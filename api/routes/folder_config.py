from __future__ import annotations

import uuid

from litestar import Controller, get, post, put, delete
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from domain.database import async_session
from domain import folder_config_repository as repo
from domain.schemas import FolderConfigCreate, FolderConfigUpdate, FolderConfigOut


class FolderConfigController(Controller):
    path = "/folder-config"
    tags = ["Configuración de Carpetas"]

    @get(
        "/",
        summary="List folder configurations",
        description="Returns all folder-to-level mappings, optionally filtered by application.",
        status_code=HTTP_200_OK,
    )
    async def list_folder_configs(
        self,
        application: str | None = Parameter(query="application", default=None),
        active_only: bool = Parameter(query="active_only", default=True),
    ) -> dict:
        async with async_session() as db:
            rows = await repo.get_folder_configs(db, application=application, active_only=active_only)
        return {
            "status": "ok",
            "total": len(rows),
            "folder_configs": [FolderConfigOut.from_row(r).model_dump() for r in rows],
        }

    @post(
        "/",
        summary="Create folder config",
        description="Map an Outlook folder name to a support level (1=básico, 2=avanzado).",
        status_code=HTTP_201_CREATED,
    )
    async def create_folder_config(self, data: FolderConfigCreate) -> dict:
        async with async_session() as db:
            row = await repo.create_folder_config(
                db,
                folder_name=data.folder_name,
                level=data.level,
                application=data.application,
            )
        return {
            "status": "ok",
            "folder_config": FolderConfigOut.from_row(row).model_dump(),
        }

    @put(
        "/{config_id:str}",
        summary="Update folder config",
        description="Update folder config fields.",
        status_code=HTTP_200_OK,
    )
    async def update_folder_config(self, config_id: str, data: FolderConfigUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        async with async_session() as db:
            row = await repo.update_folder_config(db, uuid.UUID(config_id), **fields)
        if not row:
            raise NotFoundException(detail=f"FolderConfig with id '{config_id}' not found")
        return {
            "status": "ok",
            "folder_config": FolderConfigOut.from_row(row).model_dump(),
        }

    @delete(
        "/{config_id:str}",
        summary="Delete folder config",
        description="Remove a folder-to-level mapping.",
        status_code=HTTP_200_OK,
    )
    async def delete_folder_config(self, config_id: str) -> dict:
        async with async_session() as db:
            deleted = await repo.delete_folder_config(db, uuid.UUID(config_id))
        if not deleted:
            raise NotFoundException(detail=f"FolderConfig with id '{config_id}' not found")
        return {"status": "ok", "message": "Deleted"}
