"""
infrastructure/especialist_repository.py — CRUD for especialist table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import Especialist
from api.shared.logger import get_logger

logger = get_logger("especialist_repository")


async def get_especialists(
    session: AsyncSession,
    level: int | None = None,
    active_only: bool = True,
) -> list[Especialist]:
    q = select(Especialist)
    if level is not None:
        q = q.where(Especialist.level == level)
    if active_only:
        q = q.where(Especialist.active.is_(True))
    q = q.order_by(Especialist.priority, Especialist.code)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_especialist_by_code(session: AsyncSession, code: str) -> Especialist | None:
    q = select(Especialist).where(Especialist.code == code)
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def create_especialist(
    session: AsyncSession,
    code: str,
    name: str,
    level: int,
    load_percentage: int | None = None,
    priority: int = 0,
) -> Especialist:
    row = Especialist(
        id=uuid.uuid4(),
        code=code,
        name=name,
        level=level,
        load_percentage=load_percentage,
        priority=priority,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info("Created especialist code=%s name=%s level=%d", code, name, level)
    return row


async def update_especialist(
    session: AsyncSession,
    code: str,
    **fields,
) -> Especialist | None:
    row = await get_especialist_by_code(session, code)
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    logger.info("Updated especialist code=%s fields=%s", code, list(fields.keys()))
    return row
