"""
domain/dispatcher.py — Workload Dispatch Algorithm.

Classifier → Pool Builder → Progressive Drip → Overflow Rule.

Level is derived from folder_config per application.
If an application only has level 1 configured, all dispatch goes to level 1.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Email, WorkWindow, BalanceSnapshot, Especialist
from domain.folder_config_repository import get_level_for_folder, get_folders_for_level
from domain.repository import get_conversations
from domain.work_window_repository import get_active_windows_now
from domain.balance_repository import ensure_snapshot, increment_assignment
from domain.assignment_repository import create_assignment, is_conversation_assigned
from domain.especialist_repository import get_especialists
from shared.logger import get_logger

logger = get_logger("dispatcher")


async def _classify_conversations(
    session: AsyncSession,
    conversations: list[Email],
    application_code: str,
) -> tuple[dict[int, list[Email]], list[Email]]:
    """Group conversations by level using folder_config. Returns (by_level, no_level)."""
    by_level: dict[int, list[Email]] = defaultdict(list)
    no_level: list[Email] = []

    for conv in conversations:
        level = await get_level_for_folder(session, conv.folder, application_code)
        if level is not None:
            by_level[level].append(conv)
        else:
            no_level.append(conv)

    if no_level:
        logger.warning(
            "%d conversations have no folder_config for app=%s, cannot classify",
            len(no_level), application_code,
        )

    return by_level, no_level


def _compute_load_percentages(
    windows: list[WorkWindow],
) -> dict[str, float]:
    """Compute effective load % for each specialist in the pool.

    Windows with load_percentage set use that value.
    Windows with NULL split the remaining % equally.
    """
    fixed: list[tuple[str, int]] = []
    auto: list[str] = []

    for w in windows:
        if w.load_percentage is not None:
            fixed.append((w.especialist_code, w.load_percentage))
        else:
            auto.append(w.especialist_code)

    fixed_total = sum(pct for _, pct in fixed)
    remaining = max(0, 100 - fixed_total)
    auto_pct = remaining / len(auto) if auto else 0

    result: dict[str, float] = {}
    for code, pct in fixed:
        result[code] = pct
    for code in auto:
        result[code] = auto_pct

    return result


async def _build_pool(
    session: AsyncSession,
    application_code: str,
    level: int,
    now: datetime,
) -> tuple[list[WorkWindow], dict[str, float]]:
    """Build the eligible specialist pool for a given level at the current time.

    Returns (active_windows, load_percentages).
    """
    # Get windows active right now for this application
    active_windows = await get_active_windows_now(session, application_code, now)

    if not active_windows:
        return [], {}

    # Filter to specialists that handle this level
    level_specialists = await get_especialists(session, level=level, active_only=True)
    level_codes = {s.code for s in level_specialists}

    # Primary pool: windows whose specialist handles this level
    primary = [w for w in active_windows if w.especialist_code in level_codes]

    if primary:
        load_pcts = _compute_load_percentages(primary)
        return primary, load_pcts

    # Overflow: look for multi-level specialists (those not filtered by a single level)
    all_specialists = await get_especialists(session, active_only=True)
    overflow_codes = {s.code for s in all_specialists}
    overflow = [w for w in active_windows if w.especialist_code in overflow_codes]

    if overflow:
        logger.info(
            "Primary pool empty for level=%d app=%s, using overflow (%d specialists)",
            level, application_code, len(overflow),
        )
        load_pcts = _compute_load_percentages(overflow)
        return overflow, load_pcts

    return [], {}


async def dispatch(
    session: AsyncSession,
    conversations: list[Email],
    application_code: str,
    now: datetime | None = None,
) -> dict:
    """Main dispatch entry point. Classifies, builds pools, and assigns via progressive drip.

    Returns dict with total_assigned, queued count, and assignment details.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Step 1: Classify
    by_level, no_level = await _classify_conversations(session, conversations, application_code)

    all_assignments: list[dict] = []
    queued_count = len(no_level)

    for level in sorted(by_level.keys()):
        convs = by_level[level]

        # Filter out already-assigned conversations
        unassigned = []
        for conv in convs:
            if not await is_conversation_assigned(session, conv.id):
                unassigned.append(conv)

        if not unassigned:
            continue

        # Step 2: Build pool
        windows, load_pcts = await _build_pool(session, application_code, level, now)

        if not windows:
            logger.warning(
                "No active pool for level=%d app=%s at %s, queuing %d conversations",
                level, application_code, now.isoformat(), len(unassigned),
            )
            queued_count += len(unassigned)
            continue

        # Map specialist_code → window for quick lookup
        code_to_window: dict[str, WorkWindow] = {w.especialist_code: w for w in windows}

        # Step 3: Ensure balance snapshots exist for each specialist in the pool
        snapshots: dict[str, BalanceSnapshot] = {}
        for w in windows:
            snap = await ensure_snapshot(
                session,
                especialist_code=w.especialist_code,
                application_code=application_code,
                work_window_id=w.id,
            )
            snapshots[w.especialist_code] = snap

        # Count total cases in this pool (existing + new to assign)
        total_existing = sum(s.cases_assigned for s in snapshots.values())
        total_cases = total_existing + len(unassigned)

        # Step 4: Progressive Drip — assign one by one
        for conv in unassigned:
            # Sort pool by balance (most negative first = highest priority)
            # Tiebreak: by assigned_at on snapshot (least recent gets priority)
            pool_order = sorted(
                snapshots.keys(),
                key=lambda code: (float(snapshots[code].balance), str(snapshots[code].updated_at)),
            )

            chosen_code = pool_order[0]
            chosen_window = code_to_window[chosen_code]
            chosen_snap = snapshots[chosen_code]

            # Create the assignment record
            assignment = await create_assignment(
                session,
                conversation_id=conv.id,
                especialist_code=chosen_code,
                application_code=application_code,
                level=level,
                work_window_id=chosen_window.id,
            )

            # Update balance: recalculate with new totals
            total_existing += 1
            await increment_assignment(
                session,
                snapshot=chosen_snap,
                total_cases_in_pool=total_existing,
                load_percentage=load_pcts.get(chosen_code, 0),
            )

            # Also recalculate expected_cases for all other specialists
            for other_code, other_snap in snapshots.items():
                if other_code != chosen_code:
                    pct = load_pcts.get(other_code, 0)
                    other_snap.expected_cases = Decimal(str(total_existing * pct / 100))
                    other_snap.balance = Decimal(str(other_snap.cases_assigned)) - other_snap.expected_cases

            all_assignments.append({
                "conversation_id": conv.id,
                "especialist_code": chosen_code,
                "level": level,
                "work_window_id": chosen_window.id,
            })

    await session.commit()

    logger.info(
        "Dispatch complete: app=%s assigned=%d queued=%d",
        application_code, len(all_assignments), queued_count,
    )

    return {
        "status": "ok",
        "total_assigned": len(all_assignments),
        "queued": queued_count,
        "assignments": all_assignments,
    }


async def dispatch_level(
    session: AsyncSession,
    application_code: str,
    level: int,
    now: datetime | None = None,
) -> dict:
    """Dispatch conversations for a specific level.

    1. Looks up folder_config to find which folders belong to this level
    2. Fetches conversations from those folders
    3. Assigns unassigned ones via progressive drip
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Step 1: Get folders for this level
    folders = await get_folders_for_level(session, application_code, level)
    if not folders:
        return {
            "status": "ok",
            "level": level,
            "folders_used": [],
            "total_assigned": 0,
            "queued": 0,
            "assignments": [],
            "message": f"No folders configured for level {level} in this application",
        }

    # Step 2: Fetch conversations from all folders for this level
    all_conversations: list[Email] = []
    for folder in folders:
        convs = await get_conversations(session, app=application_code, folder=folder, limit=10000, offset=0)
        all_conversations.extend(convs)

    # Step 3: Filter out already-assigned
    unassigned: list[Email] = []
    for conv in all_conversations:
        if not await is_conversation_assigned(session, conv.id):
            unassigned.append(conv)

    if not unassigned:
        return {
            "status": "ok",
            "level": level,
            "folders_used": folders,
            "total_assigned": 0,
            "queued": 0,
            "assignments": [],
        }

    # Step 4: Build pool
    windows, load_pcts = await _build_pool(session, application_code, level, now)

    if not windows:
        logger.warning(
            "No active pool for level=%d app=%s at %s, queuing %d conversations",
            level, application_code, now.isoformat(), len(unassigned),
        )
        return {
            "status": "ok",
            "level": level,
            "folders_used": folders,
            "total_assigned": 0,
            "queued": len(unassigned),
            "assignments": [],
        }

    # Map specialist_code → window
    code_to_window: dict[str, WorkWindow] = {w.especialist_code: w for w in windows}

    # Step 5: Ensure balance snapshots
    snapshots: dict[str, BalanceSnapshot] = {}
    for w in windows:
        snap = await ensure_snapshot(
            session,
            especialist_code=w.especialist_code,
            application_code=application_code,
            work_window_id=w.id,
        )
        snapshots[w.especialist_code] = snap

    total_existing = sum(s.cases_assigned for s in snapshots.values())

    # Step 6: Progressive Drip
    all_assignments: list[dict] = []
    for conv in unassigned:
        pool_order = sorted(
            snapshots.keys(),
            key=lambda code: (float(snapshots[code].balance), str(snapshots[code].updated_at)),
        )

        chosen_code = pool_order[0]
        chosen_window = code_to_window[chosen_code]
        chosen_snap = snapshots[chosen_code]

        await create_assignment(
            session,
            conversation_id=conv.id,
            especialist_code=chosen_code,
            application_code=application_code,
            level=level,
            work_window_id=chosen_window.id,
        )

        total_existing += 1
        await increment_assignment(
            session,
            snapshot=chosen_snap,
            total_cases_in_pool=total_existing,
            load_percentage=load_pcts.get(chosen_code, 0),
        )

        for other_code, other_snap in snapshots.items():
            if other_code != chosen_code:
                pct = load_pcts.get(other_code, 0)
                other_snap.expected_cases = Decimal(str(total_existing * pct / 100))
                other_snap.balance = Decimal(str(other_snap.cases_assigned)) - other_snap.expected_cases

        all_assignments.append({
            "conversation_id": str(conv.id),
            "especialist_code": chosen_code,
            "level": level,
            "work_window_id": str(chosen_window.id),
        })

    await session.commit()

    logger.info(
        "Dispatch level=%d complete: app=%s folders=%s assigned=%d",
        level, application_code, folders, len(all_assignments),
    )

    return {
        "status": "ok",
        "level": level,
        "folders_used": folders,
        "total_assigned": len(all_assignments),
        "queued": 0,
        "assignments": all_assignments,
    }
