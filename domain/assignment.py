"""
domain/assignment.py — Specialist assignment logic.

Distributes conversations among specialists based on level, load_percentage, and priority.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from domain.especialist_repository import get_especialists
from domain.folder_config_repository import get_level_for_folder
from domain.ticket_repository import count_tickets_by_especialist
from domain.models import Email, Especialist
from domain.schemas import AssignmentItem, AssignmentSummaryEntry, AssignmentResult
from shared.logger import get_logger

logger = get_logger("assignment")


def _distribute_cases(
    specialists: list[Especialist],
    total_cases: int,
) -> dict[str, int]:
    """
    Distribute total_cases among specialists based on load_percentage and priority.

    - Specialists with load_percentage set get exactly that % of cases.
    - Specialists with load_percentage=NULL split the remaining % equally.
    - Rounding remainders go to specialists with lowest priority number (highest priority).
    """
    if not specialists or total_cases == 0:
        return {}

    fixed = [(s, s.load_percentage) for s in specialists if s.load_percentage is not None]
    auto = [s for s in specialists if s.load_percentage is None]

    fixed_total_pct = sum(pct for _, pct in fixed)

    remaining_pct = max(0, 100 - fixed_total_pct)
    auto_pct = remaining_pct / len(auto) if auto else 0

    raw: list[tuple[Especialist, float]] = []
    for s, pct in fixed:
        raw.append((s, total_cases * pct / 100))
    for s in auto:
        raw.append((s, total_cases * auto_pct / 100))

    # Sort by priority (lower = higher priority) for rounding allocation
    raw.sort(key=lambda x: x[0].priority)

    result: dict[str, int] = {}
    allocated = 0
    remainders: list[tuple[str, float]] = []

    for s, exact in raw:
        floored = int(exact)
        result[s.code] = floored
        allocated += floored
        remainders.append((s.code, exact - floored))

    # Distribute leftover cases by largest remainder, tiebreak by priority (already sorted)
    leftover = total_cases - allocated
    remainders.sort(key=lambda x: -x[1])
    for i in range(min(leftover, len(remainders))):
        result[remainders[i][0]] += 1

    return result


async def assign_specialists(
    session: AsyncSession,
    conversations: list[Email],
    application: str,
) -> AssignmentResult:
    """
    Assign specialists to a list of conversations based on folder → level mapping
    and specialist load configuration.
    """
    # Group conversations by level
    by_level: dict[int, list[Email]] = defaultdict(list)
    no_level: list[Email] = []

    for conv in conversations:
        level = await get_level_for_folder(session, conv.folder, application)
        if level is not None:
            by_level[level].append(conv)
        else:
            no_level.append(conv)

    if no_level:
        logger.warning(
            "%d conversations have no folder_config mapping, skipping assignment",
            len(no_level),
        )

    all_assignments: list[AssignmentItem] = []
    summary_1: list[AssignmentSummaryEntry] = []
    summary_2: list[AssignmentSummaryEntry] = []

    for level in sorted(by_level.keys()):
        convs = by_level[level]
        specialists = await get_especialists(session, level=level, active_only=True)

        if not specialists:
            logger.warning("No active specialists for level %d, skipping %d conversations", level, len(convs))
            continue

        distribution = _distribute_cases(specialists, len(convs))

        # Build a flat list of specialist codes repeated by their allocation
        assignment_queue: list[str] = []
        for s in specialists:
            count = distribution.get(s.code, 0)
            assignment_queue.extend([s.code] * count)

        # Assign each conversation
        spec_name_map = {s.code: s.name for s in specialists}
        counts: dict[str, int] = defaultdict(int)

        for i, conv in enumerate(convs):
            if i < len(assignment_queue):
                spec_code = assignment_queue[i]
            else:
                # Fallback: round-robin if distribution doesn't cover all
                spec_code = specialists[i % len(specialists)].code

            all_assignments.append(AssignmentItem(
                conversation_id=conv.id,
                especialist_code=spec_code,
                level=level,
            ))
            counts[spec_code] += 1

        summary_entries = [
            AssignmentSummaryEntry(
                especialist_code=code,
                especialist_name=spec_name_map.get(code, ""),
                cases_assigned=cnt,
            )
            for code, cnt in counts.items()
        ]

        if level == 1:
            summary_1 = summary_entries
        elif level == 2:
            summary_2 = summary_entries

    return AssignmentResult(
        status="ok",
        total_assigned=len(all_assignments),
        assignments=all_assignments,
        summary_level_1=summary_1,
        summary_level_2=summary_2,
    )
