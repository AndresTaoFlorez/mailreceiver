from __future__ import annotations

import base64
from pathlib import Path

from sqlalchemy import select

from api.config import ATTACHMENTS_PATH, HTML_PATH
from api.database import Email, async_session
from api.models import EmailIn


async def upsert_email(email: EmailIn) -> dict:
    html_path = save_html(email.conversation_id, email.body_html)
    attachment_count = save_attachments(email.conversation_id, email.attachments)

    async with async_session() as session:
        stmt = select(Email).where(Email.conversation_id == email.conversation_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

        if row:
            row.subject = email.subject
            row.sender = email.from_
            row.received_at = email.received_at.isoformat()
            row.html_path = str(html_path)
            row.attachment_count = attachment_count
        else:
            row = Email(
                subject=email.subject,
                sender=email.from_,
                received_at=email.received_at.isoformat(),
                conversation_id=email.conversation_id,
                html_path=str(html_path),
                attachment_count=attachment_count,
            )
            session.add(row)

        await session.commit()

    return {
        "subject": email.subject,
        "from": email.from_,
        "received_at": email.received_at.isoformat(),
        "conversation_id": email.conversation_id,
        "html_path": str(html_path),
        "attachment_count": attachment_count,
    }


async def list_conversations() -> list[dict]:
    async with async_session() as session:
        result = await session.execute(select(Email).order_by(Email.id))
        rows = result.scalars().all()
        return [
            {
                "id": row.id,
                "subject": row.subject,
                "from": row.sender,
                "received_at": row.received_at,
                "conversation_id": row.conversation_id,
                "html_path": row.html_path,
                "attachment_count": row.attachment_count,
            }
            for row in rows
        ]


def save_html(conversation_id: str, body_html: str) -> Path:
    path = HTML_PATH / f"{conversation_id}.html"
    path.write_text(body_html, encoding="utf-8")
    return path


def save_attachments(conversation_id: str, attachments: list) -> int:
    if not attachments:
        return 0
    folder = ATTACHMENTS_PATH / conversation_id
    folder.mkdir(parents=True, exist_ok=True)
    for att in attachments:
        data = base64.b64decode(att.data)
        (folder / att.name).write_bytes(data)
    return len(attachments)
