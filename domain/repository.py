"""
domain/repository.py — Email repository (CRUD over PostgreSQL).

Handles upsert logic: if conversation_id already exists, the row is skipped.
This prevents duplicate conversations when the same folder is scraped multiple times.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Email, Application
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
            "application_code": app,
            "folder": folder,
            "subject": e.subject,
            "sender": e.sender,
            "sender_email": e.sender_email,
            "tags": getattr(e, "tags", ""),
            "to_address": getattr(e, "to_address", ""),
            "body": getattr(e, "body", ""),
            "from_address": getattr(e, "from_address", ""),
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

    # Ensure the application exists (auto-create if first scrape for this app)
    app_stmt = pg_insert(Application).values(code=app, name=app)
    app_stmt = app_stmt.on_conflict_do_nothing(index_elements=["code"])
    await session.execute(app_stmt)

    stmt = pg_insert(Email).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_conversation_id",
        set_={
            "subject": stmt.excluded.subject,
            "sender": stmt.excluded.sender,
            "sender_email": stmt.excluded.sender_email,
            "body": stmt.excluded.body,
            "tags": stmt.excluded.tags,
            "to_address": stmt.excluded.to_address,
            "from_address": stmt.excluded.from_address,
        },
    )
    result = await session.execute(stmt)
    await session.commit()

    upserted = result.rowcount  # type: ignore[union-attr]
    logger.info("Upserted %d/%d conversations (app=%s, folder=%s)", upserted, len(rows), app, folder)
    return upserted


# String columns on Email that can be used with the filter parameter
_FILTERABLE_FIELDS: dict[str, any] = {
    "body": Email.body,
    "tags": Email.tags,
    "subject": Email.subject,
    "sender": Email.sender,
    "sender_email": Email.sender_email,
    "to_address": Email.to_address,
    "from_address": Email.from_address,
    "conversation_id": Email.conversation_id,
}


def _apply_field_filters(q, filters: list[str]):
    """Apply field presence/absence filters to a query.

    Each filter is a field name (has value) or !field (empty/null).
    Example: ["tags", "!body"] → has tags AND body is empty.
    """
    for f in filters:
        negate = f.startswith("!")
        field_name = f.lstrip("!")
        col = _FILTERABLE_FIELDS.get(field_name)
        if col is None:
            continue
        if negate:
            q = q.where((col == "") | (col.is_(None)))
        else:
            q = q.where(col != "").where(col.is_not(None))
    return q


async def get_conversations(
    session: AsyncSession,
    app: str,
    folder: str | None = None,
    limit: int = 100,
    offset: int = 0,
    filters: list[str] | None = None,
    conversation_ids: list[str] | None = None,
    ids: list[uuid.UUID] | None = None,
) -> list[Email]:
    """Fetch stored conversations filtered by app and optional folder."""
    q = select(Email).where(Email.app == app)
    if folder:
        q = q.where(Email.folder == folder)
    if ids:
        q = q.where(Email.id.in_(ids))
    if conversation_ids:
        q = q.where(or_(*(Email.conversation_id.like(f"{cid}%") for cid in conversation_ids)))
    if filters:
        q = _apply_field_filters(q, filters)
    q = q.order_by(Email.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_conversations(
    session: AsyncSession,
    app: str,
    folder: str | None = None,
    filters: list[str] | None = None,
    conversation_ids: list[str] | None = None,
    ids: list[uuid.UUID] | None = None,
) -> int:
    """Count stored conversations for an app/folder."""
    from sqlalchemy import func
    q = select(func.count(Email.id)).where(Email.app == app)
    if folder:
        q = q.where(Email.folder == folder)
    if ids:
        q = q.where(Email.id.in_(ids))
    if conversation_ids:
        q = q.where(or_(*(Email.conversation_id.like(f"{cid}%") for cid in conversation_ids)))
    if filters:
        q = _apply_field_filters(q, filters)
    result = await session.execute(q)
    return result.scalar() or 0


async def exists(session: AsyncSession, conversation_id: str) -> bool:
    """Check if a conversation_id already exists."""
    q = select(Email.id).where(Email.conversation_id == conversation_id).limit(1)
    result = await session.execute(q)
    return result.scalar() is not None


async def update_conversation_body(
    session: AsyncSession,
    conversation_id: str,
    body: str,
) -> bool:
    """Update the body field for a conversation. Returns True if a row was updated."""
    from sqlalchemy import update
    stmt = (
        update(Email)
        .where(Email.conversation_id == conversation_id)
        .values(body=body)
    )
    result = await session.execute(stmt)
    await session.commit()
    updated = result.rowcount > 0
    if updated:
        logger.info("Updated body for conversation_id=%s (%d chars)", conversation_id, len(body))
    return updated


async def get_conversations_without_body(
    session: AsyncSession,
    app: str,
    folder: str | None = None,
    limit: int = 100,
) -> list[Email]:
    """Fetch conversations that have no body extracted yet."""
    q = select(Email).where(Email.app == app).where((Email.body == "") | (Email.body.is_(None)))
    if folder:
        q = q.where(Email.folder == folder)
    q = q.order_by(Email.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())
