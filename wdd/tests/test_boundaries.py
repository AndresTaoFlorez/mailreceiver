"""
Tests de condiciones de borde (boundary conditions).

Cada test corresponde a una fila de la seccion 8 de ALGORITHM.md.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from wdd import WorkloadEngine, PoolMember, CaseItem
from wdd.tests.mock_data import make_cases


class TestBoundaryConditions:
    """Seccion 8 de ALGORITHM.md — cada caso borde documentado."""

    def test_empty_case_list(self, pool_mixed):
        """Lista de casos vacia → reporte vacio, sin asignaciones ni cola."""
        report = WorkloadEngine.assign(pool_mixed, [])

        assert report.total_assigned == 0
        assert report.total_queued == 0
        assert report.assigned == []
        assert report.queued == []

    def test_empty_pool(self):
        """Pool vacio → todos los casos van a la cola."""
        cases = make_cases(5)
        report = WorkloadEngine.assign([], cases)

        assert report.total_assigned == 0
        assert report.total_queued == 5
        assert report.queued == [f"CONV-{i:04d}" for i in range(1, 6)]

    def test_both_empty(self):
        """Pool vacio + lista vacia → reporte completamente vacio."""
        report = WorkloadEngine.assign([], [])

        assert report.total_assigned == 0
        assert report.total_queued == 0

    def test_single_pool_member(self, pool_single):
        """Un solo miembro recibe todos los casos."""
        cases = make_cases(7)
        report = WorkloadEngine.assign(pool_single, cases)

        assert report.total_assigned == 7
        assert all(a.specialist_code == "SOLO" for a in report.assigned)

    def test_fixed_sum_exceeds_100(self):
        """Fijos suman >100 → auto recibe 0%, pero los fijos conservan su valor."""
        pool = [
            PoolMember(code="A", load_percentage=70, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="B", load_percentage=50, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="C", load_percentage=None, last_updated=datetime(2026, 1, 1)),
        ]
        pcts = WorkloadEngine.compute_load_percentages(pool)

        assert pcts["A"] == 70.0
        assert pcts["B"] == 50.0
        assert pcts["C"] == 0.0

    def test_all_null_percentages(self, pool_equal):
        """Todos con load_percentage=None → reparto equitativo."""
        pcts = WorkloadEngine.compute_load_percentages(pool_equal)

        expected = 100.0 / 3
        for code in ("A", "B", "C"):
            assert pcts[code] == pytest.approx(expected)

    def test_zero_deficit_tiebreak_by_timestamp(self):
        """Todos en deficit 0 → el que tiene last_updated mas antiguo gana."""
        pool = [
            PoolMember(code="NEWEST", load_percentage=50, last_updated=datetime(2026, 1, 3)),
            PoolMember(code="OLDEST", load_percentage=50, last_updated=datetime(2026, 1, 1)),
        ]
        cases = [CaseItem(id="first")]
        report = WorkloadEngine.assign(pool, cases)

        assert report.assigned[0].specialist_code == "OLDEST"

    def test_single_case(self, pool_mixed):
        """Un solo caso → se asigna al miembro con mayor deficit (o tiebreak)."""
        cases = [CaseItem(id="only")]
        report = WorkloadEngine.assign(pool_mixed, cases)

        assert report.total_assigned == 1
        assert report.total_queued == 0


class TestAssignmentIntegrity:
    """Verifica que el reporte es consistente internamente."""

    def test_no_duplicate_case_ids(self, pool_mixed, cases_100):
        """Cada caso aparece exactamente una vez en el reporte."""
        report = WorkloadEngine.assign(pool_mixed, cases_100)

        assigned_ids = [a.case_id for a in report.assigned]
        assert len(assigned_ids) == len(set(assigned_ids))

    def test_assigned_plus_queued_equals_input(self):
        """assigned + queued == total de casos de entrada."""
        pool = [PoolMember(code="A", load_percentage=100)]
        cases = make_cases(5)
        report = WorkloadEngine.assign(pool, cases)

        assert report.total_assigned + report.total_queued == 5

    def test_queued_ids_match_input_when_pool_empty(self):
        """Con pool vacio, los IDs en cola coinciden con los de entrada."""
        cases = make_cases(3)
        report = WorkloadEngine.assign([], cases)

        assert set(report.queued) == {c.id for c in cases}

    def test_cases_assigned_increments_correctly(self, pool_single):
        """new_cases_assigned se incrementa secuencialmente."""
        cases = make_cases(5)
        report = WorkloadEngine.assign(pool_single, cases)

        for i, a in enumerate(report.assigned, start=1):
            assert a.new_cases_assigned == i
