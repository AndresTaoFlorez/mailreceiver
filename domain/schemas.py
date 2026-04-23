from __future__ import annotations

import math
import uuid

from pydantic import BaseModel, Field


# --- Email schemas ---

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
    tags: str = Field(default="", description="Email tags/categories")
    to_address: str = Field(default="", description="Recipient address")
    body: str = Field(default="", description="Email body HTML")
    from_address: str = Field(default="", description="Sender address (explicit)")
    date: EmailDate = Field(default_factory=EmailDate, description="Parsed date components")


class EmailOut(BaseModel):
    id: uuid.UUID
    conversation_id: str
    subject: str
    sender: str
    sender_email: str
    body: str = ""
    tags: str = ""
    to_address: str = ""
    from_address: str = ""
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
            body=row.body or "",
            tags=row.tags or "",
            to_address=row.to_address or "",
            from_address=row.from_address or "",
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


# --- Especialist schemas ---

class EspecialistCreate(BaseModel):
    code: str = Field(description="Unique specialist code (e.g. s20, s15)")
    name: str = Field(description="Specialist full name")
    level: int = Field(description="1 = básico, 2 = avanzado")
    load_percentage: int | None = Field(default=None, description="Fixed load %. NULL = auto-distribute")
    priority: int = Field(default=0, description="Lower number = higher priority for tiebreaking")


class EspecialistUpdate(BaseModel):
    name: str | None = None
    level: int | None = None
    load_percentage: int | None = Field(default=None)
    priority: int | None = None
    active: bool | None = None


class EspecialistOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    level: int
    load_percentage: int | None
    priority: int
    active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> EspecialistOut:
        return cls(
            id=row.id,
            code=row.code,
            name=row.name,
            level=row.level,
            load_percentage=row.load_percentage,
            priority=row.priority,
            active=row.active,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )


# --- FolderConfig schemas ---

class FolderConfigCreate(BaseModel):
    folder_name: str = Field(description="Outlook folder name")
    level: int = Field(description="1 = SOPORTE BASICO, 2 = SOPORTE AVANZADO")
    application: str = Field(description="Application key (e.g. tutela_en_linea)")


class FolderConfigUpdate(BaseModel):
    folder_name: str | None = None
    level: int | None = None
    application: str | None = None
    active: bool | None = None


class FolderConfigOut(BaseModel):
    id: uuid.UUID
    folder_name: str
    level: int
    application: str
    active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> FolderConfigOut:
        return cls(
            id=row.id,
            folder_name=row.folder_name,
            level=row.level,
            application=row.application,
            active=row.active,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )


# --- Ticket schemas ---

class TicketOut(BaseModel):
    id: uuid.UUID
    code: str | None
    type: str | None
    application: str
    conversation_id: uuid.UUID | None
    especialist_code: str | None
    date_time: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> TicketOut:
        return cls(
            id=row.id,
            code=row.code,
            type=row.type,
            application=row.application,
            conversation_id=row.conversation_id,
            especialist_code=row.especialist_code,
            date_time=row.date_time.isoformat() if row.date_time else "",
            created_at=row.created_at.isoformat() if row.created_at else "",
        )


# --- Assignment schemas ---

class AssignRequest(BaseModel):
    application: str = Field(description="Application key")
    folder: str | None = Field(default=None, description="Optional folder filter")


class AssignmentItem(BaseModel):
    conversation_id: uuid.UUID
    especialist_code: str
    level: int


class AssignmentSummaryEntry(BaseModel):
    especialist_code: str
    especialist_name: str
    cases_assigned: int


class AssignmentResult(BaseModel):
    status: str = "ok"
    total_assigned: int
    assignments: list[AssignmentItem]
    summary_level_1: list[AssignmentSummaryEntry]
    summary_level_2: list[AssignmentSummaryEntry]


# --- Ticket creation schemas ---

class CreateTicketsRequest(BaseModel):
    application: str = Field(description="Application key")
    conversation_ids: list[uuid.UUID] = Field(description="Conversation IDs to create tickets for")
