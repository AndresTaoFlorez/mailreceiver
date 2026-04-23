from __future__ import annotations

from litestar import Controller, get, post, put
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED, HTTP_404_NOT_FOUND
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from domain.database import async_session
from domain import especialist_repository as repo
from domain.schemas import EspecialistCreate, EspecialistUpdate, EspecialistOut


class EspecialistController(Controller):
    path = "/especialists"
    tags = ["Especialistas"]

    @get(
        "/",
        summary="List specialists",
        description="Returns all specialists, optionally filtered by level.",
        status_code=HTTP_200_OK,
    )
    async def list_especialists(
        self,
        level: int | None = Parameter(query="level", default=None, description="Filter by level (1 or 2)"),
        active_only: bool = Parameter(query="active_only", default=True),
    ) -> dict:
        async with async_session() as db:
            rows = await repo.get_especialists(db, level=level, active_only=active_only)
        return {
            "status": "ok",
            "total": len(rows),
            "especialists": [EspecialistOut.from_row(r).model_dump() for r in rows],
        }

    @post(
        "/",
        summary="Create specialist",
        description="Create a new specialist with code, name, level, and optional load config.",
        status_code=HTTP_201_CREATED,
    )
    async def create_especialist(self, data: EspecialistCreate) -> dict:
        async with async_session() as db:
            row = await repo.create_especialist(
                db,
                code=data.code,
                name=data.name,
                level=data.level,
                load_percentage=data.load_percentage,
                priority=data.priority,
            )
        return {
            "status": "ok",
            "especialist": EspecialistOut.from_row(row).model_dump(),
        }

    @put(
        "/{code:str}",
        summary="Update specialist",
        description="Update specialist fields (name, level, load_percentage, priority, active).",
        status_code=HTTP_200_OK,
    )
    async def update_especialist(self, code: str, data: EspecialistUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        async with async_session() as db:
            row = await repo.update_especialist(db, code, **fields)
        if not row:
            raise NotFoundException(detail=f"Especialist with code '{code}' not found")
        return {
            "status": "ok",
            "especialist": EspecialistOut.from_row(row).model_dump(),
        }
