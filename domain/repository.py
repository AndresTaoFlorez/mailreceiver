"""
domain/repository.py — Email repository (CRUD over PostgreSQL).

Handles upsert logic: if conversation_id already exists, the row is skipped.
This prevents duplicate conversations when the same folder is scraped multiple times.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Email
from domain.schemas import ScrapedEmail
from shared.logger import get_logger

logger = get_logger("repository")


async def save_conversations(
    session: AsyncSession,
    conversations: list[ScrapedEmail],
    app: str,
    folder: str,
) -> int:
    """Bulk-upsert scraped conversations. Returns number of new rows inserted."""
    if not conversations:
        return 0

    rows = [
        {
            "id": uuid.uuid4(),
            "conversation_id": e.conversation_id,
            "app": app,
            "folder": folder,
            "subject": e.subject,
            "sender": e.sender,
            "sender_email": e.sender_email,
            "year": e.date.year,
            "month": e.date.month,
            "day": e.date.day,
            "hour": e.date.hour,
        }
        for e in conversations
        if e.conversation_id
    ]

    if not rows:
        return 0

    stmt = pg_insert(Email).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_conversation_id")
    result = await session.execute(stmt)
    await session.commit()

    inserted = result.rowcount  # type: ignore[union-attr]
    logger.info("Saved %d/%d conversations (app=%s, folder=%s)", inserted, len(rows), app, folder)
    return inserted


async def get_conversations(
    session: AsyncSession,
    app: str,
    folder: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Email]:
    """Fetch stored conversations filtered by app and optional folder."""
    q = select(Email).where(Email.app == app)
    if folder:
        q = q.where(Email.folder == folder)
    q = q.order_by(Email.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_conversations(session: AsyncSession, app: str, folder: str | None = None) -> int:
    """Count stored conversations for an app/folder."""
    from sqlalchemy import func
    q = select(func.count(Email.id)).where(Email.app == app)
    if folder:
        q = q.where(Email.folder == folder)
    result = await session.execute(q)
    return result.scalar() or 0


async def exists(session: AsyncSession, conversation_id: str) -> bool:
    """Check if a conversation_id already exists."""
    q = select(Email.id).where(Email.conversation_id == conversation_id).limit(1)
    result = await session.execute(q)
    return result.scalar() is not None
