from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from litestar import Controller, get, put
from litestar.status_codes import HTTP_200_OK
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from api.infrastructure.database import async_session
from api.infrastructure import assignment_repository as assign_repo
from api.domain.mappers import ok, ok_page, map_assignment, map_assignment_rich


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class DispatchController(Controller):
    path = "/dispatch"
    tags = ["Dispatch"]

    @get(
        "/assignments",
        summary="List assignments with specialist and conversation details",
        status_code=HTTP_200_OK,
    )
    async def list_assignments(
        self,
        application_code: str | None = Parameter(query="application_code", default=None),
        specialist_code: str | None = Parameter(query="specialist_code", default=None),
        level: int | None = Parameter(query="level", default=None),
        # Date/time filters
        date_from: str | None = Parameter(
            query="date_from", default=None,
            description="Filter assignments from this datetime (ISO 8601, e.g. 2026-05-01T08:00:00)",
        ),
        date_to: str | None = Parameter(
            query="date_to", default=None,
            description="Filter assignments up to this datetime (ISO 8601)",
        ),
        day: str | None = Parameter(
            query="day", default=None,
            description="Filter by exact date (YYYY-MM-DD, e.g. 2026-05-01)",
        ),
        hour_from: int | None = Parameter(query="hour_from", default=None, ge=0, le=23),
        hour_to: int | None = Parameter(query="hour_to", default=None, ge=0, le=23),
        # Pagination
        page: int = Parameter(query="page", default=1, ge=1),
        per_page: int = Parameter(query="per_page", default=50, ge=1, le=500),
    ) -> dict:
        offset = (page - 1) * per_page
        parsed_day = _parse_date(day)
        parsed_from = _parse_datetime(date_from)
        parsed_to = _parse_datetime(date_to)

        async with async_session() as db:
            rows = await assign_repo.get_assignments_rich(
                db,
                application_code=application_code,
                especialist_code=specialist_code,
                level=level,
                date_from=parsed_from,
                date_to=parsed_to,
                day=parsed_day,
                hour_from=hour_from,
                hour_to=hour_to,
                limit=per_page,
                offset=offset,
            )
            total = await assign_repo.count_assignments(
                db,
                application_code=application_code,
                especialist_code=specialist_code,
                level=level,
                date_from=parsed_from,
                date_to=parsed_to,
                day=parsed_day,
                hour_from=hour_from,
                hour_to=hour_to,
            )

        return ok_page("assignments", rows, total, page, per_page, map_assignment_rich)

    @put(
        "/assignments/{assignment_id:str}/ticket",
        summary="Link ticket to assignment",
        status_code=HTTP_200_OK,
    )
    async def link_ticket(self, assignment_id: str, data: dict) -> dict:
        ticket_id = data.get("ticket_id")
        if not ticket_id:
            return {"status": "error", "message": "ticket_id is required"}
        async with async_session() as db:
            row = await assign_repo.update_ticket_id(
                db, uuid.UUID(assignment_id), uuid.UUID(ticket_id),
            )
        if not row:
            raise NotFoundException(detail=f"Assignment '{assignment_id}' not found")
        return ok(assignment=map_assignment(row))
