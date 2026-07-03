"""
Tests for Node 2 — FSM Extractor (obligation → HybridFSM transformation).

Covers:
  - FSM dict parsing and pre-validation (canonical states, min transitions, timeline rules)
  - extract_fsms() with MockLLMClient
  - persist_fsms() to data/extracted/
  - Integration with M1 parser output (real SEBI circular obligations)
  - Edge cases: empty input, malformed LLM output, partial valid FSMs
  - All 5 canonical states: PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.models.fsm import CANONICAL_STATES, HybridFSM
from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.pipeline.nodes.fsm_extractor import (
    _parse_fsm_dict,
    _validate_fsm_states,
    extract_fsms,
    load_fsm_prompt_template,
    persist_fsms,
)
from app.utils.llm_client import LLMClientError, MockLLMClient


# ====================================================================
# Helpers — Build valid FSM dicts matching the canonical SEBI circular
# ====================================================================

CIRCULAR_REF = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"


def _make_canonical_states() -> list[dict[str, str]]:
    """All 5 canonical states with descriptions — must be present in every FSM."""
    return [
        {"name": "PENDING", "description": "Obligation active; deadline not yet reached"},
        {"name": "DUE", "description": "Deadline window open; compliance action expected"},
        {"name": "COMPLIANT", "description": "Required action completed within deadline"},
        {"name": "LATE", "description": "Deadline elapsed without compliance"},
        {"name": "NON_COMPLIANT", "description": "Compliance breach confirmed"},
    ]


def _make_timeline_rule(
    start_event: str = "trade_executed",
    offset: int = 1,
    grace_period: int = 0,
    unit: str = "days",
) -> dict[str, Any]:
    return {
        "start_event": start_event,
        "deadline_offset": offset,
        "grace_period": grace_period,
        "time_unit": unit,
        "overdue_transition": "LATE",
    }


def _make_base_transitions(compliance_event: str, advance_event: str = "") -> list[dict[str, Any]]:
    """Build a minimal valid transition set (6 transitions covering all paths)."""
    t = [
        {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": compliance_event, "conditions": None},
        {"from_state": "PENDING", "to_state": "DUE", "trigger_event": advance_event or "deadline_approaching", "conditions": None},
        {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": compliance_event, "conditions": None},
        {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
    ]
    return t


# ---------------------------------------------------------------------------
# Sample FSM LLM responses matching real SEBI circular obligations
# ---------------------------------------------------------------------------

FSM_CL01 = {
    "obligation_ref": "CIRC-2025-057-CL-01",
    "circular_ref": CIRCULAR_REF,
    "states": [
        {"name": "PENDING", "description": "Trade executed; awaiting margin collection by settlement day"},
        {"name": "DUE", "description": "Settlement day approaching; margin collection expected"},
        {"name": "COMPLIANT", "description": "Margins collected by settlement day"},
        {"name": "LATE", "description": "Settlement day passed without full margin collection"},
        {"name": "NON_COMPLIANT", "description": "Penalty assessed for non-collection"},
    ],
    "initial_state": "PENDING",
    "transitions": [
        {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "margin_collected", "conditions": None},
        {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "settlement_day_approaching", "conditions": None},
        {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "margin_collected", "conditions": None},
        {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
    ],
    "timeline_rules": [
        {"start_event": "trade_executed", "deadline_offset": 1, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
    ],
    "metadata": {
        "clause_text": "The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
        "obligation_type": "timeline",
        "extraction_confidence": 0.95,
    },
}

FSM_CL02 = {
    "obligation_ref": "CIRC-2025-057-CL-02",
    "circular_ref": CIRCULAR_REF,
    "states": [
        {"name": "PENDING", "description": "Margin call issued; VaR/ELM collection required before trade"},
        {"name": "DUE", "description": "Trade imminent; collection window narrowing"},
        {"name": "COMPLIANT", "description": "VaR margins and ELM collected in advance of trade"},
        {"name": "LATE", "description": "Trade executed without upfront VaR/ELM collection"},
        {"name": "NON_COMPLIANT", "description": "Penalty assessed for failure to collect upfront margins"},
    ],
    "initial_state": "PENDING",
    "transitions": [
        {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "var_margin_collected", "conditions": {"timing": "advance_of_trade"}},
        {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "trade_imminent", "conditions": None},
        {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "trade_executed", "conditions": None},
        {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "var_margin_collected", "conditions": {"timing": "advance_of_trade"}},
        {"from_state": "DUE", "to_state": "LATE", "trigger_event": "trade_executed", "conditions": None},
        {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
    ],
    "timeline_rules": [
        {"start_event": "margin_call_issued", "deadline_offset": 0, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
    ],
    "metadata": {
        "clause_text": "The TMs/CMs in cash segment are required to mandatorily collect upfront VaR margins and ELM from their clients in advance of trade.",
        "obligation_type": "timeline",
        "extraction_confidence": 0.95,
    },
}

FSM_CL03 = {
    "obligation_ref": "CIRC-2025-057-CL-03",
    "circular_ref": CIRCULAR_REF,
    "states": [
        {"name": "PENDING", "description": "Circular issued; bye-law amendments not yet made"},
        {"name": "DUE", "description": "Amendment process started; completion expected"},
        {"name": "COMPLIANT", "description": "Bye-laws amended as required"},
        {"name": "LATE", "description": "Amendment deadline missed"},
        {"name": "NON_COMPLIANT", "description": "Failure to amend confirmed"},
    ],
    "initial_state": "PENDING",
    "transitions": [
        {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "bye_laws_amended", "conditions": None},
        {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "amendment_process_started", "conditions": None},
        {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "bye_laws_amended", "conditions": None},
        {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
    ],
    "timeline_rules": [
        {"start_event": "circular_issued", "deadline_offset": 90, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
    ],
    "metadata": {
        "clause_text": "The recognized Stock Exchanges and Clearing Corporations shall make necessary amendments to the relevant bye-laws, rules and regulations for the implementation of the above decision.",
        "obligation_type": "procedure",
        "extraction_confidence": 0.90,
    },
}

FSM_CL04 = {
    "obligation_ref": "CIRC-2025-057-CL-04",
    "circular_ref": CIRCULAR_REF,
    "states": [
        {"name": "PENDING", "description": "Circular issued; dissemination not yet done"},
        {"name": "DUE", "description": "Dissemination window open; notice expected"},
        {"name": "COMPLIANT", "description": "Circular provisions disseminated to market participants"},
        {"name": "LATE", "description": "Dissemination deadline missed"},
        {"name": "NON_COMPLIANT", "description": "Failure to disseminate confirmed"},
    ],
    "initial_state": "PENDING",
    "transitions": [
        {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "circular_disseminated", "conditions": None},
        {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "dissemination_window_open", "conditions": None},
        {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "circular_disseminated", "conditions": None},
        {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
        {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
    ],
    "timeline_rules": [
        {"start_event": "circular_issued", "deadline_offset": 30, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
    ],
    "metadata": {
        "clause_text": "The recognized Stock Exchanges and Clearing Corporations shall bring the provisions of this circular to the notice of the market participants and disseminate the same on their website.",
        "obligation_type": "procedure",
        "extraction_confidence": 0.90,
    },
}

# All 4 FSMs from the canonical circular
ALL_FSMS = [FSM_CL01, FSM_CL02, FSM_CL03, FSM_CL04]
SAMPLE_LLM_FSM_RESPONSE = json.dumps(ALL_FSMS)


# ====================================================================
# Real obligation clauses matching the canonical SEBI circular
# ====================================================================

REAL_OBLIGATIONS = [
    ObligationClause(
        clause_id="CIRC-2025-057-CL-01",
        circular_ref=CIRCULAR_REF,
        clause_text="The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
        obligation_type=ObligationType.TIMELINE,
        timeline_params=TimelineParams(offset=1, grace_period=0, unit="days"),
        effective_date=date(2025, 4, 28),
        applicable_entities=["trading_member", "clearing_member"],
    ),
    ObligationClause(
        clause_id="CIRC-2025-057-CL-02",
        circular_ref=CIRCULAR_REF,
        clause_text="The TMs/CMs in cash segment are required to mandatorily collect upfront VaR margins and ELM from their clients in advance of trade.",
        obligation_type=ObligationType.TIMELINE,
        timeline_params=TimelineParams(offset=0, grace_period=0, unit="days"),
        effective_date=date(2025, 4, 28),
        applicable_entities=["trading_member", "clearing_member"],
    ),
    ObligationClause(
        clause_id="CIRC-2025-057-CL-03",
        circular_ref=CIRCULAR_REF,
        clause_text="The recognized Stock Exchanges and Clearing Corporations shall make necessary amendments to the relevant bye-laws, rules and regulations for the implementation of the above decision.",
        obligation_type=ObligationType.PROCEDURE,
        timeline_params=None,
        effective_date=date(2025, 4, 28),
        applicable_entities=["recognized_stock_exchange", "clearing_corporation"],
    ),
    ObligationClause(
        clause_id="CIRC-2025-057-CL-04",
        circular_ref=CIRCULAR_REF,
        clause_text="The recognized Stock Exchanges and Clearing Corporations shall bring the provisions of this circular to the notice of the market participants and disseminate the same on their website.",
        obligation_type=ObligationType.PROCEDURE,
        timeline_params=None,
        effective_date=date(2025, 4, 28),
        applicable_entities=["recognized_stock_exchange", "clearing_corporation"],
    ),
]


# ====================================================================
# FSM validation — pre-Pydantic checks
# ====================================================================


class TestValidateFsmStates:
    """Tests for _validate_fsm_states — canonical state presence."""

    def test_all_five_canonical_states_present(self):
        fsm_dict = {
            "obligation_ref": "CL-01",
            "states": _make_canonical_states(),
        }
        _validate_fsm_states(fsm_dict)  # Should not raise

    def test_missing_states_raises(self):
        fsm_dict = {
            "obligation_ref": "CL-01",
            "states": [
                {"name": "PENDING", "description": ""},
                {"name": "COMPLIANT", "description": ""},
                {"name": "NON_COMPLIANT", "description": ""},
            ],
        }
        with pytest.raises(ValueError, match="missing canonical states"):
            _validate_fsm_states(fsm_dict)

    def test_missing_single_state_raises(self):
        """Missing just DUE should still raise."""
        states = [s for s in _make_canonical_states() if s["name"] != "DUE"]
        fsm_dict = {"obligation_ref": "CL-01", "states": states}
        with pytest.raises(ValueError, match="missing canonical states"):
            _validate_fsm_states(fsm_dict)

    def test_missing_states_key_raises(self):
        with pytest.raises(ValueError, match="missing 'states' array"):
            _validate_fsm_states({"obligation_ref": "CL-01"})

    def test_non_list_states_raises(self):
        with pytest.raises(ValueError, match="missing 'states' array"):
            _validate_fsm_states({"obligation_ref": "CL-01", "states": "not a list"})


# ====================================================================
# FSM dict parsing
# ====================================================================


class TestParseFsmDict:
    """Tests for _parse_fsm_dict — dict-to-HybridFSM validation."""

    def test_valid_timeline_fsm(self):
        fsm = _parse_fsm_dict(FSM_CL01.copy(), CIRCULAR_REF)
        assert isinstance(fsm, HybridFSM)
        assert fsm.obligation_ref == "CIRC-2025-057-CL-01"
        assert fsm.initial_state == "PENDING"
        assert len(fsm.states) == 5
        assert len(fsm.transitions) >= 3
        assert len(fsm.timeline_rules) >= 1
        assert fsm.is_valid_canonical

    def test_valid_procedure_fsm(self):
        fsm = _parse_fsm_dict(FSM_CL03.copy(), CIRCULAR_REF)
        assert isinstance(fsm, HybridFSM)
        assert fsm.initial_state == "PENDING"
        assert fsm.timeline_rules[0].deadline_offset == 90

    def test_circular_ref_filled_when_missing(self):
        data = FSM_CL01.copy()
        del data["circular_ref"]
        fsm = _parse_fsm_dict(data, CIRCULAR_REF)
        assert fsm.circular_ref == CIRCULAR_REF

    def test_initial_state_overridden_to_pending(self):
        data = FSM_CL01.copy()
        data["initial_state"] = "DUE"
        fsm = _parse_fsm_dict(data, CIRCULAR_REF)
        assert fsm.initial_state == "PENDING"

    def test_too_few_transitions_raises(self):
        data = FSM_CL01.copy()
        data["transitions"] = [
            {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "evt", "conditions": None},
        ]
        with pytest.raises(ValueError, match="only 1 transition"):
            _parse_fsm_dict(data, CIRCULAR_REF)

    def test_missing_timeline_rules_raises(self):
        data = FSM_CL01.copy()
        data["timeline_rules"] = []
        with pytest.raises(ValueError, match="no timeline_rules"):
            _parse_fsm_dict(data, CIRCULAR_REF)

    def test_missing_states_raises(self):
        data = FSM_CL01.copy()
        data["states"] = data["states"][:2]  # only 2 states, missing canonical
        with pytest.raises(ValueError, match="missing canonical states"):
            _parse_fsm_dict(data, CIRCULAR_REF)

    def test_invalid_transition_from_state_raises(self):
        data = FSM_CL01.copy()
        data["transitions"] = data["transitions"][:4]  # remove some
        data["transitions"][0] = {
            "from_state": "NONEXISTENT",
            "to_state": "COMPLIANT",
            "trigger_event": "evt",
            "conditions": None,
        }
        with pytest.raises(ValueError, match="not found in FSM states"):
            _parse_fsm_dict(data, CIRCULAR_REF)

    def test_timeline_rule_missing_fields_raises(self):
        data = FSM_CL01.copy()
        data["timeline_rules"] = [{"start_event": "evt"}]  # missing deadline_offset
        with pytest.raises(ValueError):
            _parse_fsm_dict(data, CIRCULAR_REF)

    def test_every_canonical_state_is_terminal_or_has_outgoing(self):
        """COMPLIANT and NON_COMPLIANT are terminal; others have outgoing transitions."""
        fsm = _parse_fsm_dict(FSM_CL01.copy(), CIRCULAR_REF)
        terminal = fsm.terminal_states
        # COMPLIANT and NON_COMPLIANT should be terminal
        assert "COMPLIANT" in terminal
        assert "NON_COMPLIANT" in terminal
        # PENDING, DUE, LATE should NOT be terminal (they have outgoing transitions)
        assert "PENDING" not in terminal
        assert "DUE" not in terminal
        assert "LATE" not in terminal


# ====================================================================
# Prompt loading
# ====================================================================


class TestFsmPromptLoading:
    """Tests for load_fsm_prompt_template."""

    def test_load_default_prompt(self):
        template = load_fsm_prompt_template()
        assert len(template) > 100
        assert "FSM" in template or "finite state" in template.lower()
        assert "PENDING" in template
        assert "CANONICAL" in template or "canonical" in template.lower()

    def test_load_nonexistent_prompt(self):
        with pytest.raises(FileNotFoundError, match="FSM extractor prompt template not found"):
            load_fsm_prompt_template("/nonexistent/path/prompt.md")


# ====================================================================
# extract_fsms integration tests
# ====================================================================


class TestExtractFsms:
    """Integration tests for extract_fsms with MockLLMClient."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        """Full FSM extraction from real SEBI circular obligations."""
        client = MockLLMClient(response=SAMPLE_LLM_FSM_RESPONSE)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)

        assert len(fsms) == 4

        # FSM 1: timeline, T+1
        assert fsms[0].obligation_ref == "CIRC-2025-057-CL-01"
        assert len(fsms[0].states) == 5
        assert fsms[0].is_valid_canonical
        assert fsms[0].timeline_rules[0].deadline_offset == 1
        assert fsms[0].timeline_rules[0].start_event == "trade_executed"

        # FSM 2: timeline, offset=0 (advance of trade)
        assert fsms[1].obligation_ref == "CIRC-2025-057-CL-02"
        assert fsms[1].timeline_rules[0].deadline_offset == 0

        # FSM 3: procedure with fallback timeline
        assert fsms[2].obligation_ref == "CIRC-2025-057-CL-03"
        assert fsms[2].timeline_rules[0].deadline_offset == 90

        # FSM 4: procedure with fallback timeline
        assert fsms[3].obligation_ref == "CIRC-2025-057-CL-04"

        # Every FSM must have all 5 canonical states
        for fsm in fsms:
            assert fsm.state_names == CANONICAL_STATES
            assert fsm.initial_state == "PENDING"
            assert len(fsm.transitions) >= 3
            assert len(fsm.timeline_rules) >= 1
            assert fsm.circular_ref == CIRCULAR_REF
            assert fsm.metadata.get("clause_text")

    @pytest.mark.asyncio
    async def test_empty_clauses_raises(self):
        client = MockLLMClient()
        with pytest.raises(ValueError, match="clauses list is empty"):
            await extract_fsms([], CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_llm_returns_empty_array(self):
        client = MockLLMClient(response="[]")
        with pytest.raises(ValueError, match="No FSMs extracted"):
            await extract_fsms(REAL_OBLIGATIONS[:1], CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_llm_returns_invalid_json(self):
        client = MockLLMClient(response="not json at all")
        with pytest.raises(ValueError, match="Could not extract a valid JSON array"):
            await extract_fsms(REAL_OBLIGATIONS[:1], CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_llm_client_error_propagates(self):
        client = MockLLMClient(response="[]")

        async def _failing(*args, **kwargs):
            raise LLMClientError("API unavailable", status_code=503)
        client.generate = _failing  # type: ignore[method-assign]

        with pytest.raises(LLMClientError, match="API unavailable"):
            await extract_fsms(REAL_OBLIGATIONS[:1], CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_partial_valid_fsms_survive(self):
        """Some FSMs valid, some invalid — valid ones survive."""
        # Valid FSM + one with missing states
        mixed = [
            FSM_CL01.copy(),
            {
                "obligation_ref": "CIRC-2025-057-CL-BAD",
                "circular_ref": CIRCULAR_REF,
                "states": [
                    {"name": "PENDING", "description": ""},
                    {"name": "COMPLIANT", "description": ""},
                ],
                "initial_state": "PENDING",
                "transitions": [
                    {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "evt", "conditions": None},
                ],
                "timeline_rules": [],
                "metadata": {},
            },
        ]
        client = MockLLMClient(response=json.dumps(mixed))
        fsms = await extract_fsms(REAL_OBLIGATIONS[:2], CIRCULAR_REF, client)
        assert len(fsms) == 1
        assert fsms[0].obligation_ref == "CIRC-2025-057-CL-01"

    @pytest.mark.asyncio
    async def test_all_fsms_invalid_raises(self):
        """When every FSM fails validation, raise ValueError."""
        bad = [{
            "obligation_ref": "CIRC-BAD",
            "circular_ref": CIRCULAR_REF,
            "states": [{"name": "PENDING", "description": ""}],
            "initial_state": "PENDING",
            "transitions": [],
            "timeline_rules": [],
            "metadata": {},
        }]
        client = MockLLMClient(response=json.dumps(bad))
        with pytest.raises(ValueError, match="All .* extracted FSMs failed"):
            await extract_fsms(REAL_OBLIGATIONS[:1], CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_markdown_fenced_llm_response(self):
        """FSM response wrapped in markdown fences — should still parse."""
        fenced = f"```json\n{SAMPLE_LLM_FSM_RESPONSE}\n```"
        client = MockLLMClient(response=fenced)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)
        assert len(fsms) == 4

    @pytest.mark.asyncio
    async def test_single_clause_produces_single_fsm(self):
        """A single obligation clause → single FSM object (not array)."""
        client = MockLLMClient(response=json.dumps(FSM_CL01))
        fsms = await extract_fsms(REAL_OBLIGATIONS[:1], CIRCULAR_REF, client)
        assert len(fsms) == 1
        assert fsms[0].obligation_ref == "CIRC-2025-057-CL-01"

    @pytest.mark.asyncio
    async def test_fsm_includes_all_5_canonical_states(self):
        """Every FSM must have exactly the 5 canonical states."""
        client = MockLLMClient(response=SAMPLE_LLM_FSM_RESPONSE)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)
        for fsm in fsms:
            assert fsm.state_names == CANONICAL_STATES, (
                f"FSM {fsm.obligation_ref}: expected {CANONICAL_STATES}, got {fsm.state_names}"
            )

    @pytest.mark.asyncio
    async def test_fsm_has_deadline_based_transition(self):
        """Every FSM must include at least one time-based auto-transition (timeline_rule)."""
        client = MockLLMClient(response=SAMPLE_LLM_FSM_RESPONSE)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)
        for fsm in fsms:
            assert len(fsm.timeline_rules) >= 1
            rule = fsm.timeline_rules[0]
            assert rule.overdue_transition == "LATE"
            assert rule.start_event  # must have a defined start event

    @pytest.mark.asyncio
    async def test_fsm_ids_are_unique(self):
        """Each FSM must have a unique fsm_id."""
        client = MockLLMClient(response=SAMPLE_LLM_FSM_RESPONSE)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)
        ids = [f.fsm_id for f in fsms]
        assert len(ids) == len(set(ids)), f"Duplicate FSM IDs: {ids}"


# ====================================================================
# Persistence tests
# ====================================================================


class TestPersistFsms:
    """Tests for persist_fsms — disk serialisation."""

    @pytest.mark.asyncio
    async def test_persist_writes_files(self):
        """Persist FSMs to a temp directory and verify file structure."""
        client = MockLLMClient(response=SAMPLE_LLM_FSM_RESPONSE)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)

        with tempfile.TemporaryDirectory() as tmpdir:
            fsm_dir = persist_fsms(fsms, CIRCULAR_REF, output_dir=tmpdir)

            # Verify directory was created
            assert fsm_dir.exists()
            assert fsm_dir.is_dir()

            # Verify individual FSM files
            for fsm in fsms:
                fsm_file = fsm_dir / f"{fsm.fsm_id}.json"
                assert fsm_file.exists(), f"Missing FSM file: {fsm_file}"
                content = fsm_file.read_text()
                assert fsm.obligation_ref in content

            # Verify index file
            index_file = fsm_dir / "_index.json"
            assert index_file.exists()
            index_data = json.loads(index_file.read_text())
            assert index_data["circular_ref"] == CIRCULAR_REF
            assert index_data["fsm_count"] == 4
            assert len(index_data["fsm_ids"]) == 4

    @pytest.mark.asyncio
    async def test_persist_empty_fsms(self):
        """Persisting an empty list should still create the directory with an empty index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fsm_dir = persist_fsms([], CIRCULAR_REF, output_dir=tmpdir)
            assert fsm_dir.exists()
            index_file = fsm_dir / "_index.json"
            assert index_file.exists()
            index_data = json.loads(index_file.read_text())
            assert index_data["fsm_count"] == 0

    @pytest.mark.asyncio
    async def test_persist_roundtrip(self):
        """FSMs persisted to disk can be re-read and validated."""
        client = MockLLMClient(response=SAMPLE_LLM_FSM_RESPONSE)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)

        with tempfile.TemporaryDirectory() as tmpdir:
            fsm_dir = persist_fsms(fsms, CIRCULAR_REF, output_dir=tmpdir)

            # Re-read each FSM file and validate
            for fsm_file in sorted(fsm_dir.glob("*.json")):
                if fsm_file.name == "_index.json":
                    continue
                data = json.loads(fsm_file.read_text())
                rehydrated = HybridFSM.model_validate(data)
                assert rehydrated.obligation_ref
                assert len(rehydrated.states) == 5

    @pytest.mark.asyncio
    async def test_obligation_traceability_preserved(self):
        """Every persisted FSM must link back to its source obligation clause."""
        client = MockLLMClient(response=SAMPLE_LLM_FSM_RESPONSE)
        fsms = await extract_fsms(REAL_OBLIGATIONS, CIRCULAR_REF, client)

        obligation_refs = {c.clause_id for c in REAL_OBLIGATIONS}
        fsm_refs = {f.obligation_ref for f in fsms}
        assert fsm_refs == obligation_refs, (
            f"FSM obligation_refs {fsm_refs} don't match input clause IDs {obligation_refs}"
        )


# ====================================================================
# CANONICAL_STATES constant
# ====================================================================


def test_canonical_states_constant():
    """Verify the CANONICAL_STATES set defined in the FSM model."""
    assert CANONICAL_STATES == {"PENDING", "DUE", "COMPLIANT", "LATE", "NON_COMPLIANT"}
