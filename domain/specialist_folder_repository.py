"""
domain/specialist_folder_repository.py — CRUD for specialist_folders table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import SpecialistFolder
from shared.logger import get_logger

logger = get_logger("specialist_folder_repository")


async def get_specialist_folders(
    session: AsyncSession,
    application_code: str,
    active_only: bool = True,
) -> list[SpecialistFolder]:
    q = select(SpecialistFolder).where(SpecialistFolder.application_code == application_code)
    if active_only:
        q = q.where(SpecialistFolder.active.is_(True))
    q = q.order_by(SpecialistFolder.especialist_code)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_folder_for_specialist(
    session: AsyncSession,
    application_code: str,
    especialist_code: str,
) -> str | None:
    q = (
        select(SpecialistFolder.folder_name)
        .where(SpecialistFolder.application_code == application_code)
        .where(SpecialistFolder.especialist_code == especialist_code)
        .where(SpecialistFolder.active.is_(True))
    )
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def upsert_specialist_folder(
    session: AsyncSession,
    application_code: str,
    especialist_code: str,
    folder_name: str,
) -> SpecialistFolder:
    q = (
        select(SpecialistFolder)
        .where(SpecialistFolder.application_code == application_code)
        .where(SpecialistFolder.especialist_code == especialist_code)
    )
    result = await session.execute(q)
    row = result.scalar_one_or_none()

    if row:
        row.folder_name = folder_name
        row.active = True
    else:
        row = SpecialistFolder(
            id=uuid.uuid4(),
            application_code=application_code,
            especialist_code=especialist_code,
            folder_name=folder_name,
        )
        session.add(row)

    await session.commit()
    await session.refresh(row)
    logger.info(
        "Upserted specialist_folder app=%s specialist=%s folder=%s",
        application_code, especialist_code, folder_name,
    )
    return row


async def update_specialist_folder(
    session: AsyncSession,
    record_id: uuid.UUID,
    **fields,
) -> SpecialistFolder | None:
    q = select(SpecialistFolder).where(SpecialistFolder.id == record_id)
    result = await session.execute(q)
    row = result.scalar_one_or_none()
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    logger.info("Updated specialist_folder id=%s", record_id)
    return row


async def delete_specialist_folder(
    session: AsyncSession,
    record_id: uuid.UUID,
) -> bool:
    q = delete(SpecialistFolder).where(SpecialistFolder.id == record_id)
    result = await session.execute(q)
    await session.commit()
    deleted = result.rowcount > 0
    if deleted:
        logger.info("Deleted specialist_folder id=%s", record_id)
    return deleted
