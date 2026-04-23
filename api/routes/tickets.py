from __future__ import annotations

import os

import httpx
from litestar import Controller, post, get
from litestar.status_codes import HTTP_200_OK
from litestar.params import Parameter

from domain.database import async_session
from domain import ticket_repository as repo
from domain.schemas import CreateTicketsRequest, TicketOut
from shared.logger import get_logger

logger = get_logger("tickets_route")

TYBACASE_URL = os.getenv("TYBACASE_URL", "http://localhost:8000")


class TicketsController(Controller):
    path = "/tickets"
    tags = ["Tickets"]

    @post(
        "/create",
        summary="Create tickets in Judit via TybaCase",
        description=(
            "Sends conversation records to TybaCase RPA to create cases in Judit. "
            "Returns each record with its assigned ticket number."
        ),
        status_code=HTTP_200_OK,
    )
    async def create_tickets(self, data: CreateTicketsRequest) -> dict:
        results = []

        async with async_session() as db:
            for conv_id in data.conversation_ids:
                try:
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        response = await client.post(
                            f"{TYBACASE_URL}/cases",
                            json={
                                "raw_data": {
                                    "conversation_id": str(conv_id),
                                    "application": data.application,
                                },
                            },
                        )
                    case_result = response.json()
                    ticket_code = case_result.get("data", {}).get("ticket_code")

                    ticket = await repo.create_ticket(
                        db,
                        code=ticket_code,
                        type=data.application,
                        application=data.application,
                        conversation_id=conv_id,
                    )
                    results.append({
                        "conversation_id": str(conv_id),
                        "ticket_code": ticket_code,
                        "status": "ok",
                    })
                except Exception as e:
                    logger.error("Failed to create ticket for conversation %s: %s", conv_id, e)
                    results.append({
                        "conversation_id": str(conv_id),
                        "ticket_code": None,
                        "status": "error",
                        "detail": str(e),
                    })

        return {
            "status": "ok",
            "total": len(results),
            "results": results,
        }

    @get(
        "/",
        summary="List tickets",
        description="Returns tickets, optionally filtered by application.",
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
        return {
            "status": "ok",
            "page": page,
            "per_page": per_page,
            "tickets": [TicketOut.from_row(r).model_dump() for r in rows],
        }
