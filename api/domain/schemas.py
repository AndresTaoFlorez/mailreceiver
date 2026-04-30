"""
domain/schemas.py — Request DTOs (Pydantic models for input validation).

Output serialization is handled by domain/mappers.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Scraping (used by agent) ---

class EmailDate(BaseModel):
    year: int | None = Field(default=None)
    month: int | None = Field(default=None)
    day: int | None = Field(default=None)
    hour: int | None = Field(default=None)


class ScrapedEmail(BaseModel):
    conversation_id: str = Field(default="")
    subject: str = Field(default="")
    sender: str = Field(default="")
    sender_email: str = Field(default="")
    tags: str = Field(default="")
    to_address: str = Field(default="")
    body: str = Field(default="")
    from_address: str = Field(default="")
    date: EmailDate = Field(default_factory=EmailDate)


class ScrapeResult(BaseModel):
    status: str
    application: str
    folder: str
    expected_unread_messages: int | None = None
    scraped_conversations: int = 0
    scroll_exhausted: bool = False
    complete: bool = False
    conversations: list[ScrapedEmail] = Field(default_factory=list)
    new_saved: int = 0


# Fields excluded from GET responses by default (heavy or internal).
EXCLUDE_BY_DEFAULT: set[str] = {"body", "date", "conversation_id", "created_at"}


# --- Especialist ---

class EspecialistCreate(BaseModel):
    code: str = Field(examples=["spec01"])
    name: str = Field(examples=["Juan Perez"])
    level: int = Field(examples=[1])
    load_percentage: int | None = Field(default=None, examples=[30])
    priority: int = Field(default=0, examples=[0])


class EspecialistUpdate(BaseModel):
    name: str | None = Field(default=None)
    level: int | None = Field(default=None)
    load_percentage: int | None = Field(default=None)
    priority: int | None = Field(default=None)
    active: bool | None = Field(default=None)


# --- FolderConfig ---

class FolderConfigCreate(BaseModel):
    folder_name: str = Field(examples=["SOPORTE BASICO"])
    level: int | None = Field(default=None, examples=[1])
    especialist_code: str | None = Field(default=None, examples=["S20"])


class FolderConfigUpdate(BaseModel):
    folder_name: str | None = Field(default=None)
    level: int | None = Field(default=None)
    active: bool | None = Field(default=None)


# --- Application ---

class ApplicationCreate(BaseModel):
    code: str = Field(examples=["tutela_en_linea"])
    name: str = Field(examples=["Tutela en Linea"])
    description: str | None = Field(default=None)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    active: bool | None = Field(default=None)


# --- Work Window ---

class WorkWindowCreate(BaseModel):
    especialist_code: str = Field(examples=["spec01"])
    application_code: str = Field(examples=["tutela_en_linea"])
    load_percentage: int | None = Field(default=None, examples=[30])
    schedule: dict = Field(examples=[{
        "2026-04-28": [{"start": "08:00", "end": "12:00"}],
        "2026-04-29": [{"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "17:00"}],
    }])
    inherit_balance_from: str | None = Field(default=None)


class WorkWindowUpdate(BaseModel):
    load_percentage: int | None = Field(default=None)
    schedule: dict | None = Field(default=None)
    active: bool | None = Field(default=None)


# --- Specialist Folder ---

class SpecialistFolderSet(BaseModel):
    especialist_code: str = Field(examples=["spec01"])
    folder_name: str = Field(examples=["CARPETA ESPECIALISTA 01"])


class SpecialistFolderUpdate(BaseModel):
    folder_name: str | None = Field(default=None)
    active: bool | None = Field(default=None)


# --- Tickets ---

class CreateTicketsRequest(BaseModel):
    application: str = Field(examples=["justicia_xxi_web"])
    subcategory: str = Field(default="Asesoria / Consulta En General")
    internal_subcategory: str | None = Field(default=None)
    hold_reason: str | None = Field(default="Fuerza mayor")
