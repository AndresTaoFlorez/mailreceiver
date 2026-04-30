"""
infrastructure/folder_config_repository.py — CRUD for folder_config table.

Two folder types share this table:
  - Level folders:   especialist_id IS NULL,  level IS NOT NULL
  - Analyst folders: especialist_id IS NOT NULL, level IS NULL
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import FolderConfig, Especialist
from api.shared.logger import get_logger

logger = get_logger("folder_config_repository")


async def get_folder_configs(
    session: AsyncSession,
    application: str | None = None,
    active_only: bool = True,
    analyst_only: bool | None = None,
) -> list[FolderConfig]:
    """
    Return folder configs.

    analyst_only=None  → all rows
    analyst_only=True  → analyst folders only (especialist_id IS NOT NULL)
    analyst_only=False → level folders only   (especialist_id IS NULL)
    """
    q = select(FolderConfig)
    if application:
        q = q.where(FolderConfig.application == application)
    if active_only:
        q = q.where(FolderConfig.active.is_(True))
    if analyst_only is True:
        q = q.where(FolderConfig.especialist_id.isnot(None))
    elif analyst_only is False:
        q = q.where(FolderConfig.especialist_id.is_(None))
    q = q.order_by(FolderConfig.level, FolderConfig.folder_name)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_level_for_folder(
    session: AsyncSession,
    folder_name: str,
    application: str,
) -> int | None:
    """Return the level for a level-type folder (analyst folders are excluded)."""
    q = (
        select(FolderConfig.level)
        .where(FolderConfig.folder_name == folder_name)
        .where(FolderConfig.application == application)
        .where(FolderConfig.active.is_(True))
        .where(FolderConfig.especialist_id.is_(None))
    )
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def get_folders_for_level(
    session: AsyncSession,
    application: str,
    level: int,
) -> list[str]:
    q = (
        select(FolderConfig.folder_name)
        .where(FolderConfig.application == application)
        .where(FolderConfig.level == level)
        .where(FolderConfig.active.is_(True))
        .where(FolderConfig.especialist_id.is_(None))
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_folder_for_specialist(
    session: AsyncSession,
    application_code: str,
    especialist_id: uuid.UUID,
) -> str | None:
    """Return the analyst folder name for a specific specialist."""
    q = (
        select(FolderConfig.folder_name)
        .where(FolderConfig.application_code == application_code)
        .where(FolderConfig.especialist_id == especialist_id)
        .where(FolderConfig.active.is_(True))
    )
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def create_folder_config(
    session: AsyncSession,
    folder_name: str,
    application: str,
    level: int | None = None,
    especialist_id: uuid.UUID | None = None,
) -> FolderConfig:
    row = FolderConfig(
        id=uuid.uuid4(),
        folder_name=folder_name,
        level=level,
        application=application,
        application_code=application,
        especialist_id=especialist_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    folder_type = "analyst" if especialist_id else "level"
    logger.info(
        "Created folder_config [%s] folder=%s level=%s app=%s",
        folder_type, folder_name, level, application,
    )
    return row


async def upsert_analyst_folder(
    session: AsyncSession,
    application_code: str,
    especialist_code: str,
    folder_name: str,
) -> FolderConfig:
    """Create or update the analyst folder for a specialist."""
    esp_id_q = select(Especialist.id).where(Especialist.code == especialist_code)
    result = await session.execute(esp_id_q)
    especialist_id = result.scalar_one_or_none()
    if not especialist_id:
        raise ValueError(f"Especialist '{especialist_code}' not found")

    q = (
        select(FolderConfig)
        .where(FolderConfig.application_code == application_code)
        .where(FolderConfig.especialist_id == especialist_id)
    )
    result = await session.execute(q)
    row = result.scalar_one_or_none()

    if row:
        row.folder_name = folder_name
        row.active = True
    else:
        row = FolderConfig(
            id=uuid.uuid4(),
            folder_name=folder_name,
            level=None,
            application=application_code,
            application_code=application_code,
            especialist_id=especialist_id,
        )
        session.add(row)

    await session.flush()
    await session.refresh(row)
    logger.info(
        "Upserted analyst folder app=%s specialist=%s folder=%s",
        application_code, especialist_code, folder_name,
    )
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
    await session.flush()
    await session.refresh(row)
    logger.info("Updated folder_config id=%s", config_id)
    return row


async def delete_folder_config(
    session: AsyncSession,
    config_id: uuid.UUID,
) -> bool:
    q = delete(FolderConfig).where(FolderConfig.id == config_id)
    result = await session.execute(q)
    await session.flush()
    deleted = result.rowcount > 0
    if deleted:
        logger.info("Deleted folder_config id=%s", config_id)
    return deleted
