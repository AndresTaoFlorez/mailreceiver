"""
domain/folder_config_repository.py — CRUD for folder_config table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import FolderConfig
from shared.logger import get_logger

logger = get_logger("folder_config_repository")


async def get_folder_configs(
    session: AsyncSession,
    application: str | None = None,
    active_only: bool = True,
) -> list[FolderConfig]:
    q = select(FolderConfig)
    if application:
        q = q.where(FolderConfig.application == application)
    if active_only:
        q = q.where(FolderConfig.active.is_(True))
    q = q.order_by(FolderConfig.level, FolderConfig.folder_name)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_level_for_folder(
    session: AsyncSession,
    folder_name: str,
    application: str,
) -> int | None:
    q = (
        select(FolderConfig.level)
        .where(FolderConfig.folder_name == folder_name)
        .where(FolderConfig.application == application)
        .where(FolderConfig.active.is_(True))
    )
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def create_folder_config(
    session: AsyncSession,
    folder_name: str,
    level: int,
    application: str,
) -> FolderConfig:
    row = FolderConfig(
        id=uuid.uuid4(),
        folder_name=folder_name,
        level=level,
        application=application,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info("Created folder_config folder=%s level=%d app=%s", folder_name, level, application)
    return row


async def update_folder_config(
    session: AsyncSession,
    config_id: uuid.UUID,
    **fields,
) -> FolderConfig | None:
    q = select(FolderConfig).where(FolderConfig.id == config_id)
    result = await session.execute(q)
    row = result.scalar_one_or_none()
    if not row:
        return None
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    logger.info("Updated folder_config id=%s", config_id)
    return row


async def delete_folder_config(
    session: AsyncSession,
    config_id: uuid.UUID,
) -> bool:
    q = delete(FolderConfig).where(FolderConfig.id == config_id)
    result = await session.execute(q)
    await session.commit()
    deleted = result.rowcount > 0
    if deleted:
        logger.info("Deleted folder_config id=%s", config_id)
    return deleted
