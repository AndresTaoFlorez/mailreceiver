from __future__ import annotations

import uuid

from litestar import Controller, get, post, put
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from api.infrastructure.database import async_session
from api.infrastructure import application_repository as repo
from api.domain.schemas import ApplicationCreate, ApplicationUpdate
from api.domain.mappers import ok, ok_list, map_application


class ApplicationController(Controller):
    path = "/applications"
    tags = ["Applications"]

    @get(
        "/",
        summary="List applications",
        description="Returns all registered applications.\n\n- **active_only**: If true (default), excludes inactive applications",
        status_code=HTTP_200_OK,
    )
    async def list_applications(
        self,
        active_only: bool = Parameter(query="active_only", default=True),
    ) -> dict:
        async with async_session() as db:
            rows = await repo.get_applications(db, active_only=active_only)
        return ok_list("applications", rows, map_application)

    @get(
        "/{code:str}",
        summary="Get application by code",
        status_code=HTTP_200_OK,
    )
    async def get_application(self, code: str) -> dict:
        async with async_session() as db:
            row = await repo.get_application(db, code)
        if not row:
            raise NotFoundException(detail=f"Application '{code}' not found")
        return ok(application=map_application(row))

    @post(
        "/",
        summary="Create application",
        status_code=HTTP_201_CREATED,
    )
    async def create_application(self, data: ApplicationCreate) -> dict:
        async with async_session() as db:
            row = await repo.create_application(db, code=data.code, name=data.name, description=data.description)
        return ok(application=map_application(row))

    @put(
        "/{code:str}",
        summary="Update application",
        status_code=HTTP_200_OK,
    )
    async def update_application(self, code: str, data: ApplicationUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        async with async_session() as db:
            row = await repo.update_application(db, code, **fields)
        if not row:
            raise NotFoundException(detail=f"Application '{code}' not found")
        return ok(application=map_application(row))
