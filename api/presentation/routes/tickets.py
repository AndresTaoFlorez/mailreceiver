from __future__ import annotations

import httpx
from litestar import Controller, post, get
from litestar.status_codes import HTTP_200_OK
from litestar.params import Parameter

from api.presentation.config import MISSAQUEST_URL
from api.infrastructure.database import async_session
from api.infrastructure import ticket_repository as repo
from api.infrastructure import assignment_repository as assign_repo
from api.infrastructure import especialist_repository as esp_repo
from api.infrastructure.email_repository import get_conversations
from api.domain.schemas import CreateTicketsRequest
from api.domain.mappers import ok, ok_page, map_ticket
from api.shared.logger import get_logger

logger = get_logger("tickets_route")

# Maps mailreceiver app codes to missaquest route slugs
_APP_SLUG: dict[str, str] = {
    "justicia_xxi_web": "justicia-web",
    "firma_electronica": "firma-electronica",
    "demanda_en_linea": "demanda-en-linea",
    "tutela_en_linea": "tutela-en-linea",
}


class TicketsController(Controller):
    path = "/tickets"
    tags = ["Tickets"]

    @post(
        "/create",
        summary="Create tickets in Ivanti via missaquest",
        status_code=HTTP_200_OK,
    )
    async def create_tickets(self, data: CreateTicketsRequest) -> dict:
        slug = _APP_SLUG.get(data.application)
        if not slug:
            return {
                "status": "error",
                "message": f"Unknown application '{data.application}'. "
                           f"Valid: {', '.join(_APP_SLUG.keys())}",
            }

        async with async_session() as db:
            assignments = await assign_repo.get_assignments(
                db, application_code=data.application, filters=["!ticket"], limit=500,
            )

            if not assignments:
                return ok(message="No assignments without tickets found", total=0, results=[])

            thread_ids = [a.thread_id for a in assignments]
            conversations = await get_conversations(
                db, app=data.application, ids=thread_ids, limit=len(thread_ids),
            )
            conv_map = {c.id: c for c in conversations}

            specialists = await esp_repo.get_especialists(db, active_only=False)
            spec_map = {s.id: s for s in specialists}

            payload = []
            assignment_order = []
            for assignment in assignments:
                conv = conv_map.get(assignment.thread_id)
                if not conv:
                    logger.warning(
                        "Conversation %s not found for assignment %s, skipping",
                        assignment.thread_id, assignment.id,
                    )
                    continue

                esp = spec_map.get(assignment.especialist_id)
                entry = {
                    "subcategory": data.subcategory,
                    "level": assignment.level,
                    "owner": esp.name if esp else str(assignment.especialist_id),
                    "subject": conv.subject,
                    "sender": conv.sender,
                    "sender_email": conv.sender_email,
                    "body": conv.body or "",
                    "hold_reason": data.hold_reason,
                }
                if data.internal_subcategory:
                    entry["internal_subcategory"] = data.internal_subcategory

                payload.append(entry)
                assignment_order.append(assignment)

            if not payload:
                return ok(message="No valid conversations found for the pending assignments", total=0, results=[])

            logger.info("Sending %d cases to missaquest /applications/%s/", len(payload), slug)
            async with httpx.AsyncClient(timeout=600.0) as client:
                response = await client.post(f"{MISSAQUEST_URL}/applications/{slug}/", json=payload)
            missaquest_results = response.json()

            results = []
            for i, case_result in enumerate(missaquest_results):
                assignment = assignment_order[i] if i < len(assignment_order) else None
                if not assignment:
                    continue

                ticket_number = case_result.get("ticket")
                status = case_result.get("status", "unknown")
                error = case_result.get("error")

                if ticket_number:
                    ticket = await repo.create_ticket(
                        db, code=ticket_number, type=data.application,
                        application=data.application,
                        conversation_id=assignment.thread_id,
                        especialist_code=esp.code if esp else None,
                    )
                    await assign_repo.update_ticket_id(db, assignment.id, ticket.id)

                results.append({
                    "assignment_id": str(assignment.id),
                    "thread_id": str(assignment.thread_id),
                    "especialist_id": str(assignment.especialist_id),
                    "ticket": ticket_number,
                    "status": status,
                    "error": error,
                })

        ok_count = sum(1 for r in results if r["ticket"])
        return ok(
            application=data.application,
            total_sent=len(payload),
            tickets_created=ok_count,
            tickets_failed=len(results) - ok_count,
            results=results,
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
