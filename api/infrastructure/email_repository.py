"""
infrastructure/email_repository.py — Email (conversations) persistence.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import Email, Application
from api.domain.schemas import ScrapedEmail
from api.shared.logger import get_logger

logger = get_logger("email_repository")


# ---------------------------------------------------------------------------
# Field-presence filter (reusable)
# ---------------------------------------------------------------------------

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


def apply_field_filters(q, filters: list[str], field_map: dict | None = None):
    """Apply field presence/absence filters to a query.

    Each filter is a field name (has value) or !field (empty/null).
    Example: ["tags", "!body"] → has tags AND body is empty.
    """
    fmap = field_map or _FILTERABLE_FIELDS
    for f in filters:
        negate = f.startswith("!")
        field_name = f.lstrip("!")
        col = fmap.get(field_name)
        if col is None:
            continue
        if negate:
            q = q.where((col == "") | (col.is_(None)))
        else:
            q = q.where(col != "").where(col.is_not(None))
    return q


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def save_conversations(
    session: AsyncSession,
    conversations: list[ScrapedEmail],
    app: str,
    folder: str,
    level: int | None = None,
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
            "level": level,
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
            "level": stmt.excluded.level,
        },
    )
    result = await session.execute(stmt)
    await session.commit()

    upserted = result.rowcount
    logger.info("Upserted %d/%d conversations (app=%s, folder=%s)", upserted, len(rows), app, folder)
    return upserted


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
    q = select(Email).where(Email.app == app)
    if folder:
        q = q.where(Email.folder == folder)
    if ids:
        q = q.where(Email.id.in_(ids))
    if conversation_ids:
        q = q.where(or_(*(Email.conversation_id.like(f"{cid}%") for cid in conversation_ids)))
    if filters:
        q = apply_field_filters(q, filters)
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
    q = select(func.count(Email.id)).where(Email.app == app)
    if folder:
        q = q.where(Email.folder == folder)
    if ids:
        q = q.where(Email.id.in_(ids))
    if conversation_ids:
        q = q.where(or_(*(Email.conversation_id.like(f"{cid}%") for cid in conversation_ids)))
    if filters:
        q = apply_field_filters(q, filters)
    result = await session.execute(q)
    return result.scalar() or 0
