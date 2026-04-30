"""
Tests para el mecanismo de escalacion/traspaso del WDD.

Verifica que las escalaciones ajustan correctamente el deficit
de los especialistas involucrados.
"""

from collections import Counter
from datetime import datetime
from decimal import Decimal

import pytest

from wdd import WorkloadEngine, PoolMember, CaseItem, EscalationEvent
from wdd.tests.mock_data import make_pool, make_cases, T_0800, T_1000


class TestEscalation:
    """Escalacion: source entrega caso a target."""

    def test_escalation_adjusts_deficit(self):
        """Escalar un caso incrementa deficit de source y decrementa el de target."""
        pool = make_pool(
            ("ANA",   50, 5, 0, T_0800),
            ("BORIS", 50, 5, 0, T_0800),
        )

        WorkloadEngine.escalate(pool, EscalationEvent(
            case_id="CONV-001",
            source_code="ANA",
            target_code="BORIS",
        ))

        ana = next(m for m in pool if m.code == "ANA")
        boris = next(m for m in pool if m.code == "BORIS")

        # ANA gave away a case: deficit goes up (system owes her more)
        assert ana.deficit == Decimal("1")
        assert ana.cases_assigned == 4

        # BORIS took on a case: deficit goes down (he's more ahead)
        assert boris.deficit == Decimal("-1")
        assert boris.cases_assigned == 6

    def test_escalation_affects_next_assignment(self):
        """Despues de escalar, el source tiene prioridad en la siguiente ronda."""
        pool = make_pool(
            ("ANA",   50, 5, 0, T_0800),
            ("BORIS", 50, 5, 0, T_0800),
        )

        # ANA escala un caso a BORIS
        WorkloadEngine.escalate(pool, EscalationEvent(
            case_id="CONV-001",
            source_code="ANA",
            target_code="BORIS",
        ))

        # Ahora ANA tiene deficit +1, BORIS -1
        # El siguiente caso debe ir a ANA (mayor deficit)
        cases = [CaseItem(id="NEXT-001")]
        report = WorkloadEngine.assign(pool, cases)

        assert report.assigned[0].specialist_code == "ANA"

    def test_multiple_escalations_accumulate(self):
        """Multiples escalaciones acumulan deficit correctamente."""
        pool = make_pool(
            ("ANA",   50, 10, 0, T_0800),
            ("BORIS", 50, 10, 0, T_0800),
        )

        for i in range(3):
            WorkloadEngine.escalate(pool, EscalationEvent(
                case_id=f"ESC-{i}",
                source_code="ANA",
                target_code="BORIS",
            ))

        ana = next(m for m in pool if m.code == "ANA")
        boris = next(m for m in pool if m.code == "BORIS")

        assert ana.deficit == Decimal("3")
        assert ana.cases_assigned == 7
        assert boris.deficit == Decimal("-3")
        assert boris.cases_assigned == 13

    def test_escalation_then_batch_rebalances(self):
        """Despues de una escalacion, un batch grande restaura el equilibrio."""
        pool = make_pool(
            ("ANA",   50, 10, 0, T_0800),
            ("BORIS", 50, 10, 0, T_0800),
        )

        # BORIS escala 3 casos a ANA
        for i in range(3):
            WorkloadEngine.escalate(pool, EscalationEvent(
                case_id=f"ESC-{i}",
                source_code="BORIS",
                target_code="ANA",
            ))

        # BORIS now has deficit +3 (owed), ANA has deficit -3 (ahead)
        # Assign 20 new cases — BORIS should get more to compensate
        cases = make_cases(20)
        report = WorkloadEngine.assign(pool, cases)

        counts = Counter(a.specialist_code for a in report.assigned)
        assert counts["BORIS"] > counts["ANA"]

    def test_escalation_unknown_source_raises(self):
        """Escalar con source desconocido lanza ValueError."""
        pool = make_pool(("ANA", 50, 5, 0, T_0800),)

        with pytest.raises(ValueError, match="Source specialist 'GHOST'"):
            WorkloadEngine.escalate(pool, EscalationEvent(
                case_id="X", source_code="GHOST", target_code="ANA",
            ))

    def test_escalation_unknown_target_raises(self):
        """Escalar con target desconocido lanza ValueError."""
        pool = make_pool(("ANA", 50, 5, 0, T_0800),)

        with pytest.raises(ValueError, match="Target specialist 'GHOST'"):
            WorkloadEngine.escalate(pool, EscalationEvent(
                case_id="X", source_code="ANA", target_code="GHOST",
            ))

    def test_bidirectional_escalation_cancels_out(self):
        """ANA escala a BORIS, luego BORIS escala a ANA → deficit vuelve a 0."""
        pool = make_pool(
            ("ANA",   50, 5, 0, T_0800),
            ("BORIS", 50, 5, 0, T_0800),
        )

        WorkloadEngine.escalate(pool, EscalationEvent(
            case_id="E1", source_code="ANA", target_code="BORIS",
        ))
        WorkloadEngine.escalate(pool, EscalationEvent(
            case_id="E2", source_code="BORIS", target_code="ANA",
        ))

        ana = next(m for m in pool if m.code == "ANA")
        boris = next(m for m in pool if m.code == "BORIS")

        assert ana.deficit == Decimal("0")
        assert boris.deficit == Decimal("0")
        assert ana.cases_assigned == 5
        assert boris.cases_assigned == 5
