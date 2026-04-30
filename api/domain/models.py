"""
domain/models.py — SQLAlchemy ORM models for the mailreceiver database.

Tables: applications, conversations, especialist, tickets, folder_config,
        work_windows, balance_snapshots, assignments
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String, DateTime, Text, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = "applications"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


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
    application_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("applications.code"), nullable=False,
    )
    folder: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False, default="")
    sender: Mapped[str] = mapped_column(String, nullable=False, default="")
    sender_email: Mapped[str] = mapped_column(String, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    to_address: Mapped[str] = mapped_column(String, nullable=False, default="")
    from_address: Mapped[str] = mapped_column(String, nullable=False, default="")
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class Especialist(Base):
    __tablename__ = "especialist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    load_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    application: Mapped[str] = mapped_column(String(50), nullable=False)
    application_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("applications.code"), nullable=False,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True,
    )
    especialist_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("especialist.code"), nullable=True,
    )
    date_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class FolderConfig(Base):
    __tablename__ = "folder_config"
    __table_args__ = (
        # Partial uniqueness enforced by DB-level indexes (see migration 008).
        # analyst folders: unique (application_code, especialist_id) WHERE especialist_id IS NOT NULL
        # level folders:   unique (folder_name, application)         WHERE especialist_id IS NULL
        UniqueConstraint("application_code", "especialist_id", name="uq_folder_analyst"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    folder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    application: Mapped[str] = mapped_column(String(50), nullable=False)
    application_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("applications.code"), nullable=False,
    )
    especialist_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("especialist.id"), nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class WorkWindow(Base):
    __tablename__ = "work_windows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    especialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("especialist.id"), nullable=False,
    )
    application_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("applications.code"), nullable=False,
    )
    load_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    especialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("especialist.id"), nullable=False,
    )
    application_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("applications.code"), nullable=False,
    )
    work_window_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_windows.id"), nullable=False,
    )
    cases_assigned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_cases: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    last_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    inherited_from: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("balance_snapshots.id"), nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False,
    )
    especialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("especialist.id"), nullable=False,
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=True,
    )
    application_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("applications.code"), nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    work_window_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_windows.id"), nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


