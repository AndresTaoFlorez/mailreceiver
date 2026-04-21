from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentIn(BaseModel):
    name: str = Field(description="Filename of the attachment", examples=["invoice.pdf"])
    content_type: str = Field(description="MIME type", examples=["application/pdf"])
    data: str = Field(description="File content encoded in base64")


class EmailIn(BaseModel):
    model_config = {"populate_by_name": True}

    subject: str = Field(description="Email subject line", examples=["Orden #1234"])
    from_: str = Field(alias="from", description="Sender email address", examples=["cliente@example.com"])
    received_at: datetime = Field(description="Timestamp when the email was received", examples=["2026-04-20T15:30:00Z"])
    conversation_id: str = Field(description="Unique conversation thread ID", examples=["conv-abc-123"])
    body_html: str = Field(description="Full HTML body of the email", examples=["<p>Hola mundo</p>"])
    attachments: list[AttachmentIn] = Field(default=[], description="List of base64-encoded file attachments")


class EmailOut(BaseModel):
    id: int
    subject: str
    from_: str
    received_at: str
    conversation_id: str
    html_path: str
    attachment_count: int
