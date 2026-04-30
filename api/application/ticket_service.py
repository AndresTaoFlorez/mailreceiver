"""
application/ticket_service.py — Creates tickets in Ivanti via missaquest
for assignments that have no ticket yet.

Level mapping (missaquest subcategory auto-detection):
  level 1 → subcategory passed in (default: "Asesoria / Consulta En General")
  level 2 → subcategory = "Soporte Avanzado" (always, missaquest requires it)
"""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from api.infrastructure import assignment_repository as assign_repo
from api.infrastructure import ticket_repository as ticket_repo
from api.infrastructure import especialist_repository as esp_repo
from api.infrastructure.email_repository import get_conversations
from api.shared.logger import get_logger

logger = get_logger("ticket_service")

_APP_SLUG: dict[str, str] = {
    "justicia_xxi_web": "justicia-web",
    "firma_electronica": "firma-electronica",
    "demanda_en_linea": "demanda-en-linea",
    "tutela_en_linea": "tutela-en-linea",
}


async def create_tickets_for_app(
    session: AsyncSession,
    application_code: str,
    missaquest_url: str,
    default_subcategory: str = "Asesoria / Consulta En General",
    default_internal_subcategory: str | None = "Asesoria / Consulta En General",
    hold_reason: str | None = "Fuerza mayor",
) -> dict:
    """
    Find every assignment without a ticket for the given app, send them to
    missaquest, persist the returned ticket numbers, and link them back to
    the assignment rows.

    Returns a summary dict compatible with the ok() envelope.
    """
    slug = _APP_SLUG.get(application_code)
    if not slug:
        return {
            "status": "error",
            "message": f"No missaquest slug configured for '{application_code}'",
        }

    assignments = await assign_repo.get_assignments(
        session, application_code=application_code, filters=["!ticket"], limit=500,
    )
    if not assignments:
        logger.info("No unticket'd assignments for app=%s", application_code)
        return {"status": "ok", "tickets_created": 0, "tickets_failed": 0, "results": []}

    thread_ids = [a.thread_id for a in assignments]
    conversations = await get_conversations(
        session, app=application_code, ids=thread_ids, limit=len(thread_ids),
    )
    conv_map = {c.id: c for c in conversations}

    specialists = await esp_repo.get_especialists(session, active_only=False)
    spec_map = {s.id: s for s in specialists}

    payload: list[dict] = []
    assignment_order = []

    for assignment in assignments:
        conv = conv_map.get(assignment.thread_id)
        if not conv:
            logger.warning(
                "Conversation not found for assignment %s — skipping", assignment.id,
            )
            continue

        esp = spec_map.get(assignment.especialist_id)

        if assignment.level == 2:
            subcategory = "Soporte Avanzado"
            internal_sub = default_internal_subcategory
        else:
            subcategory = default_subcategory
            internal_sub = None

        entry: dict = {
            "subcategory": subcategory,
            "level": assignment.level,
            "owner": esp.name if esp else "",
            "subject": conv.subject,
            "sender": conv.sender,
            "sender_email": conv.sender_email,
            "body": conv.body or "",
            "hold_reason": hold_reason,
        }
        if internal_sub:
            entry["internal_subcategory"] = internal_sub

        payload.append(entry)
        assignment_order.append(assignment)

    if not payload:
        return {"status": "ok", "tickets_created": 0, "tickets_failed": 0, "results": []}

    logger.info(
        "Sending %d cases to missaquest /applications/%s/", len(payload), slug,
    )
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{missaquest_url}/applications/{slug}/", json=payload,
        )
    missaquest_results = response.json()

    results: list[dict] = []
    for i, case_result in enumerate(missaquest_results):
        if i >= len(assignment_order):
            break
        assignment = assignment_order[i]
        esp = spec_map.get(assignment.especialist_id)

        ticket_number = case_result.get("ticket")
        status = case_result.get("status", "unknown")
        error = case_result.get("error")

        if ticket_number:
            ticket = await ticket_repo.create_ticket(
                session,
                code=ticket_number,
                type=application_code,
                application=application_code,
                conversation_id=assignment.thread_id,
                especialist_code=esp.code if esp else None,
            )
            await assign_repo.update_ticket_id(session, assignment.id, ticket.id)

        results.append({
            "assignment_id": str(assignment.id),
            "thread_id": str(assignment.thread_id),
            "especialist": esp.code if esp else str(assignment.especialist_id),
            "level": assignment.level,
            "ticket": ticket_number,
            "status": status,
            "error": error,
        })

    await session.commit()

    ok_count = sum(1 for r in results if r["ticket"])
    logger.info(
        "Tickets for app=%s: created=%d failed=%d",
        application_code, ok_count, len(results) - ok_count,
    )
    return {
        "status": "ok",
        "application": application_code,
        "total_sent": len(payload),
        "tickets_created": ok_count,
        "tickets_failed": len(results) - ok_count,
        "results": results,
    }
