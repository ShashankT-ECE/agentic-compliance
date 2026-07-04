"""
Shared pytest fixtures for the compliance pipeline test suite.

Provides:
  - Basic test data (broker IDs, references, timestamps)
  - M9 demo fixtures (circular PDF, telemetry events, canonical references)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.models.telemetry import TelemetryEvent

# =============================================================================
# Basic test data
# =============================================================================


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


# =============================================================================
# M9 demo fixtures — end-to-end demo scenario data
# =============================================================================

# Canonical V1 regulatory source (from memory/decision_log.md)
DEMO_CIRCULAR_REF = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def demo_circular_path() -> Path:
    """Path to the demo SEBI circular PDF fixture.

    The PDF is a valid multi-page document generated from the canonical
    V1 circular text (circular_slice.txt) and is parseable by pdfplumber.

    Used by integration tests that exercise the full pipeline including
    PDF text extraction.
    """
    return _FIXTURE_DIR / "sample_circular.pdf"


@pytest.fixture(scope="session")
def demo_circular_text() -> str:
    """Raw text of the canonical V1 SEBI circular.

    Loaded from the existing circular_slice.txt fixture.  Tests that
    bypass PDF extraction (e.g. calling parse_circular() directly with a
    MockLLMClient) should use this fixture.
    """
    path = _FIXTURE_DIR / "circular_slice.txt"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def demo_circular_ref() -> str:
    """The canonical V1 SEBI circular reference number.

    SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57 dated 28 April 2025,
    subject: "Timelines for collection of Margins other than Upfront
    Margins — Alignment to settlement cycle."
    """
    return DEMO_CIRCULAR_REF


@pytest.fixture(scope="session")
def demo_telemetry_records() -> list[dict[str, Any]]:
    """Raw telemetry event dicts from the demo fixture file.

    Covers 3 brokers (COMPLIANT, LATE, MISSING) across 10 events
    spanning trade_executed, margin_call_made, margin_report_filed,
    and payin_made event types.

    Suitable for direct use with the API trigger endpoint or the
    pipeline runner's telemetry_events parameter.
    """
    path = _FIXTURE_DIR / "sample_telemetry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["records"]


@pytest.fixture
def demo_telemetry_events(
    demo_telemetry_records: list[dict[str, Any]],
) -> list[TelemetryEvent]:
    """Validated TelemetryEvent models from the demo fixture.

    Each event dict from sample_telemetry.json is parsed through the
    Pydantic model, ensuring the fixture data is schema-conformant.
    """
    return [TelemetryEvent.model_validate(r) for r in demo_telemetry_records]
