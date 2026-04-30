"""
wdd/tests/mock_data.py — Pre-built datasets for testing the WDD algorithm.

Each scenario is a dict with 'pool' and 'cases' keys ready to unpack into
WorkloadEngine.assign(). Scenarios simulate realistic production conditions.

Usage:
    from wdd.tests.mock_data import SCENARIOS, make_pool, make_cases

    pool, cases = SCENARIOS["turno_manana"]["pool"], SCENARIOS["turno_manana"]["cases"]
    report = WorkloadEngine.assign(pool, cases)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from wdd.models import PoolMember, CaseItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pool(*specs: tuple) -> list[PoolMember]:
    """Build a pool from compact tuples.

    Each tuple: (code, load_pct, cases_assigned, deficit, last_updated)
    load_pct can be None for auto-split.
    deficit: positive = system owes specialist, negative = specialist is ahead.
    """
    return [
        PoolMember(
            code=code,
            load_percentage=pct,
            cases_assigned=assigned,
            deficit=Decimal(str(deficit)),
            last_updated=ts,
        )
        for code, pct, assigned, deficit, ts in specs
    ]


def make_cases(n: int, level: int = 1, prefix: str = "CONV") -> list[CaseItem]:
    """Generate n cases with sequential IDs."""
    return [CaseItem(id=f"{prefix}-{i:04d}", level=level) for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# Realistic specialist profiles
# ---------------------------------------------------------------------------

# Timestamps for a typical workday
T_0800 = datetime(2026, 4, 28, 8, 0)
T_0830 = datetime(2026, 4, 28, 8, 30)
T_0900 = datetime(2026, 4, 28, 9, 0)
T_1000 = datetime(2026, 4, 28, 10, 0)
T_1100 = datetime(2026, 4, 28, 11, 0)
T_1400 = datetime(2026, 4, 28, 14, 0)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict] = {

    # --- Fresh start: nobody has any cases yet ---

    "fresh_3_mixed": {
        "description": "Inicio de turno, 3 analistas, cargas 50/30/20, sin historial.",
        "pool": make_pool(
            ("ANA",   50,  0, 0, T_0800),
            ("BORIS", 30,  0, 0, T_0800),
            ("CARLA", 20,  0, 0, T_0800),
        ),
        "cases": make_cases(20, level=1),
        "expected_counts": {"ANA": 10, "BORIS": 6, "CARLA": 4},
    },

    "fresh_5_equal": {
        "description": "5 analistas sin porcentaje fijo → reparto equitativo.",
        "pool": make_pool(
            ("SP-01", None, 0, 0, T_0800),
            ("SP-02", None, 0, 0, T_0800),
            ("SP-03", None, 0, 0, T_0800),
            ("SP-04", None, 0, 0, T_0800),
            ("SP-05", None, 0, 0, T_0800),
        ),
        "cases": make_cases(25, level=1),
        "expected_counts": {"SP-01": 5, "SP-02": 5, "SP-03": 5, "SP-04": 5, "SP-05": 5},
    },

    # --- Mid-shift: analysts have accumulated history ---

    "midshift_balanced": {
        "description": "Mitad de turno, deficits cercanos a cero. Nuevos casos se reparten normal.",
        "pool": make_pool(
            # deficit sign flipped: old balance +0.2 → deficit -0.2 (ahead)
            ("ANA",   60,  12, -0.2,  T_1000),
            # old balance -0.2 → deficit +0.2 (owed)
            ("BORIS", 40,   8,  0.2,  T_1000),
        ),
        "cases": make_cases(10, level=1),
        "expected_counts": {"ANA": 6, "BORIS": 4},
    },

    "midshift_imbalanced": {
        "description": "ANA esta sobrecargada (deficit -3), BORIS tiene deficit (+3). Los proximos casos compensan.",
        "pool": make_pool(
            # old balance +3 → deficit -3 (ahead/surplus)
            ("ANA",   50, 13, -3.0, T_1100),
            # old balance -3 → deficit +3 (owed)
            ("BORIS", 50,  7,  3.0, T_1100),
        ),
        "cases": make_cases(10, level=1),
        # BORIS recibe mas para compensar su deficit
    },

    # --- Edge: one dominant analyst ---

    "one_dominant": {
        "description": "Un analista con 80%, otro con 20%. 50 casos nivel 2.",
        "pool": make_pool(
            ("SENIOR", 80, 0, 0, T_0800),
            ("JUNIOR", 20, 0, 0, T_0800),
        ),
        "cases": make_cases(50, level=2),
        "expected_counts": {"SENIOR": 40, "JUNIOR": 10},
    },

    # --- Late joiner: analyst starts mid-batch with zero history ---

    "late_joiner": {
        "description": "ANA lleva 15 casos, BORIS se incorpora a mitad de turno con 0.",
        "pool": make_pool(
            ("ANA",   50, 15, 0, T_0800),
            ("BORIS", 50,  0, 0, T_1400),
        ),
        "cases": make_cases(10, level=1),
        # BORIS tiene deficit enorme → recibe la mayoria de los nuevos
    },

    # --- Stress: large batch ---

    "stress_200": {
        "description": "4 analistas, 200 casos. Verifica convergencia a escala.",
        "pool": make_pool(
            ("A", 40, 0, 0, T_0800),
            ("B", 30, 0, 0, T_0800),
            ("C", 20, 0, 0, T_0800),
            ("D", 10, 0, 0, T_0800),
        ),
        "cases": make_cases(200, level=1),
        "expected_counts": {"A": 80, "B": 60, "C": 40, "D": 20},
    },

    # --- Solo operator ---

    "solo": {
        "description": "Un unico analista disponible recibe todo.",
        "pool": make_pool(
            ("SOLO", 100, 0, 0, T_0800),
        ),
        "cases": make_cases(15, level=1),
        "expected_counts": {"SOLO": 15},
    },

    # --- Empty pool (queuing) ---

    "no_pool": {
        "description": "Sin analistas activos → todos los casos van a cola.",
        "pool": [],
        "cases": make_cases(8, level=1),
        "expected_queued": 8,
    },

    # --- Mixed levels ---

    "level_1_batch": {
        "description": "Lote exclusivo de nivel 1.",
        "pool": make_pool(
            ("L1-A", 60, 0, 0, T_0800),
            ("L1-B", 40, 0, 0, T_0800),
        ),
        "cases": make_cases(30, level=1, prefix="TUT"),
        "expected_counts": {"L1-A": 18, "L1-B": 12},
    },

    "level_2_batch": {
        "description": "Lote exclusivo de nivel 2.",
        "pool": make_pool(
            ("L2-A", 50, 0, 0, T_0800),
            ("L2-B", 50, 0, 0, T_0800),
        ),
        "cases": make_cases(20, level=2, prefix="ADV"),
        "expected_counts": {"L2-A": 10, "L2-B": 10},
    },

    # --- Tiebreak scenario ---

    "tiebreak_by_timestamp": {
        "description": "Dos analistas identicos. El mas antiguo gana el primer caso.",
        "pool": make_pool(
            ("RECENT", 50, 0, 0, T_0900),
            ("OLD",    50, 0, 0, T_0800),
        ),
        "cases": [CaseItem(id="TIE-001", level=1)],
        "expected_first": "OLD",
    },
}
