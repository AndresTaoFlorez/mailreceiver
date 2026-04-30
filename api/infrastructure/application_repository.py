"""
infrastructure/application_repository.py — CRUD for applications table.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import Application
from api.shared.logger import get_logger

logger = get_logger("application_repository")


async def get_applications(
    session: AsyncSession,
    active_only: bool = True,
) -> list[Application]:
    q = select(Application)
    if active_only:
        q = q.where(Application.active.is_(True))
    q = q.order_by(Application.code)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_application(session: AsyncSession, code: str) -> Application | None:
    q = select(Application).where(Application.code == code)
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def create_application(
    session: AsyncSession,
    code: str,
    name: str,
    description: str | None = None,
) -> Application:
    row = Application(code=code, name=name, description=description)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info("Created application code=%s name=%s", code, name)
    return row


async def update_application(
    session: AsyncSession,
    code: str,
    **fields,
) -> Application | None:
    row = await get_application(session, code)
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    logger.info("Updated application code=%s", code)
    return row
