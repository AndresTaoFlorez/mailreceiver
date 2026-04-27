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


# Fields excluded from GET responses by default (heavy or internal).
# Pass them in ?include=body,date,conversation_id,created_at to get them back.
EXCLUDE_BY_DEFAULT: set[str] = {"body", "date", "conversation_id", "created_at"}


class EmailOut(BaseModel):
    id: uuid.UUID
    conversation_id: str | None = None
    folder: str
    subject: str
    sender: str
    sender_email: str
    body: str | None = None
    tags: str = ""
    to_address: str = ""
    from_address: str = ""
    date: EmailDate | None = None
    created_at: str | None = None

    @classmethod
    def from_row(cls, row, include: set[str] | None = None) -> EmailOut:
        included = include or set()
        return cls(
            id=row.id,
            conversation_id=row.conversation_id if "conversation_id" in included else None,
            folder=row.folder,
            subject=row.subject,
            sender=row.sender,
            sender_email=row.sender_email,
            body=(row.body or "") if "body" in included else None,
            tags=row.tags or "",
            to_address=row.to_address or "",
            from_address=row.from_address or "",
            date=EmailDate(year=row.year, month=row.month, day=row.day, hour=row.hour) if "date" in included else None,
            created_at=(row.created_at.isoformat() if row.created_at else "") if "created_at" in included else None,
        )


class FilterSummary(BaseModel):
    filters_applied: list[str] = Field(description="Active filters")
    total_unfiltered: int = Field(description="Total records without filters")
    total_filtered: int = Field(description="Total records matching filters")
    showing: int = Field(description="Records in this page")


class PaginatedResponse(BaseModel):
    status: str = "ok"
    page: int
    per_page: int
    total: int
    pages: int
    new_saved: int = Field(default=0, description="New conversations saved in this scrape")
    summary: FilterSummary | None = None
    conversations: list[EmailOut]

    @classmethod
    def build(
        cls,
        rows: list,
        total: int,
        page: int,
        per_page: int,
        new_saved: int = 0,
        include: set[str] | None = None,
        filters: list[str] | None = None,
        total_unfiltered: int | None = None,
    ) -> PaginatedResponse:
        convs = [EmailOut.from_row(r, include=include) for r in rows]
        summary = None
        if filters:
            summary = FilterSummary(
                filters_applied=filters,
                total_unfiltered=total_unfiltered if total_unfiltered is not None else total,
                total_filtered=total,
                showing=len(convs),
            )
        return cls(
            page=page,
            per_page=per_page,
            total=total,
            pages=math.ceil(total / per_page) if per_page > 0 else 0,
            new_saved=new_saved,
            summary=summary,
            conversations=convs,
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
    code: str = Field(
        description="Unique short code that identifies this specialist across the system",
        examples=["spec01"],
    )
    name: str = Field(
        description="Full display name of the specialist",
        examples=["Juan Perez"],
    )
    level: int = Field(
        description="Support level this specialist handles. Matches the level defined in folder_config",
        examples=[1],
    )
    load_percentage: int | None = Field(
        default=None,
        description="Fixed percentage of cases this specialist should receive (1-100). Leave null to auto-distribute the remaining percentage equally",
        examples=[30],
    )
    priority: int = Field(
        default=0,
        description="Tiebreaker when two specialists have the same balance. Lower number = higher priority",
        examples=[0],
    )


class EspecialistUpdate(BaseModel):
    name: str | None = Field(default=None, description="New display name", examples=["Juan Perez"])
    level: int | None = Field(default=None, description="New support level", examples=[2])
    load_percentage: int | None = Field(default=None, description="New fixed load %. Null = auto-distribute", examples=[25])
    priority: int | None = Field(default=None, description="New priority (lower = higher)", examples=[1])
    active: bool | None = Field(default=None, description="Set false to exclude from future assignments", examples=[True])


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
    folder_name: str = Field(
        description="Exact Outlook folder name. Must match the folder name in the mailbox",
        examples=["SOPORTE BASICO"],
    )
    level: int = Field(
        description="Support level this folder represents. Used by the dispatcher to route cases to the right specialist pool",
        examples=[1],
    )


class FolderConfigUpdate(BaseModel):
    folder_name: str | None = Field(default=None, description="New Outlook folder name", examples=["SOPORTE AVANZADO"])
    level: int | None = Field(default=None, description="New support level", examples=[2])
    active: bool | None = Field(default=None, description="Set false to stop using this folder mapping", examples=[True])


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
    application: str = Field(description="Application code to assign specialists for", examples=["tutela_en_linea"])
    folder: str | None = Field(default=None, description="Only assign conversations from this folder. Null = all folders", examples=["ANDRES TAO (S20)"])


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
    application: str = Field(description="Application code the tickets belong to", examples=["tutela_en_linea"])
    conversation_ids: list[uuid.UUID] = Field(description="List of conversation UUIDs to create Judit/TybaCase tickets for")


# --- Application schemas ---

class ApplicationCreate(BaseModel):
    code: str = Field(
        description="Unique code used as primary key. Must match the app_name used in scraping routes",
        examples=["tutela_en_linea"],
    )
    name: str = Field(
        description="Human-readable display name shown in dashboards and reports",
        examples=["Tutela en Linea"],
    )
    description: str | None = Field(
        default=None,
        description="Optional notes about what this application handles",
        examples=["Outlook mailbox for Tutela en Linea support cases"],
    )


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, description="New display name", examples=["Tutela en Linea v2"])
    description: str | None = Field(default=None, description="New description", examples=["Updated description"])
    active: bool | None = Field(default=None, description="Set false to disable the application entirely", examples=[True])


class ApplicationOut(BaseModel):
    code: str
    name: str
    description: str | None
    active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> ApplicationOut:
        return cls(
            code=row.code,
            name=row.name,
            description=row.description,
            active=row.active,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )


# --- Work Window schemas ---

class WorkWindowCreate(BaseModel):
    especialist_code: str = Field(
        description="Which specialist this window belongs to",
        examples=["spec01"],
    )
    application_code: str = Field(
        description="Which application this specialist will handle during this window",
        examples=["tutela_en_linea"],
    )
    load_percentage: int | None = Field(
        default=None,
        description="Fixed percentage of cases (1-100). Leave null to auto-split the remaining % equally among all null specialists",
        examples=[30],
    )
    schedule: dict = Field(
        description="When this specialist is available. Keys = ISO dates, values = array of time slots {start, end} in HH:MM. Days not listed = specialist is off",
        examples=[{
            "2026-04-28": [{"start": "08:00", "end": "12:00"}],
            "2026-04-29": [{"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "17:00"}],
            "2026-04-30": [{"start": "08:00", "end": "17:00"}],
        }],
    )
    inherit_balance_from: uuid.UUID | None = Field(
        default=None,
        description="ID of a previous work window. If set, the specialist starts this window with the leftover balance (debt/surplus) from that window instead of zero",
    )


class WorkWindowUpdate(BaseModel):
    load_percentage: int | None = Field(default=None, description="New workload percentage. Already assigned cases are not moved", examples=[25])
    schedule: dict | None = Field(
        default=None,
        description="Full replacement schedule. Not a partial patch — send the complete schedule",
        examples=[{"2026-05-05": [{"start": "08:00", "end": "17:00"}]}],
    )
    active: bool | None = Field(default=None, description="Set false to close this window early", examples=[False])


class WorkWindowOut(BaseModel):
    id: uuid.UUID
    especialist_code: str
    application_code: str
    load_percentage: int | None
    schedule: dict
    active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> WorkWindowOut:
        return cls(
            id=row.id,
            especialist_code=row.especialist_code,
            application_code=row.application_code,
            load_percentage=row.load_percentage,
            schedule=row.schedule,
            active=row.active,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )


# --- Balance Snapshot schemas ---

class BalanceSnapshotOut(BaseModel):
    id: uuid.UUID
    especialist_code: str
    application_code: str
    work_window_id: uuid.UUID
    cases_assigned: int
    expected_cases: float
    balance: float
    last_reset_at: str | None
    updated_at: str

    @classmethod
    def from_row(cls, row) -> BalanceSnapshotOut:
        return cls(
            id=row.id,
            especialist_code=row.especialist_code,
            application_code=row.application_code,
            work_window_id=row.work_window_id,
            cases_assigned=row.cases_assigned,
            expected_cases=float(row.expected_cases),
            balance=float(row.balance),
            last_reset_at=row.last_reset_at.isoformat() if row.last_reset_at else None,
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )


# --- Assignment (new dispatch) schemas ---

class AssignmentOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    especialist_code: str
    ticket_id: uuid.UUID | None
    application_code: str
    level: int
    work_window_id: uuid.UUID | None
    assigned_at: str

    @classmethod
    def from_row(cls, row) -> AssignmentOut:
        return cls(
            id=row.id,
            conversation_id=row.conversation_id,
            especialist_code=row.especialist_code,
            ticket_id=row.ticket_id,
            application_code=row.application_code,
            level=row.level,
            work_window_id=row.work_window_id,
            assigned_at=row.assigned_at.isoformat() if row.assigned_at else "",
        )


class DispatchRequest(BaseModel):
    application_code: str = Field(
        description="Application code to run the dispatch algorithm for",
        examples=["tutela_en_linea"],
    )
    folder: str | None = Field(
        default=None,
        description="Only dispatch conversations from this specific folder. Leave null to dispatch all unassigned conversations for the application",
        examples=["SOPORTE BASICO"],
    )


class DispatchResultItem(BaseModel):
    conversation_id: uuid.UUID = Field(description="Assigned conversation UUID")
    especialist_code: str = Field(description="Specialist who received the assignment")
    level: int = Field(description="Support level determined by folder_config")
    work_window_id: uuid.UUID | None = Field(description="Work window used for this assignment")


class DispatchResult(BaseModel):
    status: str = "ok"
    total_assigned: int = Field(description="Number of conversations assigned in this run")
    queued: int = Field(default=0, description="Conversations with no active pool — waiting for next available window")
    assignments: list[DispatchResultItem] = Field(description="List of individual assignments made")


# --- Coordinator schemas ---

# --- Specialist Folder schemas ---

class SpecialistFolderSet(BaseModel):
    especialist_code: str = Field(
        description="Code of the specialist to assign a folder to",
        examples=["spec01"],
    )
    folder_name: str = Field(
        description="Outlook folder name this specialist handles in the application",
        examples=["CARPETA ESPECIALISTA 01"],
    )


class SpecialistFolderUpdate(BaseModel):
    folder_name: str | None = Field(default=None, description="New folder name", examples=["CARPETA NUEVA"])
    active: bool | None = Field(default=None, description="Set false to disable this mapping", examples=[True])


class SpecialistFolderOut(BaseModel):
    id: uuid.UUID
    application_code: str
    especialist_code: str
    folder_name: str
    active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> SpecialistFolderOut:
        return cls(
            id=row.id,
            application_code=row.application_code,
            especialist_code=row.especialist_code,
            folder_name=row.folder_name,
            active=row.active,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )


class LoadStatusEntry(BaseModel):
    especialist_code: str = Field(description="Specialist code")
    especialist_name: str = Field(description="Specialist display name")
    cases_assigned: int = Field(description="Total cases assigned in the current window")
    expected_cases: float = Field(description="Expected cases based on load_percentage and total pool cases")
    balance: float = Field(description="Cumulative balance: positive = ahead, negative = system owes cases")
    window_active: bool = Field(description="Whether the specialist's work window is currently active")
