from __future__ import annotations

from litestar import Controller, post, get
from litestar.status_codes import HTTP_200_OK
from litestar.params import Parameter

from api.presentation.config import MISSAQUEST_URL
from api.infrastructure.database import async_session
from api.infrastructure import ticket_repository as repo
from api.application.ticket_service import create_tickets_for_app
from api.domain.schemas import CreateTicketsRequest
from api.domain.mappers import ok, ok_page, map_ticket
from api.shared.logger import get_logger

logger = get_logger("tickets_route")


class TicketsController(Controller):
    path = "/tickets"
    tags = ["Tickets"]

    @post(
        "/create",
        summary="Create tickets in Ivanti via missaquest",
        status_code=HTTP_200_OK,
    )
    async def create_tickets(self, data: CreateTicketsRequest) -> dict:
        async with async_session() as db:
            return await create_tickets_for_app(
                db,
                application_code=data.application,
                missaquest_url=MISSAQUEST_URL,
                default_subcategory=data.subcategory,
                default_internal_subcategory=data.internal_subcategory,
                hold_reason=data.hold_reason,
            )

    @get(
        "/",
        summary="List tickets",
        status_code=HTTP_200_OK,
    )
    async def list_tickets(
        self,
        application: str | None = Parameter(query="application", default=None),
        page: int = Parameter(query="page", default=1, ge=1),
        per_page: int = Parameter(query="per_page", default=20, ge=1, le=100),
    ) -> dict:
        offset = (page - 1) * per_page
        async with async_session() as db:
            rows = await repo.get_tickets(db, application=application, limit=per_page, offset=offset)
        return ok_page("tickets", rows, len(rows), page, per_page, map_ticket)
