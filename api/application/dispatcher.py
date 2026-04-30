"""
application/dispatcher.py — Adapter layer between DB and WorkloadEngine.

Fetches data from repositories, converts to engine dataclasses,
calls the pure algorithm, and persists results back to DB.

Routing rules for already-seen conversations (identified by thread_id):
  1. Not assigned yet            → assign normally via WDD engine.
  2. Assigned + NEW_CASE tag     → re-assign via WDD engine (new assignment record).
  3. Assigned + no new-case tag  → redirect: return target folder so the agent
                                   can move the email in Outlook (right-click → Move).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import Email, WorkWindow, BalanceSnapshot
from api.infrastructure.folder_config_repository import (
    get_level_for_folder, get_folders_for_level, get_folder_for_specialist,
)
from api.infrastructure.email_repository import get_conversations
from api.infrastructure.work_window_repository import get_active_windows_now
from api.infrastructure.balance_repository import ensure_snapshot, increment_assignment
from api.infrastructure.assignment_repository import (
    create_assignment, is_conversation_assigned, get_assignment_for_conversation,
)
from api.infrastructure.especialist_repository import get_especialists
from api.shared.logger import get_logger
from wdd import WorkloadEngine, PoolMember, CaseItem

logger = get_logger("dispatcher")

# Tags (case-insensitive substring match) that force re-assignment.
_NEW_CASE_TAGS: frozenset[str] = frozenset({"nuevo caso", "caso nuevo"})


def _is_new_case(email: Email) -> bool:
    """Return True if the email carries a tag that forces redistribution."""
    tags_lower = (email.tags or "").lower()
    return any(tag in tags_lower for tag in _NEW_CASE_TAGS)


# ---------------------------------------------------------------------------
# Helpers: ORM → Engine dataclasses
# ---------------------------------------------------------------------------

def _snapshot_to_pool_member(
    window: WorkWindow,
    snapshot: BalanceSnapshot,
    especialist_code: str,
) -> PoolMember:
    return PoolMember(
        code=especialist_code,
        load_percentage=window.load_percentage,
        cases_assigned=snapshot.cases_assigned,
        deficit=-snapshot.balance,
        last_updated=snapshot.updated_at,
    )


def _email_to_case(email: Email, level: int | None = None) -> CaseItem:
    return CaseItem(id=str(email.id), level=level)


# ---------------------------------------------------------------------------
# Pool builder
# ---------------------------------------------------------------------------

async def _build_pool(
    session: AsyncSession,
    application_code: str,
    level: int,
    now: datetime,
) -> tuple[list[WorkWindow], dict[str, float]]:
    active_windows = await get_active_windows_now(session, application_code, now)
    if not active_windows:
        return [], {}

    level_specialists = await get_especialists(session, level=level, active_only=True)
    level_ids = {s.id for s in level_specialists}
    primary = [w for w in active_windows if w.especialist_id in level_ids]

    if primary:
        id_to_code = {s.id: s.code for s in level_specialists}
        pcts = WorkloadEngine.compute_load_percentages(
            [PoolMember(code=id_to_code[w.especialist_id], load_percentage=w.load_percentage) for w in primary]
        )
        return primary, pcts

    all_specialists = await get_especialists(session, active_only=True)
    overflow_ids = {s.id for s in all_specialists}
    overflow = [w for w in active_windows if w.especialist_id in overflow_ids]

    if overflow:
        logger.info(
            "Primary pool empty for level=%d app=%s, using overflow (%d specialists)",
            level, application_code, len(overflow),
        )
        id_to_code = {s.id: s.code for s in all_specialists}
        pcts = WorkloadEngine.compute_load_percentages(
            [PoolMember(code=id_to_code[w.especialist_id], load_percentage=w.load_percentage) for w in overflow]
        )
        return overflow, pcts

    return [], {}


# ---------------------------------------------------------------------------
# Classifier: separate conversations into assign / redirect buckets
# ---------------------------------------------------------------------------

async def _classify_conversations(
    session: AsyncSession,
    conversations: list[Email],
    application_code: str,
) -> tuple[dict[int, list[Email]], list[Email]]:
    """Group conversations by level."""
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
            "%d conversations have no folder_config for app=%s",
            len(no_level), application_code,
        )
    return by_level, no_level


async def _route_conversations(
    session: AsyncSession,
    convs: list[Email],
    application_code: str,
) -> tuple[list[Email], list[Email], list[dict]]:
    """
    For each conversation decide its fate:

    Returns:
        to_assign   — new or carrying a new-case tag (go through WDD engine)
        queued      — already assigned, no new-case tag, but no specialist folder found
        to_redirect — already assigned, no new-case tag, has a target specialist folder
                      [{thread_id, especialist_id, target_folder, subject, sender_email}]
    """
    to_assign: list[Email] = []
    to_redirect: list[dict] = []
    queued: list[Email] = []

    for conv in convs:
        already_assigned = await is_conversation_assigned(session, conv.id)

        if not already_assigned:
            to_assign.append(conv)
            continue

        if _is_new_case(conv):
            logger.info(
                "New-case tag detected on already-assigned conv=%s — queuing for re-assignment",
                conv.id,
            )
            to_assign.append(conv)
            continue

        # Already assigned, no new-case tag → redirect to specialist's folder
        assignment = await get_assignment_for_conversation(session, conv.id)
        if not assignment:
            queued.append(conv)
            continue

        target_folder = await get_folder_for_specialist(
            session, application_code, assignment.especialist_id,
        )
        if not target_folder:
            logger.warning(
                "No analyst folder configured for especialist_id=%s app=%s — queuing conv=%s",
                assignment.especialist_id, application_code, conv.id,
            )
            queued.append(conv)
            continue

        to_redirect.append({
            "thread_id": str(conv.id),
            "conversation_id": conv.conversation_id,   # Outlook thread id (for the agent)
            "source_folder": conv.folder,              # current Outlook folder to navigate to
            "especialist_id": str(assignment.especialist_id),
            "target_folder": target_folder,            # exact folder name to move to
            "subject": conv.subject,
            "sender_email": conv.sender_email,
        })

    return to_assign, queued, to_redirect


# ---------------------------------------------------------------------------
# Persist engine results → DB
# ---------------------------------------------------------------------------

async def _persist_assignments(
    session: AsyncSession,
    report_assigned: list,
    application_code: str,
    level: int,
    code_to_window: dict[str, WorkWindow],
    code_to_id: dict[str, uuid.UUID],
    snapshots: dict[str, BalanceSnapshot],
    load_pcts: dict[str, float],
) -> list[dict]:
    total_existing = sum(s.cases_assigned for s in snapshots.values())
    results: list[dict] = []

    for ar in report_assigned:
        window = code_to_window[ar.specialist_code]
        snap = snapshots[ar.specialist_code]

        await create_assignment(
            session,
            thread_id=uuid.UUID(ar.case_id),
            especialist_id=code_to_id[ar.specialist_code],
            application_code=application_code,
            level=level,
            work_window_id=window.id,
        )

        total_existing += 1
        await increment_assignment(
            session,
            snapshot=snap,
            total_cases_in_pool=total_existing,
            load_percentage=load_pcts.get(ar.specialist_code, 0),
        )

        for other_code, other_snap in snapshots.items():
            if other_code != ar.specialist_code:
                pct = load_pcts.get(other_code, 0)
                other_snap.expected_cases = Decimal(str(total_existing * pct / 100))
                other_snap.balance = Decimal(str(other_snap.cases_assigned)) - other_snap.expected_cases

        results.append({
            "thread_id": ar.case_id,
            "especialist_id": str(code_to_id[ar.specialist_code]),
            "level": level,
            "work_window_id": str(window.id),
        })

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def dispatch(
    session: AsyncSession,
    conversations: list[Email],
    application_code: str,
    now: datetime | None = None,
) -> dict:
    """Main dispatch entry point. Classifies, routes, and assigns via WDD."""
    if now is None:
        now = datetime.now(timezone.utc)

    by_level, no_level = await _classify_conversations(session, conversations, application_code)

    all_assignments: list[dict] = []
    all_redirects: list[dict] = []
    queued_count = len(no_level)

    for level in sorted(by_level.keys()):
        convs = by_level[level]

        to_assign, queued, to_redirect = await _route_conversations(session, convs, application_code)
        all_redirects.extend(to_redirect)
        queued_count += len(queued)

        if not to_assign:
            continue

        windows, load_pcts = await _build_pool(session, application_code, level, now)
        if not windows:
            logger.warning(
                "No active pool for level=%d app=%s at %s, queuing %d",
                level, application_code, now.isoformat(), len(to_assign),
            )
            queued_count += len(to_assign)
            continue

        all_specialists = await get_especialists(session, active_only=True)
        id_to_code = {s.id: s.code for s in all_specialists}
        code_to_id = {s.code: s.id for s in all_specialists}
        code_to_window = {id_to_code[w.especialist_id]: w for w in windows}

        snapshots: dict[str, BalanceSnapshot] = {}
        for w in windows:
            code = id_to_code[w.especialist_id]
            snapshots[code] = await ensure_snapshot(
                session,
                especialist_id=w.especialist_id,
                application_code=application_code,
                work_window_id=w.id,
            )

        pool = [_snapshot_to_pool_member(code_to_window[code], snap, code) for code, snap in snapshots.items()]
        cases = [_email_to_case(c, level) for c in to_assign]

        report = WorkloadEngine.assign(pool, cases)

        level_results = await _persist_assignments(
            session, report.assigned, application_code, level,
            code_to_window, code_to_id, snapshots, load_pcts,
        )
        all_assignments.extend(level_results)
        queued_count += report.total_queued

    await session.commit()

    logger.info(
        "Dispatch complete: app=%s assigned=%d redirected=%d queued=%d",
        application_code, len(all_assignments), len(all_redirects), queued_count,
    )

    return {
        "status": "ok",
        "total_assigned": len(all_assignments),
        "total_redirected": len(all_redirects),
        "queued": queued_count,
        "assignments": all_assignments,
        "redirects": all_redirects,
    }


async def dispatch_level(
    session: AsyncSession,
    application_code: str,
    level: int,
    now: datetime | None = None,
) -> dict:
    """Dispatch conversations for a specific level."""
    if now is None:
        now = datetime.now(timezone.utc)

    folders = await get_folders_for_level(session, application_code, level)
    if not folders:
        return {
            "status": "ok", "level": level, "folders_used": [],
            "total_assigned": 0, "total_redirected": 0, "queued": 0,
            "assignments": [], "redirects": [],
            "message": f"No folders configured for level {level} in this application",
        }

    all_conversations: list[Email] = []
    for folder in folders:
        convs = await get_conversations(session, app=application_code, folder=folder, limit=10000, offset=0)
        all_conversations.extend(convs)

    to_assign, queued, to_redirect = await _route_conversations(
        session, all_conversations, application_code,
    )

    if not to_assign:
        await session.commit()
        return {
            "status": "ok", "level": level, "folders_used": folders,
            "total_assigned": 0, "total_redirected": len(to_redirect),
            "queued": len(queued), "assignments": [], "redirects": to_redirect,
        }

    windows, load_pcts = await _build_pool(session, application_code, level, now)
    if not windows:
        logger.warning(
            "No active pool for level=%d app=%s at %s, queuing %d",
            level, application_code, now.isoformat(), len(to_assign),
        )
        await session.commit()
        return {
            "status": "ok", "level": level, "folders_used": folders,
            "total_assigned": 0, "total_redirected": len(to_redirect),
            "queued": len(queued) + len(to_assign),
            "assignments": [], "redirects": to_redirect,
        }

    all_specialists = await get_especialists(session, active_only=True)
    id_to_code = {s.id: s.code for s in all_specialists}
    code_to_id = {s.code: s.id for s in all_specialists}
    code_to_window = {id_to_code[w.especialist_id]: w for w in windows}

    snapshots: dict[str, BalanceSnapshot] = {}
    for w in windows:
        code = id_to_code[w.especialist_id]
        snapshots[code] = await ensure_snapshot(
            session,
            especialist_id=w.especialist_id,
            application_code=application_code,
            work_window_id=w.id,
        )

    pool = [_snapshot_to_pool_member(code_to_window[code], snap, code) for code, snap in snapshots.items()]
    cases = [_email_to_case(c, level) for c in to_assign]

    report = WorkloadEngine.assign(pool, cases)

    level_results = await _persist_assignments(
        session, report.assigned, application_code, level,
        code_to_window, code_to_id, snapshots, load_pcts,
    )

    await session.commit()

    logger.info(
        "Dispatch level=%d complete: app=%s assigned=%d redirected=%d queued=%d",
        level, application_code, len(level_results), len(to_redirect), len(queued) + report.total_queued,
    )

    return {
        "status": "ok",
        "level": level,
        "folders_used": folders,
        "total_assigned": len(level_results),
        "total_redirected": len(to_redirect),
        "queued": len(queued) + report.total_queued,
        "assignments": level_results,
        "redirects": to_redirect,
    }
