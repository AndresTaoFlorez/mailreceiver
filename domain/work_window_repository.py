"""
domain/work_window_repository.py — CRUD for work_windows + active window queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import WorkWindow
from shared.logger import get_logger

logger = get_logger("work_window_repository")


async def get_work_windows(
    session: AsyncSession,
    application_code: str | None = None,
    especialist_code: str | None = None,
    active_only: bool = True,
) -> list[WorkWindow]:
    q = select(WorkWindow)
    if application_code:
        q = q.where(WorkWindow.application_code == application_code)
    if especialist_code:
        q = q.where(WorkWindow.especialist_code == especialist_code)
    if active_only:
        q = q.where(WorkWindow.active.is_(True))
    q = q.order_by(WorkWindow.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_work_window(session: AsyncSession, window_id: uuid.UUID) -> WorkWindow | None:
    q = select(WorkWindow).where(WorkWindow.id == window_id)
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def create_work_window(
    session: AsyncSession,
    especialist_code: str,
    application_code: str,
    schedule: dict,
    load_percentage: int | None = None,
) -> WorkWindow:
    row = WorkWindow(
        id=uuid.uuid4(),
        especialist_code=especialist_code,
        application_code=application_code,
        load_percentage=load_percentage,
        schedule=schedule,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info(
        "Created work_window id=%s especialist=%s app=%s",
        row.id, especialist_code, application_code,
    )
    return row


async def update_work_window(
    session: AsyncSession,
    window_id: uuid.UUID,
    **fields,
) -> WorkWindow | None:
    row = await get_work_window(session, window_id)
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    logger.info("Updated work_window id=%s", window_id)
    return row


async def close_work_window(session: AsyncSession, window_id: uuid.UUID) -> bool:
    row = await get_work_window(session, window_id)
    if not row:
        return False
    row.active = False
    await session.commit()
    logger.info("Closed work_window id=%s", window_id)
    return True


def is_window_active_now(window: WorkWindow, now: datetime) -> bool:
    """Check if a work window covers the given datetime based on its JSONB schedule."""
    date_key = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    day_slots = window.schedule.get(date_key)
    if not day_slots:
        return False

    for slot in day_slots:
        if slot.get("start", "") <= time_str < slot.get("end", ""):
            return True

    return False


async def get_active_windows_now(
    session: AsyncSession,
    application_code: str,
    now: datetime,
) -> list[WorkWindow]:
    """Return work windows that are active and cover the given datetime."""
    windows = await get_work_windows(session, application_code=application_code, active_only=True)
    return [w for w in windows if is_window_active_now(w, now)]
