"""
infrastructure/balance_repository.py — CRUD for balance_snapshots.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import BalanceSnapshot
from api.shared.logger import get_logger

logger = get_logger("balance_repository")


async def get_snapshot(
    session: AsyncSession,
    especialist_id: uuid.UUID,
    work_window_id: uuid.UUID,
) -> BalanceSnapshot | None:
    q = (
        select(BalanceSnapshot)
        .where(BalanceSnapshot.especialist_id == especialist_id)
        .where(BalanceSnapshot.work_window_id == work_window_id)
    )
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def get_snapshots_for_window(
    session: AsyncSession,
    work_window_id: uuid.UUID,
) -> list[BalanceSnapshot]:
    q = (
        select(BalanceSnapshot)
        .where(BalanceSnapshot.work_window_id == work_window_id)
        .order_by(BalanceSnapshot.balance)
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_snapshots_for_app(
    session: AsyncSession,
    application_code: str,
) -> list[BalanceSnapshot]:
    q = (
        select(BalanceSnapshot)
        .where(BalanceSnapshot.application_code == application_code)
        .order_by(BalanceSnapshot.updated_at.desc())
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def ensure_snapshot(
    session: AsyncSession,
    especialist_id: uuid.UUID,
    application_code: str,
    work_window_id: uuid.UUID,
    initial_balance: Decimal = Decimal("0"),
    inherited_from: uuid.UUID | None = None,
) -> BalanceSnapshot:
    """Get or create a balance snapshot for the given specialist+window."""
    existing = await get_snapshot(session, especialist_id, work_window_id)
    if existing:
        return existing

    row = BalanceSnapshot(
        id=uuid.uuid4(),
        especialist_id=especialist_id,
        application_code=application_code,
        work_window_id=work_window_id,
        cases_assigned=0,
        expected_cases=Decimal("0"),
        balance=initial_balance,
        inherited_from=inherited_from,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "Created balance_snapshot especialist_id=%s window=%s initial_balance=%s",
        especialist_id, work_window_id, initial_balance,
    )
    return row


async def increment_assignment(
    session: AsyncSession,
    snapshot: BalanceSnapshot,
    total_cases_in_pool: int,
    load_percentage: float,
) -> None:
    """Record one assignment: increment cases_assigned, recalculate expected and balance."""
    snapshot.cases_assigned += 1
    snapshot.expected_cases = Decimal(str(total_cases_in_pool * load_percentage / 100))
    snapshot.balance = Decimal(str(snapshot.cases_assigned)) - snapshot.expected_cases
    snapshot.updated_at = datetime.now(timezone.utc)
    await session.flush()


async def reset_snapshot(
    session: AsyncSession,
    work_window_id: uuid.UUID,
) -> int:
    """Reset all snapshots for a window to zero. Returns count of reset snapshots."""
    snapshots = await get_snapshots_for_window(session, work_window_id)
    now = datetime.now(timezone.utc)
    for s in snapshots:
        s.cases_assigned = 0
        s.expected_cases = Decimal("0")
        s.balance = Decimal("0")
        s.last_reset_at = now
        s.updated_at = now
    await session.flush()
    logger.info("Reset %d snapshots for window=%s", len(snapshots), work_window_id)
    return len(snapshots)
