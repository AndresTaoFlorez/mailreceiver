"""
domain/mappers.py — ORM → dict mappers and standard response builders.

Single place to convert ORM rows to API-friendly dicts and wrap them
in consistent response envelopes. No Pydantic, no framework dependency.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Response envelope helpers
# ---------------------------------------------------------------------------

def ok(**data: Any) -> dict:
    """Wrap data in a standard success response."""
    return {"status": "ok", **data}


def ok_list(key: str, rows: list, mapper=None) -> dict:
    """Standard list response: {status, total, <key>: [...]}."""
    items = [mapper(r) for r in rows] if mapper else rows
    return {"status": "ok", "total": len(items), key: items}


def ok_page(
    key: str,
    rows: list,
    total: int,
    page: int,
    per_page: int,
    mapper=None,
    **extra: Any,
) -> dict:
    """Standard paginated response."""
    items = [mapper(r) for r in rows] if mapper else rows
    return {
        "status": "ok",
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": math.ceil(total / per_page) if per_page > 0 else 0,
        key: items,
        **extra,
    }


# ---------------------------------------------------------------------------
# ORM → dict mappers
# ---------------------------------------------------------------------------

def map_application(row) -> dict:
    return {
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def map_email(row, include: set[str] | None = None) -> dict:
    """Map an Email ORM row to a dict. Heavy fields excluded unless in `include`."""
    inc = include or set()
    d: dict[str, Any] = {
        "id": str(row.id),
        "folder": row.folder,
        "level": row.level,
        "subject": row.subject,
        "sender": row.sender,
        "sender_email": row.sender_email,
        "tags": row.tags or "",
        "to_address": row.to_address or "",
        "from_address": row.from_address or "",
    }
    if "conversation_id" in inc:
        d["conversation_id"] = row.conversation_id
    if "body" in inc:
        d["body"] = row.body or ""
    if "date" in inc:
        d["date"] = {"year": row.year, "month": row.month, "day": row.day, "hour": row.hour}
    if "created_at" in inc:
        d["created_at"] = row.created_at.isoformat() if row.created_at else ""
    return d


def map_especialist(row) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "level": row.level,
        "load_percentage": row.load_percentage,
        "priority": row.priority,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def map_ticket(row) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "type": row.type,
        "application": row.application,
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "especialist_code": row.especialist_code,
        "date_time": row.date_time.isoformat() if row.date_time else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def map_folder_config(row) -> dict:
    return {
        "id": str(row.id),
        "folder_name": row.folder_name,
        "level": row.level,
        "application": row.application,
        "especialist_id": str(row.especialist_id) if row.especialist_id else None,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def map_work_window(row) -> dict:
    return {
        "id": str(row.id),
        "especialist_id": str(row.especialist_id),
        "application_code": row.application_code,
        "load_percentage": row.load_percentage,
        "schedule": row.schedule,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def map_balance_snapshot(row) -> dict:
    return {
        "id": str(row.id),
        "especialist_id": str(row.especialist_id),
        "application_code": row.application_code,
        "work_window_id": str(row.work_window_id),
        "cases_assigned": row.cases_assigned,
        "expected_cases": float(row.expected_cases),
        "balance": float(row.balance),
        "last_reset_at": row.last_reset_at.isoformat() if row.last_reset_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def map_assignment(row) -> dict:
    return {
        "id": str(row.id),
        "thread_id": str(row.thread_id),
        "especialist_id": str(row.especialist_id),
        "ticket_id": str(row.ticket_id) if row.ticket_id else None,
        "application_code": row.application_code,
        "level": row.level,
        "work_window_id": str(row.work_window_id) if row.work_window_id else None,
        "assigned_at": row.assigned_at.isoformat() if row.assigned_at else "",
    }


def map_assignment_rich(row: tuple) -> dict:
    """Map a (Assignment, Email, Especialist) tuple to a rich response dict."""
    assignment, email, specialist = row
    return {
        # Assignment
        "id": str(assignment.id),
        "application_code": assignment.application_code,
        "level": assignment.level,
        "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else "",
        "ticket_id": str(assignment.ticket_id) if assignment.ticket_id else None,
        "work_window_id": str(assignment.work_window_id) if assignment.work_window_id else None,
        # Specialist
        "specialist": {
            "id": str(specialist.id),
            "code": specialist.code,
            "name": specialist.name,
            "level": specialist.level,
        },
        # Conversation / email
        "conversation": {
            "id": str(email.id),
            "folder": email.folder,
            "subject": email.subject,
            "sender": email.sender,
            "sender_email": email.sender_email,
            "to_address": email.to_address,
            "from_address": email.from_address,
            "tags": email.tags or "",
            "date": {
                "year": email.year,
                "month": email.month,
                "day": email.day,
                "hour": email.hour,
            },
        },
    }


def map_specialist_folder(row) -> dict:
    return {
        "id": str(row.id),
        "application_code": row.application_code,
        "especialist_id": str(row.especialist_id),
        "folder_name": row.folder_name,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def map_load_status(snap, specialist_name: str, window_active: bool) -> dict:
    return {
        "especialist_id": str(snap.especialist_id),
        "especialist_name": specialist_name,
        "cases_assigned": snap.cases_assigned,
        "expected_cases": float(snap.expected_cases),
        "balance": float(snap.balance),
        "window_active": window_active,
    }
