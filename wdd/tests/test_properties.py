"""
Tests de propiedades del algoritmo (ALGORITHM.md seccion 4).

Verifican garantias que deben cumplirse sin importar los datos de entrada:
determinismo, convergencia, starvation freedom, order independence.
"""

from collections import Counter
from datetime import datetime
from decimal import Decimal

import pytest

from wdd import WorkloadEngine, PoolMember, CaseItem
from wdd.tests.mock_data import make_cases


class TestDeterminism:
    """Seccion 4.1 — Misma entrada → misma salida, siempre."""

    def test_identical_runs_produce_identical_output(self, pool_mixed):
        """Dos ejecuciones con los mismos datos dan el mismo resultado."""
        cases = make_cases(20)

        # Primera ejecucion
        pool_a = [
            PoolMember(code="SP-01", load_percentage=60, last_updated=datetime(2026, 1, 1, 8, 0)),
            PoolMember(code="SP-02", load_percentage=None, last_updated=datetime(2026, 1, 1, 8, 0)),
            PoolMember(code="SP-03", load_percentage=None, last_updated=datetime(2026, 1, 1, 8, 0)),
        ]
        report_a = WorkloadEngine.assign(pool_a, cases)

        # Segunda ejecucion con datos identicos
        cases_b = make_cases(20)
        pool_b = [
            PoolMember(code="SP-01", load_percentage=60, last_updated=datetime(2026, 1, 1, 8, 0)),
            PoolMember(code="SP-02", load_percentage=None, last_updated=datetime(2026, 1, 1, 8, 0)),
            PoolMember(code="SP-03", load_percentage=None, last_updated=datetime(2026, 1, 1, 8, 0)),
        ]
        report_b = WorkloadEngine.assign(pool_b, cases_b)

        seq_a = [(a.case_id, a.specialist_code) for a in report_a.assigned]
        seq_b = [(a.case_id, a.specialist_code) for a in report_b.assigned]
        assert seq_a == seq_b


class TestConvergence:
    """Seccion 4.2 — El deficit converge hacia cero con suficientes casos."""

    @pytest.mark.parametrize("n_cases", [50, 200, 500])
    def test_deficits_near_zero_after_large_batch(self, n_cases):
        """Despues de muchos casos, todos los deficits estan cerca de cero."""
        pool = [
            PoolMember(code="A", load_percentage=50, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="B", load_percentage=30, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="C", load_percentage=20, last_updated=datetime(2026, 1, 1)),
        ]
        cases = make_cases(n_cases)
        report = WorkloadEngine.assign(pool, cases)

        # Despues del batch, todos los deficits deben estar en [-1, +1]
        for m in pool:
            assert abs(float(m.deficit)) <= 1.0, (
                f"{m.code}: deficit={m.deficit} after {n_cases} cases"
            )

    def test_distribution_matches_percentages(self):
        """La distribucion final se aproxima a los % configurados."""
        pool = [
            PoolMember(code="A", load_percentage=70, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="B", load_percentage=30, last_updated=datetime(2026, 1, 1)),
        ]
        cases = make_cases(100)
        report = WorkloadEngine.assign(pool, cases)

        counts = Counter(a.specialist_code for a in report.assigned)
        assert counts["A"] == 70
        assert counts["B"] == 30


class TestStarvationFreedom:
    """Seccion 4.3 — Ningun miembro con % >0 se queda sin casos."""

    def test_all_members_receive_at_least_one(self):
        """Con suficientes casos, todos reciben al menos uno."""
        pool = [
            PoolMember(code="BIG", load_percentage=90, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="SMALL", load_percentage=10, last_updated=datetime(2026, 1, 1)),
        ]
        cases = make_cases(20)
        report = WorkloadEngine.assign(pool, cases)

        codes = {a.specialist_code for a in report.assigned}
        assert "BIG" in codes
        assert "SMALL" in codes

    def test_minority_member_gets_cases(self):
        """Un miembro con solo 5% recibe casos en un batch de 100."""
        pool = [
            PoolMember(code="MAJORITY", load_percentage=95, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="MINORITY", load_percentage=5, last_updated=datetime(2026, 1, 1)),
        ]
        cases = make_cases(100)
        report = WorkloadEngine.assign(pool, cases)

        counts = Counter(a.specialist_code for a in report.assigned)
        assert counts["MINORITY"] == 5


class TestOrderIndependence:
    """Seccion 4.4 — El orden del pool no afecta la distribucion final."""

    def test_pool_order_does_not_affect_totals(self):
        """Reordenar el pool produce la misma distribucion total."""
        cases = make_cases(30)

        # Orden A
        pool_a = [
            PoolMember(code="X", load_percentage=60, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="Y", load_percentage=40, last_updated=datetime(2026, 1, 1)),
        ]
        report_a = WorkloadEngine.assign(pool_a, cases)

        # Orden B (invertido)
        cases_b = make_cases(30)
        pool_b = [
            PoolMember(code="Y", load_percentage=40, last_updated=datetime(2026, 1, 1)),
            PoolMember(code="X", load_percentage=60, last_updated=datetime(2026, 1, 1)),
        ]
        report_b = WorkloadEngine.assign(pool_b, cases_b)

        counts_a = Counter(a.specialist_code for a in report_a.assigned)
        counts_b = Counter(a.specialist_code for a in report_b.assigned)
        assert counts_a == counts_b
