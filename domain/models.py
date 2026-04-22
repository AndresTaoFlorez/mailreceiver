"""
domain/models.py — SQLAlchemy ORM models for the mailreceiver database.

Table: conversations
    - id            : UUID PK (auto-generated)
    - conversation_id: unique Exchange conversation thread ID (prevents duplicates)
    - app           : application key (tutela_en_linea, justicia_xxi_web, etc.)
    - folder        : Outlook folder name
    - subject       : email subject
    - sender        : sender display name
    - sender_email  : sender email address
    - year/month/day/hour : parsed date components
    - created_at    : record creation timestamp
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Integer, String, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Email(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    app: Mapped[str] = mapped_column(String(50), nullable=False)
    folder: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False, default="")
    sender: Mapped[str] = mapped_column(String, nullable=False, default="")
    sender_email: Mapped[str] = mapped_column(String, nullable=False, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
