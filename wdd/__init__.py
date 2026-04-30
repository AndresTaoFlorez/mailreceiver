"""
wdd — Weighted Deficit Dispatch. Standalone workload assignment component.

Pure Python deficit-first algorithm. No DB, no async, no framework dependencies.
Usable as an isolated library in any Python project.

Deficit convention:
    deficit(i) = ideal(i) - received(i)
    Positive → system owes the specialist cases
    Negative → specialist is ahead
"""

from wdd.engine import WorkloadEngine
from wdd.models import (
    AssignmentResult,
    CaseItem,
    DispatchReport,
    EscalationEvent,
    PoolMember,
)

__all__ = [
    "WorkloadEngine",
    "AssignmentResult",
    "CaseItem",
    "DispatchReport",
    "EscalationEvent",
    "PoolMember",
]
