from __future__ import annotations

from litestar import Controller, post
from litestar.status_codes import HTTP_200_OK

from domain.database import async_session
from domain.assignment import assign_specialists
from domain.repository import get_conversations
from domain.schemas import AssignRequest


class AssignmentController(Controller):
    path = "/assignment"
    tags = ["Asignación"]

    @post(
        "/assign-specialists",
        summary="Assign specialists to unassigned conversations",
        description=(
            "Reads conversations for the given application (and optional folder), "
            "determines level via folder_config, and distributes them among active "
            "specialists based on load_percentage and priority."
        ),
        status_code=HTTP_200_OK,
    )
    async def assign(self, data: AssignRequest) -> dict:
        async with async_session() as db:
            conversations = await get_conversations(
                db,
                app=data.application,
                folder=data.folder,
                limit=10000,
                offset=0,
            )

            result = await assign_specialists(db, conversations, data.application)

        return result.model_dump()
