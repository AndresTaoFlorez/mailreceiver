"""
Tests basados en escenarios realistas de mock_data.py.

Cada escenario simula una condicion de produccion: inicio de turno,
mitad de turno con historial, analista tardio, estres, etc.
"""

from collections import Counter

import pytest

from wdd import WorkloadEngine
from wdd.tests.mock_data import SCENARIOS


# ---------------------------------------------------------------------------
# Parametrized: all scenarios with expected_counts
# ---------------------------------------------------------------------------

_COUNTED = [
    (name, s) for name, s in SCENARIOS.items()
    if "expected_counts" in s
]


@pytest.mark.parametrize(
    "name,scenario",
    _COUNTED,
    ids=[name for name, _ in _COUNTED],
)
def test_scenario_distribution(name, scenario):
    """Verifica que la distribucion final coincide con expected_counts."""
    report = WorkloadEngine.assign(scenario["pool"], scenario["cases"])
    counts = Counter(a.specialist_code for a in report.assigned)

    for code, expected in scenario["expected_counts"].items():
        assert counts[code] == expected, (
            f"Scenario '{name}': {code} got {counts[code]}, expected {expected}"
        )


# ---------------------------------------------------------------------------
# Specific behavior tests
# ---------------------------------------------------------------------------

class TestQueueScenario:
    """Escenario sin pool: todos los casos van a cola."""

    def test_no_pool_queues_all(self):
        s = SCENARIOS["no_pool"]
        report = WorkloadEngine.assign(s["pool"], s["cases"])

        assert report.total_assigned == 0
        assert report.total_queued == s["expected_queued"]


class TestTiebreakScenario:
    """Empate de deficit: el timestamp mas antiguo gana."""

    def test_oldest_wins_tiebreak(self):
        s = SCENARIOS["tiebreak_by_timestamp"]
        report = WorkloadEngine.assign(s["pool"], s["cases"])

        assert report.assigned[0].specialist_code == s["expected_first"]


class TestLateJoiner:
    """Analista que se incorpora tarde con 0 casos."""

    def test_late_joiner_catches_up(self):
        s = SCENARIOS["late_joiner"]
        report = WorkloadEngine.assign(s["pool"], s["cases"])

        counts = Counter(a.specialist_code for a in report.assigned)
        # BORIS (0 casos previos) debe recibir mas que ANA (15 previos)
        assert counts["BORIS"] > counts["ANA"]


class TestMidshiftImbalanced:
    """Analista sobrecargado vs analista con deficit."""

    def test_deficit_gets_priority(self):
        s = SCENARIOS["midshift_imbalanced"]
        report = WorkloadEngine.assign(s["pool"], s["cases"])

        counts = Counter(a.specialist_code for a in report.assigned)
        # BORIS (deficit +3, system owes him) debe recibir mas casos que ANA (deficit -3, ahead)
        assert counts["BORIS"] > counts["ANA"]

        # Despues de 10 casos extra (50/50 split), los balances se acercan
        total_ana = 13 + counts["ANA"]
        total_boris = 7 + counts["BORIS"]
        diff = abs(total_ana - total_boris)
        assert diff <= 2  # diferencia maxima de 1-2 casos
