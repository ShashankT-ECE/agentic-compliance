"""
Tests for Node 4: Scoreboard Generator.

The scoreboard generator aggregates ComplianceVerdicts from Node 3
into a Scoreboard with per-broker summaries, compliance rates, and
hash-chain integrity.

These tests cover: aggregation, counts, compliance_rate, evidence_summary,
hash chain integration, edge cases, and determinism.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.scoreboard import BrokerScore, ObligationResult, Scoreboard
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.utils.hash_chain import verify_chain


# =========================================================================
# Fixture helpers
# =========================================================================


def _make_verdict(
    obligation_ref: str = "OBL-001",
    broker_id: str = "BROKER-1",
    fsm_ref: str = "FSM-001",
    status: VerdictStatus = VerdictStatus.COMPLIANT,
    current_state: str = "COMPLIANT",
    evidence: dict | None = None,
) -> ComplianceVerdict:
    """Build a minimal ComplianceVerdict for testing."""
    if evidence is None:
        evidence = {
            "matched_events": [],
            "transition_log": [],
            "timeline_status": [],
        }
    return ComplianceVerdict(
        obligation_ref=obligation_ref,
        broker_id=broker_id,
        fsm_ref=fsm_ref,
        status=status,
        current_state=current_state,
        evidence=evidence,
    )


def _sample_verdicts() -> list[ComplianceVerdict]:
    """Return a realistic mixed set of verdicts across two brokers."""
    return [
        _make_verdict("OBL-001", "BROKER-1", "FSM-001", VerdictStatus.COMPLIANT, "COMPLIANT"),
        _make_verdict("OBL-002", "BROKER-1", "FSM-002", VerdictStatus.COMPLIANT, "COMPLIANT"),
        _make_verdict("OBL-003", "BROKER-1", "FSM-003", VerdictStatus.NON_COMPLIANT, "PENDING"),
        _make_verdict("OBL-004", "BROKER-2", "FSM-004", VerdictStatus.COMPLIANT, "COMPLIANT"),
        _make_verdict("OBL-005", "BROKER-2", "FSM-005", VerdictStatus.PENDING, "PENDING"),
    ]


# =========================================================================
# Import / contract tests
# =========================================================================


class TestGenerateScoreboard:
    """Contract and basic functional tests for generate_scoreboard."""

    def test_imports(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        assert generate_scoreboard is not None

    def test_empty_verdicts(self):
        """Empty verdict list returns empty Scoreboard."""
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard([], "SEBI/2025/57")
        assert isinstance(sb, Scoreboard)
        assert sb.circular_id == "SEBI/2025/57"
        assert sb.broker_summaries == []
        assert sb.hash_chain is None

    def test_single_verdict(self):
        """Single verdict produces single-broker Scoreboard."""
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict()
        sb = generate_scoreboard([v], "SEBI/2025/57")
        assert len(sb.broker_summaries) == 1
        assert sb.circular_id == "SEBI/2025/57"
        assert sb.broker_summaries[0].broker_id == "BROKER-1"

    def test_returns_scoreboard_type(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard([_make_verdict()], "SEBI/2025/57")
        assert isinstance(sb, Scoreboard)
        assert sb.scoreboard_id.startswith("SB-")
        assert isinstance(sb.generated_at, datetime)

    def test_circular_id_propagated(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard([_make_verdict()], "SEBI/HO/MIRSD/2025/57")
        assert sb.circular_id == "SEBI/HO/MIRSD/2025/57"

    def test_metadata_present(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard(
            [_make_verdict()], "SEBI/2025/57",
            metadata={"run_id": "RUN-001", "version": "1.0"},
        )
        assert sb.metadata == {"run_id": "RUN-001", "version": "1.0"}

    def test_no_metadata_defaults_to_empty_dict(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard([_make_verdict()], "SEBI/2025/57")
        assert sb.metadata == {}


# =========================================================================
# Aggregation / counting tests
# =========================================================================


class TestScoreboardAggregation:
    """Tests for per-broker aggregation and compliance rate computation."""

    def test_all_compliant_rate_is_one(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-001", "B1", status=VerdictStatus.COMPLIANT),
            _make_verdict("OBL-002", "B1", status=VerdictStatus.COMPLIANT),
            _make_verdict("OBL-003", "B1", status=VerdictStatus.COMPLIANT),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        bs = sb.broker_summaries[0]
        assert bs.total_obligations == 3
        assert bs.compliant == 3
        assert bs.non_compliant == 0
        assert bs.pending == 0
        assert bs.compliance_rate == 1.0

    def test_all_non_compliant_rate_is_zero(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-001", "B1", status=VerdictStatus.NON_COMPLIANT),
            _make_verdict("OBL-002", "B1", status=VerdictStatus.NON_COMPLIANT),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        bs = sb.broker_summaries[0]
        assert bs.compliant == 0
        assert bs.non_compliant == 2
        assert bs.compliance_rate == 0.0

    def test_mixed_rate(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-001", "B1", status=VerdictStatus.COMPLIANT),
            _make_verdict("OBL-002", "B1", status=VerdictStatus.COMPLIANT),
            _make_verdict("OBL-003", "B1", status=VerdictStatus.NON_COMPLIANT),
            _make_verdict("OBL-004", "B1", status=VerdictStatus.PENDING),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        bs = sb.broker_summaries[0]
        assert bs.total_obligations == 4
        assert bs.compliant == 2
        assert bs.non_compliant == 1
        assert bs.pending == 1
        # rate = 2 / (4 - 1) = 2/3 ≈ 0.6667
        assert bs.compliance_rate == round(2 / 3, 4)

    def test_all_pending_rate_is_one(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-001", "B1", status=VerdictStatus.PENDING),
            _make_verdict("OBL-002", "B1", status=VerdictStatus.PENDING),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        bs = sb.broker_summaries[0]
        assert bs.compliant == 0
        assert bs.pending == 2
        assert bs.compliance_rate == 1.0  # all pending → 1.0

    def test_counts_are_consistent(self):
        """BrokerScore model validators enforce count consistency."""
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-001", "B1", status=VerdictStatus.COMPLIANT),
            _make_verdict("OBL-002", "B1", status=VerdictStatus.NON_COMPLIANT),
            _make_verdict("OBL-003", "B1", status=VerdictStatus.PENDING),
            _make_verdict("OBL-004", "B2", status=VerdictStatus.COMPLIANT),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        for bs in sb.broker_summaries:
            assert bs.compliant + bs.non_compliant + bs.pending == bs.total_obligations
            assert len(bs.obligation_details) == bs.total_obligations

    def test_brokers_sorted_alphabetically(self):
        """Broker scores must be sorted by broker_id for determinism."""
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-001", "Z-BROKER"),
            _make_verdict("OBL-002", "A-BROKER"),
            _make_verdict("OBL-003", "M-BROKER"),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        broker_ids = [bs.broker_id for bs in sb.broker_summaries]
        assert broker_ids == sorted(broker_ids)


# =========================================================================
# Multi-broker tests
# =========================================================================


class TestMultiBroker:
    """Tests with verdicts from multiple brokers."""

    def test_two_brokers(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard(_sample_verdicts(), "SEBI/2025/57")
        assert len(sb.broker_summaries) == 2
        assert {bs.broker_id for bs in sb.broker_summaries} == {"BROKER-1", "BROKER-2"}

    def test_broker1_counts(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard(_sample_verdicts(), "SEBI/2025/57")
        b1 = next(bs for bs in sb.broker_summaries if bs.broker_id == "BROKER-1")
        assert b1.total_obligations == 3
        assert b1.compliant == 2
        assert b1.non_compliant == 1
        assert b1.pending == 0

    def test_broker2_counts(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard(_sample_verdicts(), "SEBI/2025/57")
        b2 = next(bs for bs in sb.broker_summaries if bs.broker_id == "BROKER-2")
        assert b2.total_obligations == 2
        assert b2.compliant == 1
        assert b2.pending == 1

    def test_each_broker_has_details(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard(_sample_verdicts(), "SEBI/2025/57")
        for bs in sb.broker_summaries:
            assert len(bs.obligation_details) == bs.total_obligations

    def test_five_brokers(self):
        """Five brokers with one verdict each."""
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict(f"OBL-{i}", f"BROKER-{i}", status=VerdictStatus.COMPLIANT)
            for i in range(1, 6)
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        assert len(sb.broker_summaries) == 5
        for bs in sb.broker_summaries:
            assert bs.compliance_rate == 1.0


# =========================================================================
# ObligationResult mapping tests
# =========================================================================


class TestObligationResults:
    """Tests for correct ObligationResult creation from ComplianceVerdicts."""

    def test_result_refs_match_verdict(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict("OBL-XYZ", "B1", "FSM-XYZ", VerdictStatus.COMPLIANT)
        sb = generate_scoreboard([v], "SEBI/2025/57")
        result = sb.broker_summaries[0].obligation_details[0]
        assert result.obligation_ref == "OBL-XYZ"
        assert result.fsm_ref == "FSM-XYZ"
        assert result.status == VerdictStatus.COMPLIANT

    def test_result_current_state(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict(current_state="COMPLIANT")
        sb = generate_scoreboard([v], "SEBI/2025/57")
        assert sb.broker_summaries[0].obligation_details[0].current_state == "COMPLIANT"

    def test_result_evaluated_at(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict()
        sb = generate_scoreboard([v], "SEBI/2025/57")
        result = sb.broker_summaries[0].obligation_details[0]
        assert isinstance(result.evaluated_at, datetime)

    def test_evidence_summary_with_matches(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict(evidence={
            "matched_events": [
                {"event_index": 0, "event_type": "e1", "matched": True},
                {"event_index": 1, "event_type": "e2", "matched": False},
                {"event_index": 2, "event_type": "e3", "matched": True},
            ],
            "transition_log": [{"source": "PENDING", "target": "COMPLIANT"}],
            "timeline_status": [],
        })
        sb = generate_scoreboard([v], "SEBI/2025/57")
        summary = sb.broker_summaries[0].obligation_details[0].evidence_summary
        assert "2/3 events matched" in summary
        assert "1 transitions" in summary

    def test_evidence_summary_with_timeline(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict(evidence={
            "matched_events": [],
            "transition_log": [],
            "timeline_status": [
                {"start_event_matched": True, "deadline_met": True},
                {"start_event_matched": True, "deadline_met": False},
                {"start_event_matched": False, "deadline_met": None},
            ],
        })
        sb = generate_scoreboard([v], "SEBI/2025/57")
        summary = sb.broker_summaries[0].obligation_details[0].evidence_summary
        assert "deadline_met" in summary
        assert "deadline_missed" in summary
        assert "start_event_not_matched" in summary

    def test_evidence_summary_empty(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict(evidence={})
        sb = generate_scoreboard([v], "SEBI/2025/57")
        summary = sb.broker_summaries[0].obligation_details[0].evidence_summary
        assert "0/0 events matched" in summary
        assert "0 transitions" in summary


# =========================================================================
# Hash chain integration tests
# =========================================================================


class TestHashChainIntegration:
    """Tests for hash chain construction and verification."""

    def test_chain_built_for_non_empty_scoreboard(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard([_make_verdict()], "SEBI/2025/57")
        assert sb.hash_chain is not None
        assert sb.hash_chain.length >= 1

    def test_chain_verifies(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard(_sample_verdicts(), "SEBI/2025/57")
        assert verify_chain(sb.hash_chain) is True

    def test_chain_root_hash_deterministic(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = _sample_verdicts()
        sb1 = generate_scoreboard(vs, "SEBI/2025/57")
        sb2 = generate_scoreboard(vs, "SEBI/2025/57")
        assert sb1.hash_chain.root_hash == sb2.hash_chain.root_hash

    def test_different_verdicts_different_root(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb1 = generate_scoreboard(
            [_make_verdict("OBL-001", status=VerdictStatus.COMPLIANT)],
            "SEBI/2025/57",
        )
        sb2 = generate_scoreboard(
            [_make_verdict("OBL-001", status=VerdictStatus.NON_COMPLIANT)],
            "SEBI/2025/57",
        )
        assert sb1.hash_chain.root_hash != sb2.hash_chain.root_hash

    def test_chain_length_matches_broker_count(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-001", "B1"),
            _make_verdict("OBL-002", "B2"),
            _make_verdict("OBL-003", "B3"),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        assert sb.hash_chain.length == 3


# =========================================================================
# Edge case tests
# =========================================================================


class TestScoreboardEdgeCases:
    """Edge-case and resilience tests."""

    def test_single_broker_single_verdict(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard([_make_verdict()], "SEBI/2025/57")
        assert sb.broker_summaries[0].total_obligations == 1

    def test_verdicts_from_same_broker_unsorted(self):
        """Verdicts from the same broker in non-deterministic order
        should still produce the same scoreboard."""
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict("OBL-003", "B1", status=VerdictStatus.PENDING),
            _make_verdict("OBL-001", "B1", status=VerdictStatus.COMPLIANT),
            _make_verdict("OBL-002", "B1", status=VerdictStatus.NON_COMPLIANT),
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        bs = sb.broker_summaries[0]
        assert bs.total_obligations == 3
        assert bs.compliant == 1
        assert bs.non_compliant == 1
        assert bs.pending == 1

    def test_same_status_different_obligations(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = [
            _make_verdict(f"OBL-{i:03d}", status=VerdictStatus.COMPLIANT)
            for i in range(50)
        ]
        sb = generate_scoreboard(vs, "SEBI/2025/57")
        assert sb.broker_summaries[0].compliant == 50
        assert sb.broker_summaries[0].compliance_rate == 1.0

    def test_missing_evidence_field_survives(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        v = _make_verdict(evidence={"matched_events": []})
        sb = generate_scoreboard([v], "SEBI/2025/57")
        summary = sb.broker_summaries[0].obligation_details[0].evidence_summary
        # missing transition_log and timeline_status should default gracefully
        assert "0/0 events matched" in summary

    def test_zero_verdicts_hash_chain_is_none(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        sb = generate_scoreboard([], "SEBI/2025/57")
        assert sb.hash_chain is None
        assert sb.broker_summaries == []


# =========================================================================
# Determinism tests
# =========================================================================


class TestScoreboardDeterminism:
    """Tests for deterministic scoreboard output."""

    def test_same_verdicts_same_root_hash(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = _sample_verdicts()
        roots = [
            generate_scoreboard(vs, "SEBI/2025/57").hash_chain.root_hash
            for _ in range(10)
        ]
        assert all(r == roots[0] for r in roots)

    def test_same_verdicts_same_rates(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = _sample_verdicts()
        r1 = generate_scoreboard(vs, "SEBI/2025/57")
        r2 = generate_scoreboard(vs, "SEBI/2025/57")
        for bs1, bs2 in zip(r1.broker_summaries, r2.broker_summaries):
            assert bs1.broker_id == bs2.broker_id
            assert bs1.compliance_rate == bs2.compliance_rate
            assert bs1.compliant == bs2.compliant
            assert bs1.non_compliant == bs2.non_compliant
            assert bs1.pending == bs2.pending

    def test_same_verdicts_same_evidence_summaries(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        vs = _sample_verdicts()
        r1 = generate_scoreboard(vs, "SEBI/2025/57")
        r2 = generate_scoreboard(vs, "SEBI/2025/57")
        s1 = [o.evidence_summary for bs in r1.broker_summaries for o in bs.obligation_details]
        s2 = [o.evidence_summary for bs in r2.broker_summaries for o in bs.obligation_details]
        assert s1 == s2

    def test_chain_verified_every_run(self):
        from app.pipeline.nodes.scoreboard import generate_scoreboard
        for _ in range(5):
            sb = generate_scoreboard(_sample_verdicts(), "SEBI/2025/57")
            assert verify_chain(sb.hash_chain) is True
