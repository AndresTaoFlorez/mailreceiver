"""
wdd/models.py — Pure dataclasses for the Weighted Deficit Dispatch algorithm.

No ORM, no SQLAlchemy, no async. Framework-agnostic.

Deficit convention:
    deficit = ideal(i) - received(i)
    Positive deficit → system owes the specialist cases (priority)
    Negative deficit → specialist is ahead of their fair share
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class PoolMember:
    """A specialist available to receive cases."""

    code: str
    load_percentage: float | None = None  # None = auto-split equally
    cases_assigned: int = 0
    deficit: Decimal = field(default_factory=lambda: Decimal("0"))
    last_updated: datetime = field(default_factory=datetime.now)

    # Internal — updated by the engine during assignment
    _expected: Decimal = field(default_factory=lambda: Decimal("0"), repr=False)
    _effective_pct: float = field(default=0.0, repr=False)


@dataclass
class CaseItem:
    """A case/conversation to be assigned."""

    id: str
    level: int | None = None


@dataclass
class EscalationEvent:
    """An escalation or transfer that adjusts deficit manually.

    When a specialist escalates a case to another:
    - source loses 1 from their deficit (the case shouldn't count against them)
    - target gains 1 to their deficit (they took on extra work, system owes them)
    """

    case_id: str
    source_code: str  # specialist who escalates/transfers away
    target_code: str  # specialist who receives the escalation


@dataclass
class AssignmentResult:
    """One assignment decision made by the engine."""

    case_id: str
    specialist_code: str
    new_deficit: Decimal
    new_cases_assigned: int
    new_expected: Decimal


@dataclass
class DispatchReport:
    """Full output of an assignment run."""

    assigned: list[AssignmentResult] = field(default_factory=list)
    queued: list[str] = field(default_factory=list)

    @property
    def total_assigned(self) -> int:
        return len(self.assigned)

    @property
    def total_queued(self) -> int:
        return len(self.queued)
