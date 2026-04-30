"""
Shared fixtures for WDD tests.

Fixtures wrap mock_data scenarios for convenient use in test functions.
For direct access to all scenarios, import from mock_data.py.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from wdd.models import PoolMember, CaseItem
from wdd.tests.mock_data import make_pool, make_cases, T_0800


# ---------------------------------------------------------------------------
# Pool fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pool_mixed():
    """Three specialists: one fixed at 60%, two auto-split (20% each)."""
    return make_pool(
        ("SP-01", 60,   0, 0, T_0800),
        ("SP-02", None, 0, 0, T_0800),
        ("SP-03", None, 0, 0, T_0800),
    )


@pytest.fixture
def pool_equal():
    """Three specialists, all auto-split (33.33% each)."""
    return make_pool(
        ("A", None, 0, 0, T_0800),
        ("B", None, 0, 0, T_0800),
        ("C", None, 0, 0, T_0800),
    )


@pytest.fixture
def pool_single():
    """A single specialist."""
    return make_pool(
        ("SOLO", 100, 0, 0, T_0800),
    )


@pytest.fixture
def pool_with_history():
    """Two specialists with pre-existing history. SP-01 behind (owed), SP-02 ahead."""
    return make_pool(
        # deficit +2 = system owes SP-01 two cases (old balance was -2)
        ("SP-01", 50, 3,  2.0, datetime(2026, 1, 1, 10, 0)),
        # deficit -2 = SP-02 is ahead (old balance was +2)
        ("SP-02", 50, 7, -2.0, datetime(2026, 1, 1, 10, 0)),
    )


# ---------------------------------------------------------------------------
# Case fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cases_10():
    return make_cases(10)


@pytest.fixture
def cases_100():
    return make_cases(100)
