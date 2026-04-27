from __future__ import annotations

from litestar import Controller, get, post, put
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from domain.database import async_session
from domain import application_repository as repo
from domain.schemas import ApplicationCreate, ApplicationUpdate, ApplicationOut


class ApplicationController(Controller):
    path = "/applications"
    tags = ["Applications"]

    @get(
        "/",
        summary="List applications",
        description=(
            "Returns all registered applications. Each application represents a distinct Outlook mailbox/workflow.\n\n"
            "**Query params:**\n"
            "- **active_only**: If true (default), excludes inactive applications"
        ),
        status_code=HTTP_200_OK,
    )
    async def list_applications(
        self,
        active_only: bool = Parameter(query="active_only", default=True),
    ) -> dict:
        async with async_session() as db:
            rows = await repo.get_applications(db, active_only=active_only)
        return {
            "status": "ok",
            "total": len(rows),
            "applications": [ApplicationOut.from_row(r).model_dump() for r in rows],
        }

    @get(
        "/{code:str}",
        summary="Get application by code",
        description=(
            "Returns a single application.\n\n"
            "**Path param:**\n"
            "- **code**: Application code (e.g. `tutela_en_linea`)"
        ),
        status_code=HTTP_200_OK,
    )
    async def get_application(self, code: str) -> dict:
        async with async_session() as db:
            row = await repo.get_application(db, code)
        if not row:
            raise NotFoundException(detail=f"Application '{code}' not found")
        return {"status": "ok", "application": ApplicationOut.from_row(row).model_dump()}

    @post(
        "/",
        summary="Create application",
        description=(
            "Register a new application. The code becomes the primary key used across all tables.\n\n"
            "**Request body:**\n"
            "- **code**: Unique identifier, typically snake_case (e.g. `tutela_en_linea`). Must match the app_name used in scraping routes\n"
            "- **name**: Human-readable name for dashboards (e.g. `Tutela en Linea`)\n"
            "- **description** *(optional)*: Notes about what this application handles"
        ),
        status_code=HTTP_201_CREATED,
    )
    async def create_application(self, data: ApplicationCreate) -> dict:
        async with async_session() as db:
            row = await repo.create_application(
                db, code=data.code, name=data.name, description=data.description,
            )
        return {"status": "ok", "application": ApplicationOut.from_row(row).model_dump()}

    @put(
        "/{code:str}",
        summary="Update application",
        description=(
            "Update an application's details. Only send the fields you want to change.\n\n"
            "**Path param:**\n"
            "- **code**: Application code\n\n"
            "**Request body (all optional):**\n"
            "- **name**: New display name\n"
            "- **description**: New description\n"
            "- **active**: Set false to disable the application entirely"
        ),
        status_code=HTTP_200_OK,
    )
    async def update_application(self, code: str, data: ApplicationUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        async with async_session() as db:
            row = await repo.update_application(db, code, **fields)
        if not row:
            raise NotFoundException(detail=f"Application '{code}' not found")
        return {"status": "ok", "application": ApplicationOut.from_row(row).model_dump()}
