"""
Integration tests for M9 — full compliance pipeline end-to-end.

Validates the complete demo flow:
  sample_circular.pdf → Parser → FSM Extractor → HITL Gate
  → Approval/Rejection/Amendment → Evaluator → Scoreboard
  → Report Generation → Hash Chain Verification

All tests use fixtures from Phase 1 and a MultiMockLLMClient that
returns distinct canned responses for parser and FSM extraction,
eliminating the need for a real LLM API key at test time.

Node 3 (Evaluator) and Node 4 (Scoreboard) run with full deterministic
logic — no mocking of compliance decisions.
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.fsm import HybridFSM
from app.models.locked_fsm import LockedFSM, LockStatus
from app.models.obligation import ObligationClause
from app.models.scoreboard import HashChain, Scoreboard
from app.models.telemetry import TelemetryEvent
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.utils.hash_chain import verify_chain
from app.utils.llm_client import LLMClient, MockLLMClient

# =============================================================================
# Canned LLM responses for the demo pipeline
# =============================================================================

PARSER_RESPONSE = json.dumps([
    {
        "clause_id": "CIRC-2025-057-CL-01",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        "clause_text": "The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
        "obligation_type": "timeline",
        "timeline_params": {"offset": 1, "grace_period": 0, "unit": "days"},
        "effective_date": "2025-04-28",
        "applicable_entities": ["trading_member", "clearing_member"],
    },
    {
        "clause_id": "CIRC-2025-057-CL-02",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        "clause_text": "The TMs/CMs in cash segment are required to mandatorily collect upfront VaR margins and ELM from their clients in advance of trade.",
        "obligation_type": "timeline",
        "timeline_params": {"offset": 0, "grace_period": 0, "unit": "days"},
        "effective_date": "2025-04-28",
        "applicable_entities": ["trading_member", "clearing_member"],
    },
])

FSM_RESPONSE = json.dumps([
    {
        "obligation_ref": "CIRC-2025-057-CL-01",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        "states": [
            {"name": "PENDING", "description": "Trade executed; margin collection window open"},
            {"name": "DUE", "description": "Settlement day approaching"},
            {"name": "COMPLIANT", "description": "Margins collected by settlement day"},
            {"name": "LATE", "description": "Settlement day passed without full margin collection"},
            {"name": "NON_COMPLIANT", "description": "Penalty assessed for non-collection"},
        ],
        "initial_state": "PENDING",
        "transitions": [
            {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "margin_report_filed", "conditions": None},
            {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "trade_executed", "conditions": None},
            {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "margin_report_filed", "conditions": None},
            {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
        ],
        "timeline_rules": [
            {"start_event": "trade_executed", "deadline_offset": 1, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
        ],
        "metadata": {"clause_text": "...", "obligation_type": "timeline"},
    },
    {
        "obligation_ref": "CIRC-2025-057-CL-02",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
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
            {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "trade_executed", "conditions": None},
            {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "var_margin_collected", "conditions": {"timing": "advance_of_trade"}},
            {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
        ],
        "timeline_rules": [
            {"start_event": "trade_executed", "deadline_offset": 0, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
        ],
        "metadata": {"clause_text": "...", "obligation_type": "timeline"},
    },
])

CIRCULAR_REF = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"


# =============================================================================
# Multi-response mock LLM client
# =============================================================================


class MultiMockLLMClient(LLMClient):
    """Returns canned responses in order — first call gets parser response,
    second call gets FSM response, etc.  Tracks calls for test assertions.
    """

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self, system_prompt: str, user_message: str, *, temperature: float = 0.1,
    ) -> str:
        if self._idx >= len(self._responses):
            raise RuntimeError(
                f"MultiMockLLMClient exhausted after {len(self._responses)} "
                f"response(s) — call {self._idx + 1} has no canned response."
            )
        self.calls.append({
            "system_prompt": system_prompt[:200],
            "user_message": user_message[:200],
            "temperature": temperature,
        })
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


# =============================================================================
# Helpers
# =============================================================================

# ---------------------------------------------------------------------------
# Test isolation — redirect all runtime data writes to temporary directories
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _redirect_test_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all runtime data writes to temporary directories.

    Integration tests must never write to ``backend/data/``.  This fixture
    monkeypatches the module-level data directory constants in the HITL gate,
    FSM extractor, and pipeline API routes so every ``persist_*()`` call and
    disk read goes to a per-test temp directory.
    """
    locked_dir = tmp_path / "locked_fsms"
    locked_dir.mkdir(exist_ok=True)
    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir(exist_ok=True)

    monkeypatch.setattr("app.pipeline.nodes.hitl_gate._LOCKED_DATA_DIR", locked_dir)
    monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", locked_dir)
    monkeypatch.setattr("app.pipeline.nodes.fsm_extractor._EXTRACTED_DATA_DIR", extracted_dir)

    # tmp_path is auto-cleaned by pytest when the test function ends


# Default data directory for locked FSMs (same as pipeline routes default)
def _reset_all_stores() -> None:
    """Reset all in-memory stores before a test."""
    from app.pipeline.runner import _set_store
    from app.api.routes.telemetry import _set_telemetry_store
    from app.api.routes.reports import _set_report_store
    _set_store({})
    _set_telemetry_store({})
    _set_report_store({})


def _make_approved_fsm(locked_fsm: LockedFSM, reviewer: str = "tester") -> LockedFSM:
    """Return a copy of *locked_fsm* with status=APPROVED and integrity fields set."""
    from app.utils.hash_chain import compute_hash, link, _serialize

    fsm = deepcopy(locked_fsm)
    fsm.status = LockStatus.APPROVED
    fsm.reviewer = reviewer
    fsm.reviewed_at = datetime.now(timezone.utc)

    fsm_json = fsm.original_fsm.model_dump_json(exclude_none=True)
    data_hash = compute_hash(fsm_json)
    fsm.integrity_hash = data_hash

    # Build a hash link using the proper API
    prev = locked_fsm.hash_link  # may be None for PENDING_REVIEW
    if prev is not None:
        # Use the previous link to chain
        hl = link(prev, {"original_fsm_hash": data_hash, "reviewer": reviewer})
    else:
        # No previous link — create a standalone genesis-style link
        from app.models.scoreboard import HashLink as HL
        preimage = f"0{data_hash}{'0' * 64}"
        hl = HL(
            index=0,
            data_hash=data_hash,
            previous_hash="0" * 64,
            link_hash=compute_hash(preimage),
        )
    fsm.hash_link = hl
    return fsm


def _load_locked_fsms_from_disk(run_id: str) -> list[LockedFSM]:
    """Load LockedFSM records persisted to disk for a pipeline run.

    The HITL gate writes LockedFSMs to the module-level ``_LOCKED_DATA_DIR``
    (``backend/data/locked_fsms/{run_id}/``).  We load from the same
    directory — no test-specific override.
    """
    from app.pipeline.nodes.hitl_gate import load_locked_fsms, _LOCKED_DATA_DIR
    return load_locked_fsms(run_id, data_dir=_LOCKED_DATA_DIR)


def _make_genesis_link(fsm: HybridFSM) -> "HashLink":
    """Build a genesis hash link for a single FSM."""
    from app.utils.hash_chain import compute_hash
    data_hash = compute_hash(fsm.model_dump_json(exclude_none=True))
    preimage = f"0{data_hash}{'0' * 64}"
    from app.models.scoreboard import HashLink as HL
    return HL(
        index=0,
        data_hash=data_hash,
        previous_hash="0" * 64,
        link_hash=compute_hash(preimage),
    )


# =============================================================================
# Full pipeline happy path (headless mode)
# =============================================================================


class TestFullPipelineHappyPath:
    """End-to-end pipeline: PDF → Obligations → FSMs → Verdicts → Scoreboard."""

    @pytest.mark.asyncio
    async def test_full_headless_pipeline(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Run the complete pipeline in headless mode with pre-approved FSMs."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        # Parser + FSM Extractor assertions
        assert state.circular_id == CIRCULAR_REF
        assert len(state.obligation_clauses) == 2
        assert state.obligation_clauses[0].obligation_type.value == "timeline"
        assert len(state.extracted_fsms) == 2
        assert state.status.value == "awaiting_approval"

        # LockedFSMs are on disk, NOT in state
        locked = _load_locked_fsms_from_disk(state.run_id)
        assert len(locked) == 2
        assert all(f.status == LockStatus.PENDING_REVIEW for f in locked)

        approved_fsms = [_make_approved_fsm(f) for f in locked]

        # Resume: evaluator → scoreboard
        final_state = await runner.resume(state.run_id, approved_fsms)

        assert final_state is not None
        assert final_state.status.value == "completed"

        # Verdicts — at least one per approved FSM
        verdicts = final_state.compliance_verdicts
        assert len(verdicts) > 0
        assert len(verdicts) >= len(locked), (
            f"Expected ≥ {len(locked)} verdicts (1 per FSM), got {len(verdicts)}"
        )

        # Scoreboard
        scoreboard = final_state.scoreboard
        assert scoreboard is not None
        assert scoreboard.circular_id == CIRCULAR_REF
        assert len(scoreboard.broker_summaries) > 0

        sb_brokers = {b.broker_id for b in scoreboard.broker_summaries}
        verdict_brokers = {v.broker_id for v in verdicts}
        assert sb_brokers == verdict_brokers

        # Hash chain
        chain = scoreboard.hash_chain
        assert chain is not None
        assert chain.length > 0
        assert verify_chain(chain)

        # LLM called exactly twice
        assert len(llm.calls) == 2

    def test_parser_node_deterministic_with_same_input(self, demo_circular_text: str):
        """Parser produces identical output given identical input."""
        async def _run():
            from app.pipeline.nodes.parser import parse_circular
            c1 = await parse_circular(demo_circular_text, CIRCULAR_REF, MockLLMClient(response=PARSER_RESPONSE))
            c2 = await parse_circular(demo_circular_text, CIRCULAR_REF, MockLLMClient(response=PARSER_RESPONSE))
            assert len(c1) == len(c2)
            for a, b in zip(c1, c2):
                assert a.clause_id == b.clause_id
            return True
        assert asyncio.run(_run())

    def test_evaluator_is_deterministic(
        self, demo_circular_text: str, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Evaluator produces identical verdicts for identical inputs."""
        from app.pipeline.nodes.evaluator import evaluate_compliance

        async def _run():
            from app.pipeline.nodes.parser import parse_circular
            from app.pipeline.nodes.fsm_extractor import extract_fsms

            clauses = await parse_circular(demo_circular_text, CIRCULAR_REF, MockLLMClient(response=PARSER_RESPONSE))
            fsms = await extract_fsms(clauses, CIRCULAR_REF, MockLLMClient(response=FSM_RESPONSE))
            assert len(fsms) == 2

            # Wrap HybridFSMs in approved LockedFSMs for the evaluator
            locked = [
                LockedFSM(
                    fsm_id=f.fsm_id,
                    obligation_ref=f.obligation_ref,
                    circular_ref=f.circular_ref,
                    version=1,
                    original_fsm=f,
                    status=LockStatus.APPROVED,
                    reviewer="tester",
                    reviewed_at=datetime.now(timezone.utc),
                    integrity_hash="a" * 64,
                    hash_link=_make_genesis_link(f),
                )
                for f in fsms
            ]

            v1 = evaluate_compliance(locked, list(demo_telemetry_events))
            v2 = evaluate_compliance(locked, list(demo_telemetry_events))

            assert len(v1) == len(v2)
            sorter = lambda x: (x.broker_id, x.obligation_ref)
            for a, b in zip(sorted(v1, key=sorter), sorted(v2, key=sorter)):
                assert a.status == b.status, f"{a.broker_id}/{a.obligation_ref}"
                assert a.broker_id == b.broker_id
            return True
        assert asyncio.run(_run())

    def test_node_3_has_no_llm_imports(self):
        """Safety gate: evaluator module must never import or reference an LLM."""
        import ast
        evaluator_path = (
            Path(__file__).resolve().parent.parent
            / "app" / "pipeline" / "nodes" / "evaluator.py"
        )
        source = evaluator_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                module = getattr(node, "module", "") or ""
                full = module + " " + " ".join(names)
                assert "llm" not in full.lower(), f"LLM reference found: {full.strip()}"
                assert "openai" not in full.lower(), f"OpenAI reference found: {full.strip()}"


# =============================================================================
# HITL pause / resume flow
# =============================================================================


class TestHitlPauseResume:
    """Pipeline starts, pauses at HITL gate, resumes after human approval."""

    @pytest.mark.asyncio
    async def test_pipeline_pauses_at_hitl(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """After start(), the pipeline must be in AWAITING_APPROVAL status."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        assert state.status.value == "awaiting_approval"
        assert len(state.extracted_fsms) == 2

        # LockedFSMs are on disk
        locked = _load_locked_fsms_from_disk(state.run_id)
        assert len(locked) == 2
        assert all(f.status == LockStatus.PENDING_REVIEW for f in locked)

        # Verdicts must be empty — evaluator hasn't run yet
        assert len(state.compliance_verdicts) == 0

    @pytest.mark.asyncio
    async def test_resume_after_approval_completes_pipeline(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Approve all FSMs, resume, and verify the pipeline reaches COMPLETED."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f, reviewer="compliance-officer") for f in locked]
        for f in approved:
            assert f.status == LockStatus.APPROVED
            assert f.integrity_hash is not None

        final_state = await runner.resume(state.run_id, approved)

        assert final_state.status.value == "completed"
        assert len(final_state.compliance_verdicts) > 0
        assert final_state.scoreboard is not None

    @pytest.mark.asyncio
    async def test_pipeline_state_persists_across_pause(self, demo_circular_path: Path):
        """Pipeline state is retrievable from the store across the pause boundary."""
        from app.pipeline.runner import PipelineRunner, get_run_state
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
        )

        retrieved = get_run_state(state.run_id)
        assert retrieved is not None
        assert retrieved.run_id == state.run_id
        assert retrieved.status.value == "awaiting_approval"
        assert len(retrieved.obligation_clauses) == 2
        assert len(retrieved.extracted_fsms) == 2


# =============================================================================
# HITL rejection flow
# =============================================================================


class TestHitlRejection:
    """Rejecting an FSM removes it from the evaluator input."""

    @pytest.mark.asyncio
    async def test_rejected_fsms_not_evaluated(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """When FSM-1 is rejected, only FSM-2 reaches the evaluator."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        locked = _load_locked_fsms_from_disk(state.run_id)
        assert len(locked) == 2

        # Reject the first, approve the second
        rejected = locked[0]
        rejected.status = LockStatus.REJECTED
        rejected.reviewer = "compliance-officer"
        rejected.reviewed_at = datetime.now(timezone.utc)
        rejected.review_comments = "FSM does not accurately reflect the obligation."

        approved_fsm = _make_approved_fsm(locked[1], reviewer="compliance-officer")

        # Resume with only the approved FSM
        final_state = await runner.resume(state.run_id, [approved_fsm])

        assert final_state.status.value == "completed"
        verdicts = final_state.compliance_verdicts
        approved_refs = {v.fsm_ref for v in verdicts}
        assert approved_fsm.fsm_id in approved_refs
        assert rejected.fsm_id not in approved_refs

    def test_rejection_requires_comments(self):
        """LockedFSM validation enforces review_comments on rejection."""
        from app.models.fsm import FSMState

        fsm = HybridFSM(
            fsm_id="FSM-TEST",
            obligation_ref="OBL-001",
            circular_ref=CIRCULAR_REF,
            initial_state="PENDING",
            states=[
                FSMState(name="PENDING"),
                FSMState(name="DUE"),
                FSMState(name="COMPLIANT"),
                FSMState(name="LATE"),
                FSMState(name="NON_COMPLIANT"),
            ],
            transitions=[
                {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "evt"},
                {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "evt2"},
                {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline"},
            ],
            timeline_rules=[
                {"start_event": "evt", "deadline_offset": 1, "time_unit": "days", "overdue_transition": "LATE"},
            ],
        )

        # Valid rejection with comments
        LockedFSM(
            fsm_id=fsm.fsm_id,
            obligation_ref=fsm.obligation_ref,
            circular_ref=fsm.circular_ref,
            version=1,
            original_fsm=fsm,
            status=LockStatus.REJECTED,
            reviewer="tester",
            reviewed_at=datetime.now(timezone.utc),
            review_comments="The obligation interpretation is incorrect.",
        )

        # Invalid rejection without comments
        with pytest.raises(Exception):
            LockedFSM(
                fsm_id=fsm.fsm_id,
                obligation_ref=fsm.obligation_ref,
                circular_ref=fsm.circular_ref,
                version=1,
                original_fsm=fsm,
                status=LockStatus.REJECTED,
                reviewer="tester",
                reviewed_at=datetime.now(timezone.utc),
                review_comments="",
            )


# =============================================================================
# HITL amendment flow
# =============================================================================


class TestHitlAmendment:
    """Amending an FSM preserves amendment history and uses the corrected FSM."""

    @pytest.mark.asyncio
    async def test_amended_fsm_used_in_evaluation(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """An amended FSM's correction is what the evaluator sees."""
        from app.pipeline.nodes.hitl_gate import amend_fsm, build_hitl_hash_chain
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        locked = _load_locked_fsms_from_disk(state.run_id)
        target = locked[0]
        original_fsm_id = target.fsm_id

        # Amend: add a new transition
        amended_fsm_dict = target.original_fsm.model_dump(mode="json")
        amended_fsm_dict["transitions"].append({
            "from_state": "DUE",
            "to_state": "NON_COMPLIANT",
            "trigger_event": "penalty_imposed",
            "conditions": None,
        })
        corrected_fsm = HybridFSM.model_validate(amended_fsm_dict)

        chain = build_hitl_hash_chain(locked)
        previous = chain.last_link

        amended = amend_fsm(
            locked_fsm=target,
            corrected_fsm=corrected_fsm,
            reviewer="compliance-officer",
            comments="Added penalty transition for completeness.",
            previous_hash_link=previous,
        )

        assert amended.status == LockStatus.AMENDED
        assert amended.version == 2
        assert len(amended.amendment_history) == 1
        assert amended.amendment_history[0].amended_by == "compliance-officer"
        assert amended.original_fsm.fsm_id == original_fsm_id

        transition_events = [t.trigger_event for t in amended.original_fsm.transitions]
        assert "penalty_imposed" in transition_events

        # Resume with the amended FSM + the other approved FSM
        approved_other = _make_approved_fsm(locked[1], reviewer="compliance-officer")
        final_state = await runner.resume(state.run_id, [amended, approved_other])

        assert final_state.status.value == "completed"

    def test_amended_fsm_preserves_prior(self):
        """Amendment history records the original FSM before the change."""
        from app.pipeline.nodes.hitl_gate import amend_fsm, build_hitl_hash_chain
        from app.models.fsm import FSMState

        original = HybridFSM(
            fsm_id="FSM-AMEND-TEST",
            obligation_ref="OBL-001",
            circular_ref=CIRCULAR_REF,
            initial_state="PENDING",
            states=[
                FSMState(name="PENDING"),
                FSMState(name="DUE"),
                FSMState(name="COMPLIANT"),
                FSMState(name="LATE"),
                FSMState(name="NON_COMPLIANT"),
            ],
            transitions=[
                {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "evt"},
                {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "evt2"},
                {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline"},
            ],
            timeline_rules=[
                {"start_event": "evt", "deadline_offset": 1, "time_unit": "days", "overdue_transition": "LATE"},
            ],
        )

        lf = LockedFSM(
            fsm_id=original.fsm_id,
            obligation_ref=original.obligation_ref,
            circular_ref=original.circular_ref,
            version=1,
            original_fsm=original,
        )

        corrected = HybridFSM(
            fsm_id=original.fsm_id,
            obligation_ref=original.obligation_ref,
            circular_ref=original.circular_ref,
            initial_state="PENDING",
            states=[
                FSMState(name="PENDING"),
                FSMState(name="DUE"),
                FSMState(name="COMPLIANT"),
                FSMState(name="LATE"),
                FSMState(name="NON_COMPLIANT"),
                FSMState(name="UNDER_REVIEW", description="Added for internal review"),
            ],
            transitions=[
                {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "evt"},
                {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "evt2"},
                {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline"},
                {"from_state": "LATE", "to_state": "UNDER_REVIEW", "trigger_event": "review_triggered"},
                {"from_state": "UNDER_REVIEW", "to_state": "NON_COMPLIANT", "trigger_event": "review_complete"},
            ],
            timeline_rules=[
                {"start_event": "evt", "deadline_offset": 1, "time_unit": "days", "overdue_transition": "LATE"},
            ],
        )

        chain = build_hitl_hash_chain([lf])
        previous = chain.last_link

        amended = amend_fsm(
            locked_fsm=lf,
            corrected_fsm=corrected,
            reviewer="reviewer-1",
            comments="Added UNDER_REVIEW state.",
            previous_hash_link=previous,
        )

        assert amended.version == 2
        assert len(amended.amendment_history) == 1
        hist = amended.amendment_history[0]
        assert hist.version == 1
        assert hist.prior_fsm.fsm_id == original.fsm_id
        assert "UNDER_REVIEW" not in {s.name for s in hist.prior_fsm.states}
        assert "UNDER_REVIEW" in {s.name for s in amended.original_fsm.states}


# =============================================================================
# Hash chain verification
# =============================================================================


class TestHashChainVerification:
    """End-to-end hash chain integrity across the full pipeline."""

    @pytest.mark.asyncio
    async def test_scoreboard_hash_chain_verifies(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """The scoreboard's hash chain must verify after a full pipeline run."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f) for f in locked]
        final_state = await runner.resume(state.run_id, approved)

        chain = final_state.scoreboard.hash_chain  # type: ignore[union-attr]
        assert chain is not None
        assert chain.length >= len(final_state.scoreboard.broker_summaries)  # type: ignore[union-attr]
        assert verify_chain(chain), "Hash chain must verify end-to-end"

        # Tampered chain must NOT verify
        tampered = deepcopy(chain)
        if tampered.chain:
            tampered.chain[-1].link_hash = "f" * 64
        assert not verify_chain(tampered), "Tampered chain must fail verification"

    def test_hash_chain_tamper_detection_every_attack(self):
        """Test multiple tampering vectors — each must be detected."""
        from app.utils.hash_chain import build_chain

        chain = build_chain([{"id": i} for i in range(3)])
        assert verify_chain(chain)

        # Attack 1: Modify data hash
        c1 = deepcopy(chain)
        c1.chain[1].data_hash = "a" * 64
        assert not verify_chain(c1), "Data tampering undetected"

        # Attack 2: Modify link hash
        c2 = deepcopy(chain)
        c2.chain[0].link_hash = "b" * 64
        assert not verify_chain(c2), "Link tampering undetected"

        # Attack 3: Remove a link
        c3 = deepcopy(chain)
        c3.chain.pop(1)
        assert not verify_chain(c3), "Missing link undetected"

        # Attack 4: Reorder links
        c4 = deepcopy(chain)
        if len(c4.chain) >= 2:
            c4.chain[0], c4.chain[1] = c4.chain[1], c4.chain[0]
        assert not verify_chain(c4), "Reordered links undetected"

    def test_root_hash_deterministic(self):
        """Same data produces the same root hash every time."""
        from app.utils.hash_chain import build_chain
        r1 = build_chain([{"id": 1}]).root_hash
        r2 = build_chain([{"id": 1}]).root_hash
        assert r1 == r2, "Root hash must be deterministic"

    def test_different_data_different_root(self):
        """Different genesis data produces different root hashes."""
        from app.utils.hash_chain import build_chain
        c1 = build_chain([{"id": 1}])
        c2 = build_chain([{"id": 2}])
        # First (and only) link hashes different data → different link_hash → different root
        assert c1.root_hash != c2.root_hash


# =============================================================================
# Report generation
# =============================================================================


class TestReportGeneration:
    """Compliance report generation from completed pipeline runs."""

    @pytest.fixture(autouse=True)
    def setup(self):
        _reset_all_stores()

    def _client(self):
        from app.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_report_generated_from_completed_run(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Generate a report from a completed run and verify its contents."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f) for f in locked]
        await runner.resume(state.run_id, approved)

        # Generate report via API
        client = self._client()
        r = client.get(f"/api/reports/generate/{state.run_id}")
        assert r.status_code == 200
        data = r.json()
        assert "report_id" in data
        assert data["run_id"] == state.run_id
        assert data["circular_id"] == CIRCULAR_REF

        report_id = data["report_id"]

        # Retrieve the report
        r2 = client.get(f"/api/reports/{report_id}")
        assert r2.status_code == 200
        report = r2.json()
        assert report["report_id"] == report_id
        assert report["run_id"] == state.run_id

        # Summary
        summary = report["summary"]
        assert summary["total_verdicts"] > 0
        assert "compliant" in summary
        assert "non_compliant" in summary
        assert summary["total_verdicts"] == (
            summary["compliant"] + summary["non_compliant"] + summary["pending"]
        )

        # Verdicts
        assert len(report["verdicts"]) == summary["total_verdicts"]

        # Scoreboard
        assert report["scoreboard"] is not None
        assert len(report["scoreboard"]["broker_summaries"]) > 0

    def test_report_generation_fails_for_incomplete_run(self):
        """Cannot generate a report for a run that hasn't completed."""
        from app.pipeline.state import CompliancePipelineState, PipelineStatus
        from app.pipeline.runner import RunRecord, _get_store
        _reset_all_stores()

        state = CompliancePipelineState(run_id="run-in-progress", circular_id=CIRCULAR_REF)
        state.status = PipelineStatus.AWAITING_APPROVAL
        _get_store()["run-in-progress"] = RunRecord(state=state)

        r = self._client().get("/api/reports/generate/run-in-progress")
        assert r.status_code == 400

    def test_report_not_found_returns_404(self):
        r = self._client().get("/api/reports/RPT-NONEXISTENT")
        assert r.status_code == 404


# =============================================================================
# Telemetry ingest and query integration
# =============================================================================


class TestTelemetryIntegration:
    """End-to-end telemetry ingest + query against the API."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from app.api.routes.telemetry import _set_telemetry_store
        _set_telemetry_store({})

    def _client(self):
        from app.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_ingest_and_query_demo_fixture(self, demo_telemetry_records: list[dict[str, Any]]):
        """Ingest the full demo telemetry fixture and verify query results."""
        client = self._client()

        r = client.post("/api/telemetry/ingest", json={"events": demo_telemetry_records})
        assert r.status_code == 201
        data = r.json()
        assert data["ingested"] == len(demo_telemetry_records)
        assert data["rejected"] == 0

        r2 = client.get("/api/telemetry/query?limit=50")
        assert r2.status_code == 200
        qdata = r2.json()
        assert qdata["total"] == len(demo_telemetry_records)
        assert len(qdata["events"]) == len(demo_telemetry_records)

    def test_query_filters_work_on_demo_data(self, demo_telemetry_records: list[dict[str, Any]]):
        """Broker and event-type filters correctly narrow results."""
        client = self._client()
        client.post("/api/telemetry/ingest", json={"events": demo_telemetry_records})

        r = client.get("/api/telemetry/query?broker_id=BROKER-COMPLIANT&limit=50")
        data = r.json()
        assert data["total"] == 4  # BROKER-COMPLIANT has 4 events

        r2 = client.get("/api/telemetry/query?event_type=margin_report_filed&limit=50")
        assert r2.json()["total"] == 2  # 2 margin_report_filed events

        r3 = client.get("/api/telemetry/query?broker_id=BROKER-LATE&event_type=payin_made&limit=50")
        assert r3.json()["total"] == 1

    def test_ingest_with_default_broker_id(self):
        """Events without broker_id inherit the request-level default."""
        client = self._client()
        r = client.post("/api/telemetry/ingest", json={
            "events": [{"event_type": "test_event", "timestamp": "2026-06-01T09:00:00Z"}],
            "broker_id": "DEFAULT-BROKER",
        })
        assert r.status_code == 201
        assert r.json()["ingested"] == 1

        r2 = client.get("/api/telemetry/query?limit=10")
        assert r2.json()["events"][0]["broker_id"] == "DEFAULT-BROKER"

    def test_validation_errors_reported(self):
        """Invalid events are rejected individually with clear error messages."""
        client = self._client()
        r = client.post("/api/telemetry/ingest", json={
            "events": [
                {"broker_id": "B-OK", "event_type": "evt", "timestamp": "2026-06-01T09:00:00Z"},
                {"broker_id": "", "event_type": "", "timestamp": "not-a-date"},
                {"broker_id": "B-ALSO-OK", "event_type": "evt2", "timestamp": "2026-06-01T10:00:00Z"},
            ],
        })
        data = r.json()
        assert data["ingested"] == 2
        assert data["rejected"] == 1

    def test_pagination_on_demo_data(self, demo_telemetry_records: list[dict[str, Any]]):
        """Pagination (limit + offset) works correctly on demo data."""
        client = self._client()
        client.post("/api/telemetry/ingest", json={"events": demo_telemetry_records})

        r1 = client.get("/api/telemetry/query?limit=4&offset=0")
        d1 = r1.json()
        assert d1["total"] == 10
        assert len(d1["events"]) == 4

        r2 = client.get("/api/telemetry/query?limit=4&offset=4")
        assert len(r2.json()["events"]) == 4

        r3 = client.get("/api/telemetry/query?limit=4&offset=8")
        assert len(r3.json()["events"]) == 2

        ids_p1 = {e["event_id"] for e in d1["events"]}
        ids_p2 = {e["event_id"] for e in r2.json()["events"]}
        ids_p3 = {e["event_id"] for e in r3.json()["events"]}
        assert ids_p1.isdisjoint(ids_p2)
        assert ids_p1.isdisjoint(ids_p3)
        assert ids_p2.isdisjoint(ids_p3)


# =============================================================================
# Data integrity — evidence trails and scoreboard correctness
# =============================================================================


class TestDataIntegrity:
    """Verify evidence trails, scoreboard consistency, and auditability."""

    @pytest.mark.asyncio
    async def test_every_verdict_has_evidence(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Every compliance verdict must include an evidence trail."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )
        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f) for f in locked]
        final_state = await runner.resume(state.run_id, approved)

        for verdict in final_state.compliance_verdicts:
            assert verdict.evidence is not None
            assert "matched_events" in verdict.evidence
            assert "transition_log" in verdict.evidence

    @pytest.mark.asyncio
    async def test_scoreboard_counts_match_verdicts(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Scoreboard per-broker totals must match the actual verdict counts."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )
        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f) for f in locked]
        final_state = await runner.resume(state.run_id, approved)

        scoreboard = final_state.scoreboard
        assert scoreboard is not None

        expected: dict[str, dict[str, int]] = {}
        for v in final_state.compliance_verdicts:
            bid = v.broker_id
            if bid not in expected:
                expected[bid] = {"total": 0, "compliant": 0, "non_compliant": 0, "pending": 0}
            expected[bid]["total"] += 1
            s = str(v.status.value)
            if s in expected[bid]:
                expected[bid][s] += 1

        for broker in scoreboard.broker_summaries:
            exp = expected.get(broker.broker_id)
            assert exp is not None
            assert broker.total_obligations == exp["total"]
            assert broker.compliant == exp["compliant"]
            assert broker.non_compliant == exp["non_compliant"]

    @pytest.mark.asyncio
    async def test_verdicts_traceable_to_circular(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Every verdict must be traceable to the originating obligation and circular."""
        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )
        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f) for f in locked]
        final_state = await runner.resume(state.run_id, approved)

        fsm_to_obligation: dict[str, str] = {}
        for fsm in state.extracted_fsms:
            fsm_to_obligation[fsm.fsm_id] = fsm.obligation_ref

        for verdict in final_state.compliance_verdicts:
            assert verdict.obligation_ref
            assert verdict.fsm_ref
            assert verdict.fsm_ref in fsm_to_obligation
            assert verdict.obligation_ref == fsm_to_obligation[verdict.fsm_ref]


# Re‑export PipelineRunner so tests don't need to import it separately
from app.pipeline.runner import PipelineRunner


# =============================================================================
# Helper — minimal valid HybridFSM for _count_fsms tests
# =============================================================================


def _make_minimal_fsm() -> HybridFSM:
    """Build a minimal but valid HybridFSM with all 5 canonical states."""
    from app.models.fsm import FSMState, FSMTransition, TimelineRule

    return HybridFSM(
        fsm_id="FSM-TEST",
        obligation_ref="CIRC-001",
        circular_ref="SEBI-TEST",
        states=[
            FSMState(name="PENDING", description="Start"),
            FSMState(name="DUE", description="Due"),
            FSMState(name="COMPLIANT", description="Done"),
            FSMState(name="LATE", description="Late"),
            FSMState(name="NON_COMPLIANT", description="Failed"),
        ],
        initial_state="PENDING",
        transitions=[
            FSMTransition(from_state="PENDING", to_state="DUE", trigger_event="start", conditions=None),
            FSMTransition(from_state="DUE", to_state="COMPLIANT", trigger_event="submit", conditions=None),
            FSMTransition(from_state="DUE", to_state="LATE", trigger_event="deadline", conditions=None),
            FSMTransition(from_state="LATE", to_state="NON_COMPLIANT", trigger_event="grace_expired", conditions=None),
        ],
        timeline_rules=[
            TimelineRule(start_event="start", deadline_offset=1, grace_period=0, time_unit="days", overdue_transition="LATE"),
        ],
        metadata={},
    )


# =============================================================================
# M9 Regression — V1 interactive demo fixes
# =============================================================================


class TestResumeEndpoint:
    """Regression tests for the POST /api/pipeline/{run_id}/resume endpoint (RC #2)."""

    @pytest.mark.asyncio
    async def test_resume_endpoint_returns_200(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Resume endpoint should return 200 after all FSMs are approved."""
        from fastapi.testclient import TestClient
        from app.main import app

        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)
        from app.api.deps import set_runner
        set_runner(runner)

        # Trigger pipeline via runner
        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        # Approve all FSMs on disk
        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f) for f in locked]
        from app.pipeline.nodes.hitl_gate import persist_locked_fsms
        persist_locked_fsms(approved, state.run_id)

        # Resume via the new endpoint
        client = TestClient(app)
        resp = client.post(f"/api/pipeline/{state.run_id}/resume")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["run_id"] == state.run_id
        assert data["status"] == "completed"
        assert data["verdict_count"] > 0

    @pytest.mark.asyncio
    async def test_resume_endpoint_rejects_pending_fsms(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Resume endpoint should return 400 when FSMs are still pending."""
        from fastapi.testclient import TestClient
        from app.main import app

        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)
        from app.api.deps import set_runner
        set_runner(runner)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        # Don't approve any FSMs — all should still be pending

        client = TestClient(app)
        resp = client.post(f"/api/pipeline/{state.run_id}/resume")
        assert resp.status_code == 400
        assert "still pending review" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_resume_endpoint_merges_telemetry(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Telemetry ingested via API should be merged before evaluation (RC #7)."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api.routes.telemetry import _get_telemetry_store

        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)
        from app.api.deps import set_runner
        set_runner(runner)

        # Trigger with NO telemetry
        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=[],
        )

        # Ingest telemetry separately via the global store
        tstore = _get_telemetry_store()
        for ev in demo_telemetry_events:
            tstore.setdefault(ev.broker_id, []).append(ev)

        # Approve all FSMs
        locked = _load_locked_fsms_from_disk(state.run_id)
        approved = [_make_approved_fsm(f) for f in locked]
        from app.pipeline.nodes.hitl_gate import persist_locked_fsms
        persist_locked_fsms(approved, state.run_id)

        # Resume — should merge telemetry from global store
        client = TestClient(app)
        resp = client.post(f"/api/pipeline/{state.run_id}/resume")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verdict_count"] > 0


class TestStatusFix:
    """Regression tests for get_pipeline_status returning correct FSM counts (RC #5, #6)."""

    @pytest.mark.asyncio
    async def test_status_shows_correct_fsm_counts_during_awaiting_approval(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Status endpoint must show FSM counts from disk when awaiting approval."""
        from fastapi.testclient import TestClient
        from app.main import app

        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)
        from app.api.deps import set_runner
        set_runner(runner)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        client = TestClient(app)
        resp = client.get(f"/api/pipeline/status/{state.run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_fsms"] > 0, f"Expected positive total_fsms, got {data['total_fsms']}"
        assert data["pending"] > 0, f"Expected positive pending, got {data['pending']}"


class TestHitlListFix:
    """Regression tests for list_hitl_runs scanning disk (RC #4)."""

    @pytest.mark.asyncio
    async def test_hitl_list_without_run_id_includes_disk_runs(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """HITL list without run_id should find runs from disk."""
        from fastapi.testclient import TestClient
        from app.main import app

        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)
        from app.api.deps import set_runner
        set_runner(runner)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        client = TestClient(app)
        resp = client.get("/api/pipeline/hitl")
        assert resp.status_code == 200
        data = resp.json()
        ids = [r["run_id"] for r in data["runs"]]
        assert state.run_id in ids, (
            f"Expected {state.run_id} in HITL list, got {ids}"
        )

    @pytest.mark.asyncio
    async def test_hitl_list_excludes_deleted_runs(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Deleting a run from disk must remove it from the HITL queue."""
        from fastapi.testclient import TestClient
        from app.main import app

        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)
        from app.api.deps import set_runner
        set_runner(runner)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        client = TestClient(app)

        # Confirm the run appears
        resp = client.get("/api/pipeline/hitl")
        ids = [r["run_id"] for r in resp.json()["runs"]]
        assert state.run_id in ids

        # Delete the run directory from disk
        from app.api.routes.pipeline import _get_data_dir
        import shutil
        run_dir = _get_data_dir() / state.run_id
        assert run_dir.exists()
        shutil.rmtree(run_dir)
        assert not run_dir.exists()

        # HITL list must no longer include the deleted run
        resp = client.get("/api/pipeline/hitl")
        ids_after = [r["run_id"] for r in resp.json()["runs"]]
        assert state.run_id not in ids_after, (
            f"Deleted run {state.run_id} still appears in HITL list: {ids_after}"
        )

    @pytest.mark.asyncio
    async def test_hitl_list_ignores_empty_directories(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Empty or orphaned directories must not appear in the HITL list."""
        from app.api.routes.pipeline import _get_data_dir

        # Create an empty directory (no LOCKED-*.json files)
        empty_dir = _get_data_dir() / "orphaned-empty-dir"
        empty_dir.mkdir(parents=True, exist_ok=True)
        try:
            from fastapi.testclient import TestClient
            from app.main import app

            _reset_all_stores()

            llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
            runner = PipelineRunner(llm_client=llm)
            from app.api.deps import set_runner
            set_runner(runner)

            await runner.start(
                circular_path=str(demo_circular_path),
                circular_id=CIRCULAR_REF,
                telemetry_events=list(demo_telemetry_events),
            )

            client = TestClient(app)
            resp = client.get("/api/pipeline/hitl")
            ids = [r["run_id"] for r in resp.json()["runs"]]
            assert "orphaned-empty-dir" not in ids, (
                f"Empty directory appears in HITL list: {ids}"
            )
        finally:
            import shutil
            shutil.rmtree(empty_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_hitl_list_excludes_fully_approved_runs(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Runs with zero pending obligations must not appear in the HITL list."""
        from fastapi.testclient import TestClient
        from app.main import app

        _reset_all_stores()

        llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
        runner = PipelineRunner(llm_client=llm)
        from app.api.deps import set_runner
        set_runner(runner)

        state = await runner.start(
            circular_path=str(demo_circular_path),
            circular_id=CIRCULAR_REF,
            telemetry_events=list(demo_telemetry_events),
        )

        client = TestClient(app)

        # Approve all FSMs
        locked = _load_locked_fsms_from_disk(state.run_id)
        for lfsm in locked:
            approved = _make_approved_fsm(lfsm)
            from app.pipeline.nodes.hitl_gate import persist_locked_fsms
            persist_locked_fsms([approved], state.run_id)

        # Now re-count pending from files — should be 0
        resp = client.get("/api/pipeline/hitl")
        ids = [r["run_id"] for r in resp.json()["runs"]]
        # After _pipeline_state.json is stale, the fix re-counts from file statuses
        # All approved means no pending, so run should drop from list
        assert state.run_id not in ids, (
            f"Fully approved run should NOT appear in HITL list, got: {ids}"
        )

    @pytest.mark.asyncio
    async def test_hitl_list_is_disk_authoritative(
        self, demo_circular_path: Path, demo_telemetry_events: list[TelemetryEvent],
    ):
        """Stale in-memory runs must NOT leak into the HITL list."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.pipeline.runner import _set_store, RunRecord
        from app.pipeline.state import CompliancePipelineState, PipelineStatus

        # Seed the in-memory store with a fake run that has NO disk counterpart
        _reset_all_stores()
        from datetime import datetime, timezone
        fake_state = CompliancePipelineState(
            run_id="stale-memory-only-run",
            circular_id="STALE-CIRCULAR",
            telemetry_events=[],
            metadata={"started_at": datetime.now(timezone.utc).isoformat()},
        )
        fake_state.status = PipelineStatus.AWAITING_APPROVAL
        _set_store({
            "stale-memory-only-run": RunRecord(
                state=fake_state,
                created_at=datetime.now(timezone.utc).isoformat(),
            ),
        })

        client = TestClient(app)
        resp = client.get("/api/pipeline/hitl")
        ids = [r["run_id"] for r in resp.json()["runs"]]
        assert "stale-memory-only-run" not in ids, (
            f"Stale in-memory run leaked into HITL list: {ids}"
        )


class TestCountFsmsFix:
    """Regression tests for _count_fsms() using .value instead of str() (RC #6)."""

    def test_count_fsms_counts_correctly(self):
        """_count_fsms must correctly count by status.value."""
        from app.api.routes.pipeline import _count_fsms
        from app.models.locked_fsm import LockedFSM, LockStatus
        from app.models.fsm import FSMState, FSMTransition, HybridFSM, TimelineRule

        # Build a minimal but valid FSM with all 5 canonical states
        fsm = _make_minimal_fsm()
        pending = LockedFSM(
            fsm_id="FSM-TEST",
            obligation_ref="CIRC-001",
            circular_ref="SEBI-TEST",
            version=1,
            original_fsm=fsm,
            status=LockStatus.PENDING_REVIEW,
        )
        approved = pending.model_copy(deep=True)
        approved.status = LockStatus.APPROVED
        rejected = pending.model_copy(deep=True)
        rejected.status = LockStatus.REJECTED
        amended = pending.model_copy(deep=True)
        amended.status = LockStatus.AMENDED

        counts = _count_fsms([pending, approved, rejected, amended])
        assert counts == {"pending": 1, "approved": 1, "rejected": 1, "amended": 1}

    def test_count_fsms_all_pending(self):
        """All-pending should return correct counts."""
        from app.api.routes.pipeline import _count_fsms
        from app.models.locked_fsm import LockedFSM, LockStatus

        fsm1 = _make_minimal_fsm()  # fsm_id="FSM-TEST"
        fsm2_data = _make_minimal_fsm().model_dump()
        fsm2_data["fsm_id"] = "FSM-TEST2"
        fsm2_data["obligation_ref"] = "CIRC-002"
        from app.models.fsm import HybridFSM
        fsm2 = HybridFSM.model_validate(fsm2_data)

        locked = [
            LockedFSM(fsm_id="FSM-TEST", obligation_ref="CIRC-001", circular_ref="SEBI-TEST", version=1, original_fsm=fsm1, status=LockStatus.PENDING_REVIEW),
            LockedFSM(fsm_id="FSM-TEST2", obligation_ref="CIRC-002", circular_ref="SEBI-TEST", version=1, original_fsm=fsm2, status=LockStatus.PENDING_REVIEW),
        ]
        counts = _count_fsms(locked)
        assert counts["pending"] == 2
        assert counts["approved"] == 0
