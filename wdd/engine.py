"""
wdd/engine.py — Weighted Deficit Dispatch (WDD) assignment algorithm.

Pure Python. No I/O, no DB, no async. Receives data in, returns decisions out.

Deficit convention:
    deficit(i) = ideal(i) - received(i)
    Positive → system owes the specialist more cases (highest priority)
    Negative → specialist has received more than their share

Usage:
    from wdd import WorkloadEngine, PoolMember, CaseItem

    pool = [PoolMember("ana", load_percentage=60), PoolMember("bob")]
    cases = [CaseItem("c1", level=1), CaseItem("c2", level=1)]
    report = WorkloadEngine.assign(pool, cases)

Escalations:
    from wdd import WorkloadEngine, EscalationEvent

    WorkloadEngine.escalate(pool, EscalationEvent(
        case_id="c1", source_code="ana", target_code="bob",
    ))
"""

from __future__ import annotations

from decimal import Decimal

from wdd.models import PoolMember, CaseItem, EscalationEvent, AssignmentResult, DispatchReport


class WorkloadEngine:
    """Stateless workload distributor using deficit-first progressive drip.

    Each call to ``assign`` is independent — pass the current pool state and
    unassigned cases, get back a deterministic list of assignment decisions.

    Deficit = ideal - received. Positive deficit = system owes the specialist.
    The specialist with the highest deficit gets the next case.
    """

    @staticmethod
    def compute_load_percentages(members: list[PoolMember]) -> dict[str, float]:
        """Compute effective load % for each pool member.

        Members with ``load_percentage`` set keep that value.
        Members with ``None`` split the remaining % equally.

        Returns a dict mapping member code → effective percentage.
        """
        fixed: list[tuple[str, float]] = []
        auto: list[str] = []

        for m in members:
            if m.load_percentage is not None:
                fixed.append((m.code, m.load_percentage))
            else:
                auto.append(m.code)

        fixed_total = sum(pct for _, pct in fixed)
        remaining = max(0.0, 100.0 - fixed_total)
        auto_pct = remaining / len(auto) if auto else 0.0

        result: dict[str, float] = {}
        for code, pct in fixed:
            result[code] = pct
        for code in auto:
            result[code] = auto_pct

        return result

    @staticmethod
    def assign(
        pool: list[PoolMember],
        cases: list[CaseItem],
    ) -> DispatchReport:
        """Run the deficit-first progressive drip algorithm.

        For each case (in order), assigns it to the pool member with the
        highest deficit (i.e., the specialist who is owed the most work).
        Ties are broken by ``last_updated`` (least recent wins).

        After each assignment, all members' expected cases and deficits are
        recalculated so the next pick reflects the updated state.

        Args:
            pool: Current state of available specialists. Must not be empty
                  unless ``cases`` is also empty.
            cases: Unassigned cases to distribute.

        Returns:
            DispatchReport with assignment decisions.
        """
        report = DispatchReport()

        if not cases:
            return report

        if not pool:
            report.queued = [c.id for c in cases]
            return report

        # Compute effective percentages and stamp them on members
        pcts = WorkloadEngine.compute_load_percentages(pool)
        for m in pool:
            m._effective_pct = pcts[m.code]

        # Running total of cases in this pool (existing assigned + new ones)
        total_cases = sum(m.cases_assigned for m in pool)

        for case in cases:
            # Sort: highest deficit first (most owed), then least recently updated
            pool_order = sorted(
                pool,
                key=lambda m: (-float(m.deficit), str(m.last_updated)),
            )

            chosen = pool_order[0]
            total_cases += 1

            # Update the chosen member
            chosen.cases_assigned += 1
            chosen._expected = Decimal(str(total_cases * chosen._effective_pct / 100))
            chosen.deficit = chosen._expected - Decimal(str(chosen.cases_assigned))

            # Recalculate expected/deficit for everyone else
            for other in pool:
                if other.code != chosen.code:
                    other._expected = Decimal(str(total_cases * other._effective_pct / 100))
                    other.deficit = other._expected - Decimal(str(other.cases_assigned))

            report.assigned.append(AssignmentResult(
                case_id=case.id,
                specialist_code=chosen.code,
                new_deficit=chosen.deficit,
                new_cases_assigned=chosen.cases_assigned,
                new_expected=chosen._expected,
            ))

        return report

    @staticmethod
    def escalate(
        pool: list[PoolMember],
        event: EscalationEvent,
    ) -> None:
        """Apply an escalation/transfer event to the pool deficits.

        When source escalates a case to target:
        - source.deficit += 1  (the case shouldn't count against them, system owes less)
        - target.deficit -= 1  (they took on extra work, they're now more ahead)

        This is an in-place mutation of the pool members.

        Raises:
            ValueError: if source_code or target_code not found in pool.
        """
        by_code = {m.code: m for m in pool}

        if event.source_code not in by_code:
            raise ValueError(f"Source specialist '{event.source_code}' not in pool")
        if event.target_code not in by_code:
            raise ValueError(f"Target specialist '{event.target_code}' not in pool")

        source = by_code[event.source_code]
        target = by_code[event.target_code]

        # Source gave away a case: they effectively received one less
        source.deficit += 1
        source.cases_assigned -= 1

        # Target took on a case: they effectively received one more
        target.deficit -= 1
        target.cases_assigned += 1
