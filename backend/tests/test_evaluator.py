"""
Tests for Node 3: Assertion Evaluator (deterministic — NO LLM allowed).

The evaluator is the most critical node in the pipeline. Architecture rule:
- Node 3 must **never** call an LLM.
- Evaluation is strictly deterministic: FSM state transitions matched against telemetry.
- Human approval is required before execution (HITL gate upstream of this node).

These tests enforce the interface contract, the architectural safety constraints,
and provide comprehensive functional coverage of all M5 requirements.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure backend package root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.fsm import (
    FSMState,
    FSMTransition,
    HybridFSM,
    TimelineRule,
)
from app.models.locked_fsm import LockStatus, LockedFSM
from app.models.scoreboard import HashLink
from app.models.telemetry import TelemetryEvent
from app.models.verdict import ComplianceVerdict, VerdictStatus

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# =========================================================================
# Fixture helpers
# =========================================================================


def _load_mock_telemetry() -> list[dict]:
    """Load the mock telemetry fixture."""
    path = FIXTURES_DIR / "mock_telemetry.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("records", [])


def _make_simple_fsm(
    fsm_id: str = "FSM-001",
    obligation_ref: str = "OBL-001",
    initial_state: str = "PENDING",
    states: list[str] | None = None,
    transitions: list[tuple[str, str, str]] | None = None,
    timeline_rules: list[TimelineRule] | None = None,
) -> HybridFSM:
    """Build a minimal valid HybridFSM for testing.

    Args:
        fsm_id: FSM identifier.
        obligation_ref: Source obligation reference.
        initial_state: Name of the initial state.
        states: List of state names (default: PENDING, COMPLIANT).
        transitions: List of (from_state, to_state, trigger_event) tuples.
        timeline_rules: Optional list of TimelineRule objects.
    """
    if states is None:
        states = ["PENDING", "COMPLIANT"]
    if transitions is None:
        transitions = [("PENDING", "COMPLIANT", "margin_report_filed")]

    return HybridFSM(
        fsm_id=fsm_id,
        obligation_ref=obligation_ref,
        circular_ref="SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        initial_state=initial_state,
        states=[FSMState(name=s) for s in states],
        transitions=[
            FSMTransition(from_state=f, to_state=t, trigger_event=trig)
            for f, t, trig in transitions
        ],
        timeline_rules=timeline_rules or [],
    )


def _make_hash_link(index: int = 0) -> HashLink:
    """Build a minimal valid HashLink for testing."""
    return HashLink(
        index=index,
        data_hash="b" * 64,
        previous_hash="0" * 64,
        link_hash="c" * 64,
    )


def _make_locked_fsm(
    fsm: HybridFSM | None = None,
    locked_fsm_id: str = "LOCKED-001",
    status: LockStatus = LockStatus.APPROVED,
    reviewer: str = "tester",
) -> LockedFSM:
    """Build a minimal LockedFSM for testing.

    For APPROVED/AMENDED statuses, includes integrity_hash and hash_link.
    For REJECTED status, includes review_comments.
    """
    if fsm is None:
        fsm = _make_simple_fsm()

    kwargs: dict = {
        "locked_fsm_id": locked_fsm_id,
        "fsm_id": fsm.fsm_id,
        "obligation_ref": fsm.obligation_ref,
        "circular_ref": fsm.circular_ref,
        "version": 1,
        "original_fsm": fsm,
        "status": status,
        "reviewer": reviewer,
        "reviewed_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
    }

    if status in (LockStatus.APPROVED, LockStatus.AMENDED):
        kwargs["integrity_hash"] = "a" * 64
        kwargs["hash_link"] = _make_hash_link()
    elif status == LockStatus.REJECTED:
        kwargs["review_comments"] = "FSM is incorrect"

    return LockedFSM(**kwargs)


def _make_telemetry_event(
    event_type: str = "margin_report_filed",
    timestamp: datetime | None = None,
    *,
    broker_id: str = "BROKER001",
) -> TelemetryEvent:
    """Build a minimal TelemetryEvent for testing.

    Args:
        event_type: Event type (positional).
        timestamp: Timestamp (positional, defaults to 2026-06-01T12:00Z).
        broker_id: Broker ID (keyword-only).
    """
    if timestamp is None:
        timestamp = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    return TelemetryEvent(
        broker_id=broker_id,
        event_type=event_type,
        timestamp=timestamp,
    )


# =========================================================================
# CRITICAL: No-LLM architectural safety tests
# =========================================================================


class TestEvaluatorNoLLM:
    """Verify the evaluator module never imports or uses LLM libraries."""

    _FORBIDDEN = {
        "openai", "langchain", "anthropic", "deepseek", "cohere",
        "google.generativeai", "mistralai", "llama_index", "llamaindex",
        "transformers",
    }

    def test_no_llm_imports_in_evaluator(self):
        """Static AST analysis: evaluator must not import any LLM library."""
        source = _get_evaluator_source()
        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        forbidden = [
            imp for imp in imports
            if any(p in imp.lower() for p in self._FORBIDDEN)
        ]
        assert not forbidden, (
            f"FORBIDDEN LLM imports in evaluator: {forbidden}"
        )

    def test_no_llm_imports_in_state_machine(self):
        """State machine must also be LLM-free."""
        import app.utils.state_machine as mod
        source = inspect.getsource(mod)
        for pattern in self._FORBIDDEN:
            assert pattern not in source.lower(), (
                f"Forbidden '{pattern}' in state_machine.py"
            )

    def test_no_llm_imports_in_timeline_evaluator(self):
        """Timeline evaluator must also be LLM-free."""
        import app.utils.timeline_evaluator as mod
        source = inspect.getsource(mod)
        for pattern in self._FORBIDDEN:
            assert pattern not in source.lower(), (
                f"Forbidden '{pattern}' in timeline_evaluator.py"
            )

    def test_no_http_calls(self):
        """Evaluator must not make HTTP calls."""
        source = _get_evaluator_source()
        assert "requests." not in source, "evaluator must not use requests"
        assert "httpx." not in source, "evaluator must not use httpx"

    def test_no_randomness(self):
        """Evaluator must not use random, secrets, or uuid."""
        source = _get_evaluator_source()
        for pattern in ["import random", "from random", "secrets.", "os.urandom"]:
            assert pattern not in source, (
                f"Non-deterministic pattern: '{pattern}'"
            )

    def test_no_dynamic_imports(self):
        """Evaluator must not use dynamic import mechanisms."""
        source = _get_evaluator_source()
        assert "importlib" not in source
        assert "__import__" not in source


# =========================================================================
# State Machine Tests
# =========================================================================


class TestStateMachine:
    """Tests for the deterministic state machine engine."""

    def test_imports(self):
        from app.utils.state_machine import StateMachine
        assert StateMachine is not None

    def test_initial_state(self):
        from app.utils.state_machine import StateMachine
        fsm = _make_simple_fsm()
        sm = StateMachine(fsm)
        assert sm.current_state == "PENDING"
        assert sm.is_initial is True
        assert sm.is_terminal is False

    def test_event_triggers_transition(self):
        from app.utils.state_machine import StateMachine
        fsm = _make_simple_fsm()
        sm = StateMachine(fsm)
        event = {"event_type": "margin_report_filed", "timestamp": "2026-06-01T12:00:00Z"}
        transitioned, record = sm.apply_event(event)
        assert transitioned is True
        assert record is not None
        assert record["source"] == "PENDING"
        assert record["target"] == "COMPLIANT"
        assert sm.current_state == "COMPLIANT"
        assert sm.is_terminal is True

    def test_no_matching_event(self):
        from app.utils.state_machine import StateMachine
        fsm = _make_simple_fsm()
        sm = StateMachine(fsm)
        transitioned, record = sm.apply_event(
            {"event_type": "unknown_event", "timestamp": "2026-06-01T12:00:00Z"}
        )
        assert transitioned is False
        assert record is None
        assert sm.current_state == "PENDING"

    def test_terminal_state_stays_terminal(self):
        from app.utils.state_machine import StateMachine
        fsm = _make_simple_fsm()
        sm = StateMachine(fsm)
        sm.apply_event({"event_type": "margin_report_filed", "timestamp": "2026-06-01T12:00:00Z"})
        assert sm.is_terminal is True
        # Extra events are no-ops
        sm.apply_event({"event_type": "margin_report_filed", "timestamp": "2026-06-02T12:00:00Z"})
        assert sm.current_state == "COMPLIANT"
        assert sm.transition_count == 1  # no second transition

    def test_apply_events_sequence(self):
        from app.utils.state_machine import StateMachine
        fsm = _make_simple_fsm(
            transitions=[
                ("PENDING", "DUE", "trade_executed"),
                ("DUE", "COMPLIANT", "margin_report_filed"),
            ],
            states=["PENDING", "DUE", "COMPLIANT"],
            initial_state="PENDING",
        )
        sm = StateMachine(fsm)
        events = [
            {"event_type": "trade_executed", "timestamp": "2026-06-01T09:00:00Z"},
            {"event_type": "margin_report_filed", "timestamp": "2026-06-01T12:00:00Z"},
        ]
        history = sm.apply_events(events)
        assert len(history) == 2
        assert sm.current_state == "COMPLIANT"
        assert history[0]["source"] == "PENDING"
        assert history[0]["target"] == "DUE"
        assert history[1]["source"] == "DUE"
        assert history[1]["target"] == "COMPLIANT"

    def test_determine_compliant(self):
        from app.utils.state_machine import StateMachine
        fsm = _make_simple_fsm()
        sm = StateMachine(fsm)
        sm.apply_event({"event_type": "margin_report_filed", "timestamp": "2026-06-01T12:00:00Z"})
        assert sm.determine_compliance_status() == StateMachine.STATUS_COMPLIANT

    def test_determine_pending(self):
        from app.utils.state_machine import StateMachine
        sm = StateMachine(_make_simple_fsm())
        assert sm.determine_compliance_status() == StateMachine.STATUS_PENDING

    def test_determine_due(self):
        from app.utils.state_machine import StateMachine
        fsm = _make_simple_fsm(
            transitions=[
                ("PENDING", "DUE", "trade_executed"),
                ("DUE", "COMPLIANT", "margin_report_filed"),
            ],
            states=["PENDING", "DUE", "COMPLIANT"],
            initial_state="PENDING",
        )
        sm = StateMachine(fsm)
        sm.apply_event({"event_type": "trade_executed", "timestamp": "2026-06-01T09:00:00Z"})
        assert sm.current_state == "DUE"
        assert sm.determine_compliance_status() == StateMachine.STATUS_DUE

    def test_determine_late(self):
        from app.utils.state_machine import StateMachine
        sm = StateMachine(_make_simple_fsm())
        sm.apply_event({"event_type": "margin_report_filed", "timestamp": "2026-06-01T12:00:00Z"})
        assert sm.determine_compliance_status(deadline_met=False) == StateMachine.STATUS_LATE

    def test_reset(self):
        from app.utils.state_machine import StateMachine
        sm = StateMachine(_make_simple_fsm())
        sm.apply_event({"event_type": "margin_report_filed", "timestamp": "2026-06-01T12:00:00Z"})
        sm.reset()
        assert sm.current_state == "PENDING"
        assert sm.history == []
        assert sm.transition_count == 0
        assert sm.is_initial is True

    def test_deterministic(self):
        from app.utils.state_machine import StateMachine
        events = [
            {"event_type": "margin_report_filed", "timestamp": "2026-06-01T09:00:00Z"},
        ]
        results = []
        for _ in range(5):
            sm = StateMachine(_make_simple_fsm())
            results.append((sm.apply_events(list(events)), sm.current_state))
        assert all(r == results[0] for r in results)

    def test_to_dict(self):
        from app.utils.state_machine import StateMachine
        sm = StateMachine(_make_simple_fsm())
        d = sm.to_dict()
        assert d["fsm_id"] == "FSM-001"
        assert d["current_state"] == "PENDING"


# =========================================================================
# Timeline Evaluator Tests
# =========================================================================


class TestTimelineEvaluator:
    """Tests for the deterministic timeline evaluation utility."""

    def test_imports(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        assert TimelineEvaluator is not None

    def test_parse_deadline(self):
        from app.utils.timeline_evaluator import TimelineEvaluator, DeadlineType
        assert TimelineEvaluator.parse_deadline("T") == (DeadlineType.T0, 0)
        assert TimelineEvaluator.parse_deadline("T+0") == (DeadlineType.T0, 0)
        assert TimelineEvaluator.parse_deadline("T+1") == (DeadlineType.T1, 1)
        assert TimelineEvaluator.parse_deadline("T+2") == (DeadlineType.T2, 2)
        assert TimelineEvaluator.parse_deadline("T+3") == (DeadlineType.T3, 3)
        assert TimelineEvaluator.parse_deadline("T+5") == (DeadlineType.CUSTOM, 5)

    def test_parse_deadline_fallback(self):
        from app.utils.timeline_evaluator import TimelineEvaluator, DeadlineType
        assert TimelineEvaluator.parse_deadline("garbage") == (DeadlineType.T0, 0)
        assert TimelineEvaluator.parse_deadline("") == (DeadlineType.T0, 0)

    def test_parse_offset_days(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        assert TimelineEvaluator.parse_offset_days("T+3") == 3
        assert TimelineEvaluator.parse_offset_days("T+1") == 1

    def test_compute_deadline_t0(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        ref = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
        dl = TimelineEvaluator.compute_deadline(ref, "T")
        assert dl == datetime(2026, 6, 1, 23, 59, 59, tzinfo=timezone.utc)

    def test_compute_deadline_t2(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        ref = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
        dl = TimelineEvaluator.compute_deadline(ref, "T+2")
        assert dl == datetime(2026, 6, 3, 23, 59, 59, tzinfo=timezone.utc)

    def test_compute_deadline_with_grace(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        ref = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
        dl = TimelineEvaluator.compute_deadline(ref, "T", grace_minutes=30)
        assert dl == datetime(2026, 6, 2, 0, 29, 59, tzinfo=timezone.utc)

    def test_compute_deadline_from_offset(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        ref = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
        dl = TimelineEvaluator.compute_deadline_from_offset(ref, offset_days=3, grace_days=1)
        assert dl == datetime(2026, 6, 5, 23, 59, 59, tzinfo=timezone.utc)

    def test_is_within_deadline(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        dl = datetime(2026, 6, 1, 23, 59, 59, tzinfo=timezone.utc)
        assert TimelineEvaluator.is_within_deadline(
            datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc), dl) is True
        assert TimelineEvaluator.is_within_deadline(
            datetime(2026, 6, 1, 23, 59, 59, tzinfo=timezone.utc), dl) is True
        assert TimelineEvaluator.is_within_deadline(
            datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc), dl) is False

    def test_evaluate_timeline_all_on_time(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        events = [
            {"timestamp": "2026-06-01T10:00:00Z", "event_type": "trade_executed"},
            {"timestamp": "2026-06-01T15:00:00Z", "event_type": "margin_report_filed"},
        ]
        r = TimelineEvaluator.evaluate_timeline(events, "T")
        assert r["deadline_met"] is True
        assert len(r["on_time_events"]) == 2
        assert len(r["late_events"]) == 0

    def test_evaluate_timeline_some_late(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        events = [
            {"timestamp": "2026-06-01T10:00:00Z", "event_type": "trade_executed"},
            {"timestamp": "2026-06-03T10:00:00Z", "event_type": "margin_report_filed"},
        ]
        r = TimelineEvaluator.evaluate_timeline(events, "T+1")
        assert r["deadline_met"] is False
        assert len(r["late_events"]) == 1

    def test_evaluate_timeline_empty(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        r = TimelineEvaluator.evaluate_timeline([], "T")
        assert r["deadline_met"] is None

    def test_deterministic(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        events = [
            {"timestamp": "2026-06-01T10:00:00Z", "event_type": "trade_executed"},
        ]
        r1 = TimelineEvaluator.evaluate_timeline(events, "T+2")
        r2 = TimelineEvaluator.evaluate_timeline(events, "T+2")
        assert r1 == r2

    def test_evaluate_timeline_rule_matched(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        rule = TimelineRule(
            start_event="trade_executed",
            deadline_offset=3,
            grace_period=0,
            time_unit="days",
            overdue_transition="LATE",
        )
        events = [
            {"timestamp": "2026-06-01T09:00:00Z", "event_type": "trade_executed"},
            {"timestamp": "2026-06-03T10:00:00Z", "event_type": "margin_report_filed"},
        ]
        r = TimelineEvaluator.evaluate_timeline_rule(events, rule)
        assert r["start_event_matched"] is True
        assert r["deadline_met"] is True  # within T+3

    def test_evaluate_timeline_rule_late(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        rule = TimelineRule(
            start_event="trade_executed",
            deadline_offset=1,
            grace_period=0,
            time_unit="days",
            overdue_transition="LATE",
        )
        events = [
            {"timestamp": "2026-06-01T09:00:00Z", "event_type": "trade_executed"},
            {"timestamp": "2026-06-05T10:00:00Z", "event_type": "margin_report_filed"},
        ]
        r = TimelineEvaluator.evaluate_timeline_rule(events, rule)
        assert r["start_event_matched"] is True
        assert r["deadline_met"] is False

    def test_evaluate_timeline_rule_no_start_event(self):
        from app.utils.timeline_evaluator import TimelineEvaluator
        rule = TimelineRule(
            start_event="trade_executed",
            deadline_offset=3,
            time_unit="days",
            overdue_transition="LATE",
        )
        events = [
            {"timestamp": "2026-06-01T10:00:00Z", "event_type": "other_event"},
        ]
        r = TimelineEvaluator.evaluate_timeline_rule(events, rule)
        assert r["start_event_matched"] is False
        assert r["deadline_met"] is None


# =========================================================================
# Telemetry Generator Tests
# =========================================================================


class TestTelemetryGenerator:
    """Tests for the synthetic telemetry generator."""

    def test_imports(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        assert TelemetryGenerator is not None

    def test_record(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        rec = TelemetryGenerator.record(
            "BROKER001", datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc),
            "margin_report_filed",
        )
        assert rec["broker_id"] == "BROKER001"
        assert rec["event_type"] == "margin_report_filed"
        assert "timestamp" in rec

    def test_compliant_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.compliant_sequence()
        assert len(seq) == 1
        assert seq[0]["event_type"] == "margin_report_filed"

    def test_non_compliant_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.non_compliant_sequence()
        assert seq == []

    def test_late_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.late_sequence(late_days=5)
        assert len(seq) == 1
        assert seq[0]["event_type"] == "margin_report_filed"

    def test_missing_event_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.missing_event_sequence()
        assert len(seq) == 1
        assert seq[0]["event_type"] == "irrelevant_event"

    def test_duplicate_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.duplicate_event_sequence()
        assert len(seq) == 2
        types = [e["event_type"] for e in seq]
        assert types.count("margin_report_filed") == 2

    def test_out_of_order_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.out_of_order_sequence()
        assert len(seq) == 2
        assert seq[0]["timestamp"] > seq[1]["timestamp"]

    def test_multi_event_compliant(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.multi_event_compliant()
        assert len(seq) == 2
        assert seq[0]["event_type"] == "trade_executed"
        assert seq[1]["event_type"] == "margin_report_filed"

    def test_multi_event_late(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.multi_event_late(late_days=5)
        assert len(seq) == 2
        assert seq[0]["event_type"] == "trade_executed"
        assert seq[1]["event_type"] == "margin_report_filed"

    def test_empty_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        assert TelemetryGenerator.empty_sequence() == []

    def test_custom_sequence(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        seq = TelemetryGenerator.custom_sequence([
            {"event_type": "evt_a", "offset_minutes": 0},
            {"event_type": "evt_b", "offset_minutes": 60},
        ])
        assert len(seq) == 2
        assert seq[0]["event_type"] == "evt_a"
        assert seq[1]["event_type"] == "evt_b"

    def test_deterministic(self):
        from app.utils.telemetry_gen import TelemetryGenerator
        s1 = TelemetryGenerator.compliant_sequence("BROKER001")
        s2 = TelemetryGenerator.compliant_sequence("BROKER001")
        assert s1 == s2


# =========================================================================
# Evaluator Functional Tests
# =========================================================================


class TestEvaluateCompliance:
    """Functional tests for the main evaluate_compliance entry point."""

    def test_imports(self):
        from app.pipeline.nodes.evaluator import evaluate_compliance
        assert evaluate_compliance is not None

    def test_empty_locked_fsms(self):
        from app.pipeline.nodes.evaluator import evaluate_compliance
        result = evaluate_compliance([], [])
        assert result == []

    def test_only_pending_fsms_skipped(self):
        """LockedFSMs with PENDING_REVIEW status should be skipped."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm()
        lf = _make_locked_fsm(fsm, status=LockStatus.PENDING_REVIEW)
        result = evaluate_compliance([lf], [])
        assert result == []

    def test_rejected_fsms_skipped(self):
        """LockedFSMs with REJECTED status should be skipped."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm()
        lf = _make_locked_fsm(fsm, status=LockStatus.REJECTED)
        result = evaluate_compliance([lf], [])
        assert result == []

    def test_compliant_single_event(self):
        """FSM reaches terminal state with one matching event."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm()
        lf = _make_locked_fsm(fsm)
        event = _make_telemetry_event()
        result = evaluate_compliance([lf], [event])
        assert len(result) == 1
        v = result[0]
        assert isinstance(v, ComplianceVerdict)
        assert v.status == VerdictStatus.COMPLIANT
        assert v.current_state == "COMPLIANT"
        assert v.obligation_ref == "OBL-001"

    def test_no_events_pending(self):
        """No events → FSM stays in PENDING."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm()
        lf = _make_locked_fsm(fsm)
        result = evaluate_compliance([lf], [])
        assert len(result) == 1
        assert result[0].status == VerdictStatus.PENDING
        assert result[0].current_state == "PENDING"

    def test_irrelevant_event_pending(self):
        """Events that don't match any transition → PENDING."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm()
        lf = _make_locked_fsm(fsm)
        event = _make_telemetry_event(event_type="wrong_event")
        result = evaluate_compliance([lf], [event])
        assert result[0].status == VerdictStatus.PENDING

    def test_multi_step_compliant(self):
        """Two-step FSM with both triggers present."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm(
            fsm_id="FSM-MULTI",
            transitions=[
                ("PENDING", "DUE", "trade_executed"),
                ("DUE", "COMPLIANT", "margin_report_filed"),
            ],
            states=["PENDING", "DUE", "COMPLIANT"],
        )
        lf = _make_locked_fsm(fsm)
        events = [
            _make_telemetry_event(
                event_type="trade_executed",
                timestamp=datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc),
            ),
            _make_telemetry_event(
                event_type="margin_report_filed",
                timestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        result = evaluate_compliance([lf], events)
        assert result[0].status == VerdictStatus.COMPLIANT
        assert result[0].current_state == "COMPLIANT"

    def test_multiple_fsms_independent(self):
        """Each LockedFSM gets its own independent evaluation."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm1 = _make_simple_fsm(fsm_id="FSM-1", obligation_ref="OBL-1")
        fsm2 = _make_simple_fsm(fsm_id="FSM-2", obligation_ref="OBL-2")
        lf1 = _make_locked_fsm(fsm1, locked_fsm_id="LOCKED-1")
        lf2 = _make_locked_fsm(fsm2, locked_fsm_id="LOCKED-2")
        event = _make_telemetry_event()
        result = evaluate_compliance([lf1, lf2], [event])
        assert len(result) == 2
        assert {v.obligation_ref for v in result} == {"OBL-1", "OBL-2"}
        assert all(v.status == VerdictStatus.COMPLIANT for v in result)

    def test_evidence_trail(self):
        """Verdict must include evidence with matched_events and transition_log."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm()
        lf = _make_locked_fsm(fsm)
        events = [
            _make_telemetry_event(
                event_type="wrong_event",
                timestamp=datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc),
            ),
            _make_telemetry_event(
                event_type="margin_report_filed",
                timestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        result = evaluate_compliance([lf], events)
        v = result[0]
        assert "matched_events" in v.evidence
        assert "transition_log" in v.evidence
        assert len(v.evidence["matched_events"]) == 2
        assert v.evidence["matched_events"][0]["matched"] is False
        assert v.evidence["matched_events"][1]["matched"] is True
        assert len(v.evidence["transition_log"]) == 1


# =========================================================================
# Timeline Integration Tests
# =========================================================================


class TestEvaluatorWithTimeline:
    """Tests combining FSM evaluation with timeline rules."""

    def test_timeline_compliant(self):
        """Timeline rule with events within deadline → COMPLIANT."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm(
            fsm_id="FSM-TL",
            states=["PENDING", "COMPLIANT", "LATE"],
            transitions=[("PENDING", "COMPLIANT", "margin_report_filed")],
            timeline_rules=[
                TimelineRule(
                    start_event="trade_executed",
                    deadline_offset=3,
                    grace_period=0,
                    time_unit="days",
                    overdue_transition="LATE",
                )
            ],
        )
        lf = _make_locked_fsm(fsm)
        events = [
            _make_telemetry_event("trade_executed", datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)),
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)),
        ]
        result = evaluate_compliance([lf], events)
        assert result[0].status == VerdictStatus.COMPLIANT

    def test_timeline_late(self):
        """Timeline rule with late events → NON_COMPLIANT."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm(
            fsm_id="FSM-TL-LATE",
            states=["PENDING", "COMPLIANT", "LATE"],
            transitions=[("PENDING", "COMPLIANT", "margin_report_filed")],
            timeline_rules=[
                TimelineRule(
                    start_event="trade_executed",
                    deadline_offset=1,
                    grace_period=0,
                    time_unit="days",
                    overdue_transition="LATE",
                )
            ],
        )
        lf = _make_locked_fsm(fsm)
        events = [
            _make_telemetry_event("trade_executed", datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)),
            # 5 days after reference → past T+1 deadline
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 6, 12, 0, 0, tzinfo=timezone.utc)),
        ]
        result = evaluate_compliance([lf], events)
        assert result[0].status == VerdictStatus.NON_COMPLIANT

    def test_timeline_missing_start_event(self):
        """Timeline rule where start_event never fires → PENDING for
        timeline, but FSM terminal → COMPLIANT."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm(
            fsm_id="FSM-TL-NOSTART",
            states=["PENDING", "COMPLIANT", "LATE"],
            transitions=[("PENDING", "COMPLIANT", "margin_report_filed")],
            timeline_rules=[
                TimelineRule(
                    start_event="trade_executed",
                    deadline_offset=3,
                    time_unit="days",
                    overdue_transition="LATE",
                )
            ],
        )
        lf = _make_locked_fsm(fsm)
        events = [
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)),
        ]
        result = evaluate_compliance([lf], events)
        # FSM terminal + no timeline violation (no start_event) → COMPLIANT
        assert result[0].status == VerdictStatus.COMPLIANT


# =========================================================================
# Edge Case Tests
# =========================================================================


class TestEvaluatorEdgeCases:
    """Edge-case tests: duplicates, out-of-order, missing events."""

    def test_duplicate_events(self):
        """Duplicate events must not cause double transitions."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm()
        lf = _make_locked_fsm(fsm)
        events = [
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)),
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 1, 11, 0, 0, tzinfo=timezone.utc)),
        ]
        result = evaluate_compliance([lf], events)
        v = result[0]
        assert v.status == VerdictStatus.COMPLIANT
        assert len(v.evidence["transition_log"]) == 1  # only 1 transition

    def test_out_of_order_events(self):
        """Events with out-of-order timestamps must be sorted."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_simple_fsm(
            transitions=[
                ("PENDING", "DUE", "trade_executed"),
                ("DUE", "COMPLIANT", "margin_report_filed"),
            ],
            states=["PENDING", "DUE", "COMPLIANT"],
        )
        lf = _make_locked_fsm(fsm)
        # Provided in reverse order
        events = [
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)),
            _make_telemetry_event("trade_executed", datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)),
        ]
        result = evaluate_compliance([lf], events)
        # After sorting: trade_executed → margin_report_filed → COMPLIANT
        assert result[0].status == VerdictStatus.COMPLIANT

    def test_mixed_approved_and_pending(self):
        """Only approved FSMs evaluated; pending/rejected skipped."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm_approved = _make_locked_fsm(
            _make_simple_fsm(fsm_id="FSM-A", obligation_ref="OBL-A"),
            locked_fsm_id="LOCKED-A",
            status=LockStatus.APPROVED,
        )
        fsm_pending = _make_locked_fsm(
            _make_simple_fsm(fsm_id="FSM-P", obligation_ref="OBL-P"),
            locked_fsm_id="LOCKED-P",
            status=LockStatus.PENDING_REVIEW,
        )
        event = _make_telemetry_event()
        result = evaluate_compliance([fsm_approved, fsm_pending], [event])
        assert len(result) == 1
        assert result[0].obligation_ref == "OBL-A"


# =========================================================================
# Determinism Tests
# =========================================================================


class TestEvaluatorDeterminism:
    """Determinism and replay consistency tests."""

    def test_identical_inputs_identical_outputs(self):
        """Same inputs → same verdicts — verified across 10 runs.

        Compares meaningful fields (excludes auto-generated verdict_id and
        evaluated_at which differ by design).
        """
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_locked_fsm(_make_simple_fsm())
        events = [_make_telemetry_event()]

        def _key(v: ComplianceVerdict) -> tuple:
            return (
                v.obligation_ref, v.broker_id, v.fsm_ref,
                v.status, v.current_state,
                str(v.evidence),  # dict → str for hashability
            )

        results = [_key(evaluate_compliance([fsm], events)[0]) for _ in range(10)]
        for i in range(1, 10):
            assert results[i] == results[0], f"Determinism violation at run {i}"

    def test_evidence_identical_every_run(self):
        """Evidence trails must be bit-for-bit identical."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsm = _make_locked_fsm(_make_simple_fsm())
        events = [
            _make_telemetry_event("wrong_event", datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)),
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)),
        ]
        r1 = evaluate_compliance([fsm], events)
        r2 = evaluate_compliance([fsm], events)
        # Compare evidence directly (dicts are deterministic)
        assert r1[0].evidence == r2[0].evidence
        assert r1[0].current_state == r2[0].current_state
        assert r1[0].status == r2[0].status

    def test_complex_deterministic(self):
        """Determinism with multiple FSMs and multiple events."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        fsms = [
            _make_locked_fsm(_make_simple_fsm(
                fsm_id="FSM-1", obligation_ref="OBL-1",
                transitions=[
                    ("PENDING", "DUE", "trade_executed"),
                    ("DUE", "COMPLIANT", "margin_report_filed"),
                ],
                states=["PENDING", "DUE", "COMPLIANT"],
            ), locked_fsm_id="LOCKED-1"),
            _make_locked_fsm(_make_simple_fsm(
                fsm_id="FSM-2", obligation_ref="OBL-2",
            ), locked_fsm_id="LOCKED-2"),
        ]
        events = [
            _make_telemetry_event("trade_executed", datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)),
            _make_telemetry_event("margin_report_filed", datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)),
        ]

        def _key(vs: list[ComplianceVerdict]) -> list[tuple]:
            return [(v.obligation_ref, v.broker_id, v.fsm_ref,
                     v.status, v.current_state, str(v.evidence)) for v in vs]

        r1 = _key(evaluate_compliance(fsms, events))
        r2 = _key(evaluate_compliance(fsms, events))
        assert r1 == r2


# =========================================================================
# Telemetry Generator Tests
# =========================================================================


class TestBrokerScenario:
    """Integration scenarios using the telemetry generator."""

    def test_compliant_scenario_integration(self):
        """FSM + compliant sequence → COMPLIANT."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        from app.utils.telemetry_gen import TelemetryGenerator

        fsm = _make_simple_fsm(
            transitions=[
                ("PENDING", "DUE", "trade_executed"),
                ("DUE", "COMPLIANT", "margin_report_filed"),
            ],
            states=["PENDING", "DUE", "COMPLIANT"],
        )
        lf = _make_locked_fsm(fsm)
        events_dict = TelemetryGenerator.multi_event_compliant()
        events = [_make_telemetry_event(
            broker_id=e["broker_id"],
            event_type=e["event_type"],
            timestamp=e["timestamp"],
        ) for e in events_dict]
        result = evaluate_compliance([lf], events)
        assert result[0].status == VerdictStatus.COMPLIANT

    def test_late_scenario_integration(self):
        """FSM + late sequence → NON_COMPLIANT."""
        from app.pipeline.nodes.evaluator import evaluate_compliance
        from app.utils.telemetry_gen import TelemetryGenerator

        fsm = _make_simple_fsm(
            fsm_id="FSM-TL",
            states=["PENDING", "COMPLIANT", "LATE"],
            transitions=[("PENDING", "COMPLIANT", "margin_report_filed")],
            timeline_rules=[
                TimelineRule(
                    start_event="trade_executed",
                    deadline_offset=3,
                    time_unit="days",
                    overdue_transition="LATE",
                )
            ],
        )
        lf = _make_locked_fsm(fsm)
        events_dict = TelemetryGenerator.multi_event_late(late_days=7)
        events = [_make_telemetry_event(
            broker_id=e["broker_id"],
            event_type=e["event_type"],
            timestamp=e["timestamp"],
        ) for e in events_dict]
        result = evaluate_compliance([lf], events)
        assert result[0].status == VerdictStatus.NON_COMPLIANT


# =========================================================================
# Helpers
# =========================================================================


def _get_evaluator_source() -> str:
    """Read evaluator module source code as a string."""
    from app.pipeline.nodes import evaluator
    return inspect.getsource(evaluator)
