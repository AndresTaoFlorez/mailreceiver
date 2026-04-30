"""
infrastructure/assignment_repository.py — CRUD for assignments table.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import Assignment, Email, Especialist
from api.infrastructure.email_repository import apply_field_filters
from api.shared.logger import get_logger

logger = get_logger("assignment_repository")


_ASSIGNMENT_FILTER_FIELDS: dict[str, any] = {
    "ticket": Assignment.ticket_id,
}


async def create_assignment(
    session: AsyncSession,
    thread_id: uuid.UUID,
    especialist_id: uuid.UUID,
    application_code: str,
    level: int,
    work_window_id: uuid.UUID | None = None,
) -> Assignment:
    row = Assignment(
        id=uuid.uuid4(),
        thread_id=thread_id,
        especialist_id=especialist_id,
        application_code=application_code,
        level=level,
        work_window_id=work_window_id,
    )
    session.add(row)
    await session.flush()
    return row


def _apply_filters(q, filters: list[str] | None):
    if filters:
        q = apply_field_filters(q, filters, _ASSIGNMENT_FILTER_FIELDS)
    return q


def _filter_by_especialist(q, especialist_code: str):
    sub = select(Especialist.id).where(Especialist.code == especialist_code).scalar_subquery()
    return q.where(Assignment.especialist_id == sub)


def _apply_date_filters(
    q,
    date_from: datetime | None,
    date_to: datetime | None,
    day: date | None,
    hour_from: int | None,
    hour_to: int | None,
):
    """Apply date/time range filters to Assignment.assigned_at."""
    if date_from:
        q = q.where(Assignment.assigned_at >= date_from)
    if date_to:
        q = q.where(Assignment.assigned_at <= date_to)
    if day:
        q = q.where(cast(Assignment.assigned_at, Date) == day)
    if hour_from is not None:
        q = q.where(func.extract("hour", func.timezone("UTC", Assignment.assigned_at)) >= hour_from)
    if hour_to is not None:
        q = q.where(func.extract("hour", func.timezone("UTC", Assignment.assigned_at)) <= hour_to)
    return q


def _build_base_query(
    application_code: str | None,
    especialist_code: str | None,
    level: int | None,
    filters: list[str] | None,
    date_from: datetime | None,
    date_to: datetime | None,
    day: date | None,
    hour_from: int | None,
    hour_to: int | None,
):
    q = select(Assignment)
    if application_code:
        q = q.where(Assignment.application_code == application_code)
    if especialist_code:
        q = _filter_by_especialist(q, especialist_code)
    if level is not None:
        q = q.where(Assignment.level == level)
    q = _apply_filters(q, filters)
    q = _apply_date_filters(q, date_from, date_to, day, hour_from, hour_to)
    return q


async def get_assignments(
    session: AsyncSession,
    application_code: str | None = None,
    especialist_code: str | None = None,
    level: int | None = None,
    filters: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    day: date | None = None,
    hour_from: int | None = None,
    hour_to: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Assignment]:
    q = _build_base_query(
        application_code, especialist_code, level, filters,
        date_from, date_to, day, hour_from, hour_to,
    )
    q = q.order_by(Assignment.assigned_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_assignments(
    session: AsyncSession,
    application_code: str | None = None,
    especialist_code: str | None = None,
    level: int | None = None,
    filters: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    day: date | None = None,
    hour_from: int | None = None,
    hour_to: int | None = None,
) -> int:
    q = _build_base_query(
        application_code, especialist_code, level, filters,
        date_from, date_to, day, hour_from, hour_to,
    )
    count_q = select(func.count()).select_from(q.subquery())
    result = await session.execute(count_q)
    return result.scalar() or 0


async def get_assignments_rich(
    session: AsyncSession,
    application_code: str | None = None,
    especialist_code: str | None = None,
    level: int | None = None,
    filters: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    day: date | None = None,
    hour_from: int | None = None,
    hour_to: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[Assignment, Email, Especialist]]:
    """Return assignments joined with conversation and specialist data."""
    q = (
        select(Assignment, Email, Especialist)
        .join(Email, Email.id == Assignment.thread_id)
        .join(Especialist, Especialist.id == Assignment.especialist_id)
    )
    if application_code:
        q = q.where(Assignment.application_code == application_code)
    if especialist_code:
        q = q.where(Especialist.code == especialist_code)
    if level is not None:
        q = q.where(Assignment.level == level)
    q = _apply_filters(q, filters)
    q = _apply_date_filters(q, date_from, date_to, day, hour_from, hour_to)
    q = q.order_by(Assignment.assigned_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.tuples().all())


async def is_conversation_assigned(
    session: AsyncSession,
    thread_id: uuid.UUID,
) -> bool:
    q = (
        select(Assignment.id)
        .where(Assignment.thread_id == thread_id)
        .limit(1)
    )
    result = await session.execute(q)
    return result.scalar() is not None


async def get_assignment_for_conversation(
    session: AsyncSession,
    thread_id: uuid.UUID,
) -> Assignment | None:
    """Return the most recent assignment for a conversation, or None."""
    q = (
        select(Assignment)
        .where(Assignment.thread_id == thread_id)
        .order_by(Assignment.assigned_at.desc())
        .limit(1)
    )
    result = await session.execute(q)
    return result.scalar_one_or_none()


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
    await session.flush()
    await session.refresh(row)
    logger.info("Updated assignment id=%s ticket_id=%s", assignment_id, ticket_id)
    return row
