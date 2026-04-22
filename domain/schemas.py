from __future__ import annotations

import math
import uuid

from pydantic import BaseModel, Field


class EmailDate(BaseModel):
    year: int | None = Field(default=None, description="Year (e.g. 2026)")
    month: int | None = Field(default=None, description="Month (1-12)")
    day: int | None = Field(default=None, description="Day of month (1-31)")
    hour: int | None = Field(default=None, description="Hour (0-23)")


class ScrapedEmail(BaseModel):
    conversation_id: str = Field(default="", description="Exchange conversation thread ID")
    subject: str = Field(default="", description="Email subject line")
    sender: str = Field(default="", description="Sender display name")
    sender_email: str = Field(default="", description="Sender email address")
    date: EmailDate = Field(default_factory=EmailDate, description="Parsed date components")


class EmailOut(BaseModel):
    id: uuid.UUID
    conversation_id: str
    subject: str
    sender: str
    sender_email: str
    date: EmailDate
    created_at: str

    @classmethod
    def from_row(cls, row) -> EmailOut:
        return cls(
            id=row.id,
            conversation_id=row.conversation_id,
            subject=row.subject,
            sender=row.sender,
            sender_email=row.sender_email,
            date=EmailDate(year=row.year, month=row.month, day=row.day, hour=row.hour),
            created_at=row.created_at.isoformat() if row.created_at else "",
        )


class PaginatedResponse(BaseModel):
    status: str = "ok"
    page: int
    per_page: int
    total: int
    pages: int
    new_saved: int = Field(default=0, description="New conversations saved in this scrape")
    conversations: list[EmailOut]

    @classmethod
    def build(cls, rows: list, total: int, page: int, per_page: int, new_saved: int = 0) -> PaginatedResponse:
        return cls(
            page=page,
            per_page=per_page,
            total=total,
            pages=math.ceil(total / per_page) if per_page > 0 else 0,
            new_saved=new_saved,
            conversations=[EmailOut.from_row(r) for r in rows],
        )


class ScrapeResult(BaseModel):
    status: str = Field(description="ok or error")
    application: str = Field(description="Application key")
    folder: str = Field(description="Outlook folder name")
    expected_unread_messages: int | None = Field(default=None, description="Unread message count from folder badge")
    scraped_conversations: int = Field(default=0, description="Number of conversation rows scraped")
    scroll_exhausted: bool = Field(default=False, description="Whether the full list was scrolled")
    complete: bool = Field(default=False, description="Whether scrape is considered complete")
    conversations: list[ScrapedEmail] = Field(default_factory=list, description="Scraped email conversations")
    new_saved: int = Field(default=0, description="New conversations persisted to DB (duplicates skipped)")
