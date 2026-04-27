from __future__ import annotations

from litestar import Controller, get, post, put
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Parameter

from domain.database import async_session
from domain import especialist_repository as repo
from domain.schemas import EspecialistCreate, EspecialistUpdate, EspecialistOut


class EspecialistController(Controller):
    path = "/especialists"
    tags = ["Specialists"]

    @get(
        "/",
        summary="List specialists",
        description=(
            "Returns all registered specialists.\n\n"
            "**Query params:**\n"
            "- **level** *(optional)*: Filter by support level (e.g. `1` or `2`)\n"
            "- **active_only**: If true (default), excludes inactive specialists"
        ),
        status_code=HTTP_200_OK,
    )
    async def list_especialists(
        self,
        level: int | None = Parameter(query="level", default=None),
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
        summary="Create specialists",
        description=(
            "Register one or more specialists in the system. Accepts a JSON array.\n\n"
            "**Request body (array of objects):**\n"
            "- **code**: Unique short identifier (e.g. `spec01`). Used as FK in assignments, tickets, and work_windows\n"
            "- **name**: Full display name (e.g. `Especialista 01`)\n"
            "- **level**: Support level this specialist handles. Must match the level values in folder_config\n"
            "- **load_percentage** *(optional)*: Fixed percentage of cases (1-100). "
            "If null, the system auto-distributes the remaining percentage equally among all null specialists\n"
            "- **priority**: Tiebreaker when two specialists have the same balance. Lower number = higher priority (default 0)"
        ),
        status_code=HTTP_201_CREATED,
    )
    async def create_especialist(self, data: list[EspecialistCreate]) -> dict:
        # Check for duplicates within the request
        codes = [item.code for item in data]
        dupes_in_request = [c for c in codes if codes.count(c) > 1]
        if dupes_in_request:
            raise ClientException(
                detail=f"Duplicate codes in request: {', '.join(set(dupes_in_request))}",
                status_code=400,
            )

        # Check for duplicates against existing specialists in DB
        async with async_session() as db:
            existing = await repo.get_especialists(db, active_only=False)
            existing_codes = {r.code for r in existing}
            already_exist = [c for c in codes if c in existing_codes]
            if already_exist:
                raise ClientException(
                    detail=f"Codes already exist: {', '.join(already_exist)}",
                    status_code=409,
                )

            created = []
            for item in data:
                row = await repo.create_especialist(
                    db,
                    code=item.code,
                    name=item.name,
                    level=item.level,
                    load_percentage=item.load_percentage,
                    priority=item.priority,
                )
                created.append(EspecialistOut.from_row(row).model_dump())
        return {
            "status": "ok",
            "total": len(created),
            "especialists": created,
        }

    @put(
        "/{code:str}",
        summary="Update specialist",
        description=(
            "Update any field of an existing specialist. Only send the fields you want to change.\n\n"
            "**Path param:**\n"
            "- **code**: Specialist code (e.g. `spec01`)\n\n"
            "**Request body (all optional):**\n"
            "- **name**: New display name\n"
            "- **level**: New support level\n"
            "- **load_percentage**: New fixed load % (null = auto-distribute)\n"
            "- **priority**: New priority (lower = higher)\n"
            "- **active**: Set false to exclude from future assignments"
        ),
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
