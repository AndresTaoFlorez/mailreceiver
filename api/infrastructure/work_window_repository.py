"""
infrastructure/work_window_repository.py — CRUD for work_windows + active window queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import WorkWindow
from api.shared.logger import get_logger

logger = get_logger("work_window_repository")


async def get_work_windows(
    session: AsyncSession,
    application_code: str | None = None,
    especialist_code: str | None = None,
    active_only: bool = True,
) -> list[WorkWindow]:
    from api.domain.models import Especialist
    q = select(WorkWindow)
    if application_code:
        q = q.where(WorkWindow.application_code == application_code)
    if especialist_code:
        sub = select(Especialist.id).where(Especialist.code == especialist_code).scalar_subquery()
        q = q.where(WorkWindow.especialist_id == sub)
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
    especialist_id: uuid.UUID,
    application_code: str,
    schedule: dict,
    load_percentage: int | None = None,
) -> WorkWindow:
    row = WorkWindow(
        id=uuid.uuid4(),
        especialist_id=especialist_id,
        application_code=application_code,
        load_percentage=load_percentage,
        schedule=schedule,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    logger.info(
        "Created work_window id=%s especialist_id=%s app=%s",
        row.id, especialist_id, application_code,
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
    await session.flush()
    await session.refresh(row)
    logger.info("Updated work_window id=%s", window_id)
    return row


async def close_work_window(session: AsyncSession, window_id: uuid.UUID) -> bool:
    row = await get_work_window(session, window_id)
    if not row:
        return False
    row.active = False
    await session.flush()
    logger.info("Closed work_window id=%s", window_id)
    return True


def is_window_active_now(window: WorkWindow, now: datetime, timezone: str = "America/Bogota") -> bool:
    """Check if a work window covers the given datetime.

    Schedule strings (date keys and HH:MM times) are interpreted in the given
    timezone (default: America/Bogota). Pass `now` in any tz — it is converted
    before comparison.

    If schedule is empty ({}) the window is treated as always-on.
    """
    if not window.schedule:
        return window.active

    local_now = now.astimezone(ZoneInfo(timezone))
    date_key = local_now.strftime("%Y-%m-%d")
    time_str = local_now.strftime("%H:%M")

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
    timezone: str | None = None,
) -> list[WorkWindow]:
    """Return work windows that are active and cover the given datetime."""
    from api.presentation.config import load_config
    tz = timezone or load_config().get("timezone", "America/Bogota")
    windows = await get_work_windows(session, application_code=application_code, active_only=True)
    return [w for w in windows if is_window_active_now(w, now, tz)]
