"""
Shared pytest fixtures for the compliance pipeline test suite.
"""

from datetime import date, datetime

import pytest

# ---------------------------------------------------------------------------
# Reusable test data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_broker_id() -> str:
    """A representative broker ID."""
    return "B-12345"


@pytest.fixture
def sample_circular_ref() -> str:
    """A representative SEBI circular reference."""
    return "SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001"


@pytest.fixture
def sample_clause_id() -> str:
    """A representative clause ID."""
    return "CIRC-2024-001-CL-03"


@pytest.fixture
def sample_fsm_id() -> str:
    """A representative FSM ID prefix."""
    return "FSM-A1B2C3D4E5F6"


@pytest.fixture
def sample_timestamp() -> datetime:
    """A fixed UTC timestamp for deterministic test assertions."""
    return datetime(2026, 7, 3, 10, 0, 0)
