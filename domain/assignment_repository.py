"""
domain/assignment_repository.py — CRUD for assignments table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Assignment
from shared.logger import get_logger

logger = get_logger("assignment_repository")


async def create_assignment(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    especialist_code: str,
    application_code: str,
    level: int,
    work_window_id: uuid.UUID | None = None,
) -> Assignment:
    row = Assignment(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        especialist_code=especialist_code,
        application_code=application_code,
        level=level,
        work_window_id=work_window_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get_assignments(
    session: AsyncSession,
    application_code: str | None = None,
    especialist_code: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Assignment]:
    q = select(Assignment)
    if application_code:
        q = q.where(Assignment.application_code == application_code)
    if especialist_code:
        q = q.where(Assignment.especialist_code == especialist_code)
    q = q.order_by(Assignment.assigned_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_assignments(
    session: AsyncSession,
    application_code: str | None = None,
    especialist_code: str | None = None,
) -> int:
    q = select(func.count(Assignment.id))
    if application_code:
        q = q.where(Assignment.application_code == application_code)
    if especialist_code:
        q = q.where(Assignment.especialist_code == especialist_code)
    result = await session.execute(q)
    return result.scalar() or 0


async def is_conversation_assigned(
    session: AsyncSession,
    conversation_id: uuid.UUID,
) -> bool:
    q = (
        select(Assignment.id)
        .where(Assignment.conversation_id == conversation_id)
        .limit(1)
    )
    result = await session.execute(q)
    return result.scalar() is not None


async def update_ticket_id(
    session: AsyncSession,
    assignment_id: uuid.UUID,
    ticket_id: uuid.UUID,
) -> Assignment | None:
    q = select(Assignment).where(Assignment.id == assignment_id)
    result = await session.execute(q)
    row = result.scalar_one_or_none()
    if not row:
        return None
    row.ticket_id = ticket_id
    await session.commit()
    await session.refresh(row)
    logger.info("Updated assignment id=%s ticket_id=%s", assignment_id, ticket_id)
    return row
