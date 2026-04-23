"""
domain/ticket_repository.py — CRUD for tickets table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Ticket
from shared.logger import get_logger

logger = get_logger("ticket_repository")


async def create_ticket(
    session: AsyncSession,
    code: str | None,
    type: str | None,
    application: str,
    conversation_id: uuid.UUID | None = None,
    especialist_code: str | None = None,
) -> Ticket:
    row = Ticket(
        id=uuid.uuid4(),
        code=code,
        type=type,
        application=application,
        conversation_id=conversation_id,
        especialist_code=especialist_code,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info("Created ticket code=%s app=%s", code, application)
    return row


async def get_tickets(
    session: AsyncSession,
    application: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Ticket]:
    q = select(Ticket)
    if application:
        q = q.where(Ticket.application == application)
    q = q.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_tickets_by_especialist(
    session: AsyncSession,
    especialist_code: str,
) -> int:
    q = select(func.count(Ticket.id)).where(Ticket.especialist_code == especialist_code)
    result = await session.execute(q)
    return result.scalar() or 0
