"""
Tests del camino feliz (happy path) para WorkloadEngine.

Verifica que el algoritmo distribuye correctamente bajo condiciones normales.
"""

from collections import Counter

import pytest

from wdd import WorkloadEngine, PoolMember, CaseItem
from wdd.tests.mock_data import make_cases


# ---------------------------------------------------------------------------
# compute_load_percentages
# ---------------------------------------------------------------------------

class TestComputeLoadPercentages:
    """Verifica la resolucion de porcentajes efectivos."""

    def test_all_fixed(self):
        """Miembros con % explicito conservan su valor."""
        members = [
            PoolMember(code="A", load_percentage=60),
            PoolMember(code="B", load_percentage=40),
        ]
        pcts = WorkloadEngine.compute_load_percentages(members)
        assert pcts == {"A": 60.0, "B": 40.0}

    def test_all_auto(self, pool_equal):
        """Miembros sin % se reparten 100% equitativamente."""
        pcts = WorkloadEngine.compute_load_percentages(pool_equal)
        for code in ("A", "B", "C"):
            assert pcts[code] == pytest.approx(100 / 3)

    def test_mixed(self, pool_mixed):
        """60% fijo + 2 auto = 20% cada uno."""
        pcts = WorkloadEngine.compute_load_percentages(pool_mixed)
        assert pcts["SP-01"] == 60.0
        assert pcts["SP-02"] == 20.0
        assert pcts["SP-03"] == 20.0

    def test_fixed_exceeds_100(self):
        """Si los fijos suman >100, los auto reciben 0%."""
        members = [
            PoolMember(code="A", load_percentage=70),
            PoolMember(code="B", load_percentage=50),
            PoolMember(code="C", load_percentage=None),
        ]
        pcts = WorkloadEngine.compute_load_percentages(members)
        assert pcts["A"] == 70.0
        assert pcts["B"] == 50.0
        assert pcts["C"] == 0.0


# ---------------------------------------------------------------------------
# assign — happy path
# ---------------------------------------------------------------------------

class TestAssignHappyPath:
    """Distribucion correcta bajo condiciones normales."""

    def test_proportional_distribution(self, pool_mixed, cases_10):
        """60/20/20 split con 10 casos → 6/2/2."""
        report = WorkloadEngine.assign(pool_mixed, cases_10)

        counts = Counter(a.specialist_code for a in report.assigned)
        assert counts["SP-01"] == 6
        assert counts["SP-02"] == 2
        assert counts["SP-03"] == 2

    def test_equal_distribution(self, pool_equal):
        """3 especialistas iguales + 9 casos → 3 cada uno."""
        cases = make_cases(9)
        report = WorkloadEngine.assign(pool_equal, cases)

        counts = Counter(a.specialist_code for a in report.assigned)
        assert counts["A"] == 3
        assert counts["B"] == 3
        assert counts["C"] == 3

    def test_all_cases_assigned(self, pool_mixed, cases_100):
        """Todos los casos se asignan, ninguno queda en cola."""
        report = WorkloadEngine.assign(pool_mixed, cases_100)

        assert report.total_assigned == 100
        assert report.total_queued == 0

    def test_case_ids_preserved(self, pool_single):
        """Los IDs de los casos se conservan en el reporte."""
        cases = [CaseItem(id="X-1"), CaseItem(id="X-2"), CaseItem(id="X-3")]
        report = WorkloadEngine.assign(pool_single, cases)

        assigned_ids = [a.case_id for a in report.assigned]
        assert assigned_ids == ["X-1", "X-2", "X-3"]

    def test_respects_existing_deficit(self, pool_with_history):
        """SP-01 tiene deficit positivo (+2, se le deben), debe recibir los primeros casos."""
        cases = make_cases(4)
        report = WorkloadEngine.assign(pool_with_history, cases)

        # Los primeros casos van a SP-01 porque tiene el mayor deficit (system owes them)
        first_two = [report.assigned[0].specialist_code, report.assigned[1].specialist_code]
        assert first_two.count("SP-01") >= 1

    @pytest.mark.parametrize("n_cases", [10, 50, 100])
    def test_large_batch_converges(self, pool_mixed, n_cases):
        """Con suficientes casos, la distribucion se acerca al % configurado."""
        cases = make_cases(n_cases)
        report = WorkloadEngine.assign(pool_mixed, cases)

        counts = Counter(a.specialist_code for a in report.assigned)
        # SP-01 (60%) debe tener entre 55%-65% del total
        sp01_ratio = counts["SP-01"] / n_cases
        assert 0.55 <= sp01_ratio <= 0.65
