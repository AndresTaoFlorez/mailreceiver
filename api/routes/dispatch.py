from __future__ import annotations

import uuid

from litestar import Controller, get, put
from litestar.status_codes import HTTP_200_OK
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from domain.database import async_session
from domain import assignment_repository as assign_repo
from domain.schemas import AssignmentOut


class DispatchController(Controller):
    path = "/dispatch"
    tags = ["Dispatch"]

    @get(
        "/assignments",
        summary="List assignments",
        description=(
            "Returns paginated assignment records.\n\n"
            "**Query params:**\n"
            "- **application_code** *(optional)*: Filter by application\n"
            "- **especialist_code** *(optional)*: Filter by specialist\n"
            "- **page**: Page number, 1-based (default 1)\n"
            "- **per_page**: Results per page, max 500 (default 50)"
        ),
        status_code=HTTP_200_OK,
    )
    async def list_assignments(
        self,
        application_code: str | None = Parameter(query="application_code", default=None),
        especialist_code: str | None = Parameter(query="especialist_code", default=None),
        page: int = Parameter(query="page", default=1, ge=1),
        per_page: int = Parameter(query="per_page", default=50, ge=1, le=500),
    ) -> dict:
        offset = (page - 1) * per_page
        async with async_session() as db:
            rows = await assign_repo.get_assignments(
                db,
                application_code=application_code,
                especialist_code=especialist_code,
                limit=per_page,
                offset=offset,
            )
            total = await assign_repo.count_assignments(
                db,
                application_code=application_code,
                especialist_code=especialist_code,
            )
        return {
            "status": "ok",
            "page": page,
            "per_page": per_page,
            "total": total,
            "assignments": [AssignmentOut.from_row(r).model_dump() for r in rows],
        }

    @put(
        "/assignments/{assignment_id:str}/ticket",
        summary="Link ticket to assignment",
        description=(
            "Attaches a Judit/TybaCase ticket ID to an existing assignment. "
            "Called after the ticket creation process completes.\n\n"
            "**Path param:**\n"
            "- **assignment_id**: UUID of the assignment\n\n"
            "**Request body:**\n"
            "- **ticket_id**: UUID of the ticket returned by TybaCase"
        ),
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
        return {"status": "ok", "assignment": AssignmentOut.from_row(row).model_dump()}
