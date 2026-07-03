"""
Model validation tests for M0 data structures.

Tests every Pydantic model with representative data to ensure:
  - Valid data parses without error
  - Field validators catch invalid data
  - Default values are applied correctly
  - Model constraints (min_length, ge, patterns) are enforced
"""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.fsm import CANONICAL_STATES, FSMState, FSMTransition, HybridFSM, TimelineRule
from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.models.scoreboard import BrokerScore, HashChain, HashLink, ObligationResult, Scoreboard
from app.models.telemetry import BrokerInfo, TelemetryEvent
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.pipeline.state import CompliancePipelineState, PipelineError, PipelineStatus
from app.utils.hash_chain import build_chain, compute_hash, link, verify_chain


# ====================================================================
# Obligation models
# ====================================================================


class TestTimelineParams:
    """Tests for TimelineParams."""

    def test_valid_timeline_params(self):
        tp = TimelineParams(offset=1, grace_period=0, unit="days")
        assert tp.offset == 1
        assert tp.grace_period == 0
        assert tp.unit == "days"

    def test_default_unit_is_days(self):
        tp = TimelineParams(offset=3)
        assert tp.unit == "days"
        assert tp.grace_period == 0

    def test_offset_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            TimelineParams(offset=-1)

    def test_grace_period_defaults_to_zero(self):
        tp = TimelineParams(offset=5)
        assert tp.grace_period == 0

    def test_invalid_unit_rejected(self):
        with pytest.raises(ValidationError):
            TimelineParams(offset=1, unit="weeks")


class TestObligationClause:
    """Tests for ObligationClause."""

    def test_valid_timeline_clause(self):
        clause = ObligationClause(
            clause_id="CIRC-2024-001-CL-03",
            circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
            clause_text="Stock brokers shall submit margin reports within T+1 day of trade execution.",
            obligation_type=ObligationType.TIMELINE,
            timeline_params=TimelineParams(offset=1, grace_period=0, unit="days"),
            effective_date=date(2024, 6, 15),
            applicable_entities=["stock_broker", "clearing_member"],
        )
        assert clause.obligation_type == ObligationType.TIMELINE
        assert clause.timeline_params.offset == 1

    def test_timeline_clause_requires_timeline_params(self):
        with pytest.raises(ValidationError, match="timeline_params is required"):
            ObligationClause(
                clause_id="CIRC-2024-001-CL-03",
                circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
                clause_text="Stock brokers shall submit margin reports within T+1 day of trade execution.",
                obligation_type=ObligationType.TIMELINE,
            )

    def test_threshold_clause_without_timeline_params(self):
        """Threshold and procedure types should not require timeline_params."""
        clause = ObligationClause(
            clause_id="CIRC-2024-001-CL-05",
            circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
            clause_text="Brokers must maintain minimum net worth of INR 1 crore.",
            obligation_type=ObligationType.THRESHOLD,
        )
        assert clause.timeline_params is None

    def test_clause_id_pattern_enforced(self):
        with pytest.raises(ValidationError):
            ObligationClause(
                clause_id="clause with spaces",
                circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
                clause_text="Stock brokers shall submit margin reports.",
                obligation_type=ObligationType.THRESHOLD,
            )

    def test_clause_text_min_length(self):
        with pytest.raises(ValidationError, match="String should have at least 10 characters"):
            ObligationClause(
                clause_id="CIRC-2024-001-CL-03",
                circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
                clause_text="Short",
                obligation_type=ObligationType.THRESHOLD,
            )

    def test_empty_circular_ref_rejected(self):
        with pytest.raises(ValidationError, match="circular_ref must not be empty"):
            ObligationClause(
                clause_id="CIRC-2024-001-CL-03",
                circular_ref="   ",
                clause_text="Stock brokers shall submit margin reports.",
                obligation_type=ObligationType.THRESHOLD,
            )

    def test_minimal_valid_clause(self):
        """A threshold clause with minimal required fields."""
        clause = ObligationClause(
            clause_id="CIRC-001-CL-01",
            circular_ref="SEBI/CIR/2024/001",
            clause_text="Brokers must maintain adequate records for 5 years.",
            obligation_type=ObligationType.PROCEDURE,
        )
        assert clause.applicable_entities == []
        assert clause.effective_date is None


# ====================================================================
# Telemetry models
# ====================================================================


class TestBrokerInfo:
    """Tests for BrokerInfo."""

    def test_valid_broker_info(self):
        broker = BrokerInfo(
            broker_id="B-12345",
            name="ABC Securities Pvt Ltd",
            registration_number="INZ000001234",
        )
        assert broker.broker_id == "B-12345"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            BrokerInfo(
                broker_id="B-12345",
                name="",
                registration_number="INZ000001234",
            )

    def test_broker_id_pattern_enforced(self):
        with pytest.raises(ValidationError):
            BrokerInfo(
                broker_id="broker with spaces!",
                name="ABC Securities",
                registration_number="INZ000001234",
            )


class TestTelemetryEvent:
    """Tests for TelemetryEvent."""

    def test_valid_event(self):
        event = TelemetryEvent(
            broker_id="B-12345",
            event_type="margin_report_filed",
            timestamp=datetime(2026, 7, 1, 9, 30, 0, tzinfo=timezone.utc),
            payload={"report_id": "MR-001", "filing_date": "2026-07-01"},
        )
        assert event.broker_id == "B-12345"
        assert event.event_type == "margin_report_filed"

    def test_event_id_auto_generated(self):
        event = TelemetryEvent(
            broker_id="B-12345",
            event_type="trade_executed",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.event_id  # auto-generated UUID
        assert len(event.event_id) > 0

    def test_event_id_explicit(self):
        event = TelemetryEvent(
            event_id="EVT-001",
            broker_id="B-12345",
            event_type="trade_settled",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.event_id == "EVT-001"

    def test_empty_event_type_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryEvent(
                broker_id="B-12345",
                event_type="",
                timestamp=datetime.now(timezone.utc),
            )

    def test_payload_defaults_to_empty_dict(self):
        event = TelemetryEvent(
            broker_id="B-12345",
            event_type="client_onboarded",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.payload == {}


# ====================================================================
# FSM models
# ====================================================================


class TestFSMState:
    """Tests for FSMState."""

    def test_valid_state(self):
        state = FSMState(name="PENDING", description="Obligation period has begun")
        assert state.name == "PENDING"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            FSMState(name="")

    def test_description_defaults_to_empty(self):
        state = FSMState(name="COMPLIANT")
        assert state.description == ""


class TestFSMTransition:
    """Tests for FSMTransition."""

    def test_valid_transition(self):
        t = FSMTransition(
            from_state="PENDING",
            to_state="COMPLIANT",
            trigger_event="margin_report_filed",
        )
        assert t.from_state == "PENDING"
        assert t.to_state == "COMPLIANT"

    def test_same_state_transition_rejected(self):
        with pytest.raises(ValidationError, match="must differ"):
            FSMTransition(
                from_state="PENDING",
                to_state="PENDING",
                trigger_event="noop",
            )

    def test_conditions_optional(self):
        t = FSMTransition(
            from_state="DUE",
            to_state="COMPLIANT",
            trigger_event="report_filed",
            conditions={"report_type": "daily"},
        )
        assert t.conditions == {"report_type": "daily"}


class TestTimelineRule:
    """Tests for TimelineRule."""

    def test_valid_rule(self):
        rule = TimelineRule(
            start_event="trade_executed",
            deadline_offset=1,
            grace_period=0,
            time_unit="days",
        )
        assert rule.start_event == "trade_executed"
        assert rule.deadline_offset == 1
        assert rule.overdue_transition == "LATE"

    def test_deadline_offset_non_negative(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            TimelineRule(start_event="evt", deadline_offset=-1)

    def test_custom_overdue_transition(self):
        rule = TimelineRule(
            start_event="settlement_due",
            deadline_offset=3,
            overdue_transition="NON_COMPLIANT",
        )
        assert rule.overdue_transition == "NON_COMPLIANT"

    def test_invalid_time_unit_rejected(self):
        with pytest.raises(ValidationError):
            TimelineRule(start_event="evt", deadline_offset=1, time_unit="years")


class TestHybridFSM:
    """Tests for HybridFSM."""

    @pytest.fixture
    def minimal_states(self) -> list[FSMState]:
        return [
            FSMState(name="PENDING"),
            FSMState(name="COMPLIANT"),
            FSMState(name="LATE"),
            FSMState(name="NON_COMPLIANT"),
        ]

    @pytest.fixture
    def minimal_transitions(self) -> list[FSMTransition]:
        return [
            FSMTransition(from_state="PENDING", to_state="COMPLIANT", trigger_event="report_filed"),
            FSMTransition(from_state="PENDING", to_state="LATE", trigger_event="deadline_elapsed"),
            FSMTransition(from_state="LATE", to_state="NON_COMPLIANT", trigger_event="grace_expired"),
        ]

    def test_valid_hybrid_fsm(self, minimal_states, minimal_transitions):
        fsm = HybridFSM(
            obligation_ref="CIRC-2024-001-CL-03",
            circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
            states=minimal_states,
            initial_state="PENDING",
            transitions=minimal_transitions,
            timeline_rules=[
                TimelineRule(start_event="trade_executed", deadline_offset=1),
            ],
            metadata={"confidence": 0.95},
        )
        assert fsm.initial_state == "PENDING"
        assert fsm.fsm_id.startswith("FSM-")
        assert fsm.state_names == {"PENDING", "COMPLIANT", "LATE", "NON_COMPLIANT"}
        assert fsm.is_valid_canonical is True

    def test_initial_state_not_in_states_rejected(self, minimal_states, minimal_transitions):
        with pytest.raises(ValidationError, match="initial_state"):
            HybridFSM(
                obligation_ref="CIRC-2024-001-CL-03",
                circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
                states=minimal_states,
                initial_state="NONEXISTENT",
                transitions=minimal_transitions,
            )

    def test_transition_to_nonexistent_state_rejected(self, minimal_states):
        with pytest.raises(ValidationError, match="not found in FSM states"):
            HybridFSM(
                obligation_ref="CIRC-2024-001-CL-03",
                circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
                states=minimal_states,
                initial_state="PENDING",
                transitions=[
                    FSMTransition(from_state="PENDING", to_state="NOWHERE", trigger_event="evt"),
                ],
            )

    def test_timeline_rule_overdue_target_invalid(self, minimal_states):
        with pytest.raises(ValidationError, match="not found in FSM states"):
            HybridFSM(
                obligation_ref="CIRC-2024-001-CL-03",
                circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
                states=minimal_states,
                initial_state="PENDING",
                timeline_rules=[
                    TimelineRule(
                        start_event="evt", deadline_offset=1, overdue_transition="NOWHERE"
                    ),
                ],
            )

    def test_terminal_states_property(self, minimal_states, minimal_transitions):
        fsm = HybridFSM(
            obligation_ref="CIRC-2024-001-CL-03",
            circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
            states=minimal_states,
            initial_state="PENDING",
            transitions=minimal_transitions,
        )
        # COMPLIANT and NON_COMPLIANT have no outgoing transitions
        assert "COMPLIANT" in fsm.terminal_states
        assert "NON_COMPLIANT" in fsm.terminal_states

    def test_non_canonical_states(self):
        """FSM with non-canonical state names should report is_valid_canonical=False."""
        fsm = HybridFSM(
            obligation_ref="CIRC-2024-001-CL-03",
            circular_ref="SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001",
            states=[FSMState(name="START"), FSMState(name="END")],
            initial_state="START",
        )
        assert fsm.is_valid_canonical is False

    def test_empty_obligation_ref_rejected(self):
        with pytest.raises(ValidationError, match="obligation_ref must not be empty"):
            HybridFSM(
                obligation_ref="   ",
                circular_ref="SEBI/HO/MIRSD/2024/001",
                states=[FSMState(name="PENDING"), FSMState(name="COMPLIANT")],
                initial_state="PENDING",
            )

    def test_minimum_states_enforced(self):
        with pytest.raises(ValidationError, match="List should have at least 2 items"):
            HybridFSM(
                obligation_ref="CL-001",
                circular_ref="SEBI/CIR/2024/001",
                states=[FSMState(name="PENDING")],
                initial_state="PENDING",
            )

    def test_fsm_id_auto_generated(self, minimal_states):
        fsm = HybridFSM(
            obligation_ref="CIRC-2024-001-CL-03",
            circular_ref="SEBI/HO/MIRSD/2024/001",
            states=minimal_states,
            initial_state="PENDING",
        )
        assert fsm.fsm_id.startswith("FSM-")
        assert len(fsm.fsm_id) == 16  # "FSM-" + 12 hex chars


# ====================================================================
# Verdict models
# ====================================================================


class TestVerdictStatus:
    """Tests for VerdictStatus enum."""

    def test_all_statuses_exist(self):
        assert VerdictStatus.COMPLIANT.value == "compliant"
        assert VerdictStatus.NON_COMPLIANT.value == "non_compliant"
        assert VerdictStatus.PENDING.value == "pending"


class TestComplianceVerdict:
    """Tests for ComplianceVerdict."""

    def test_valid_compliant_verdict(self):
        verdict = ComplianceVerdict(
            obligation_ref="CIRC-2024-001-CL-03",
            broker_id="B-12345",
            fsm_ref="FSM-A1B2C3D4E5F6",
            status=VerdictStatus.COMPLIANT,
            current_state="COMPLIANT",
            evidence={
                "matched_events": [
                    {"event_id": "EVT-001", "transition": "PENDING→COMPLIANT", "timestamp": "2026-07-01T09:30:00Z"},
                ],
                "timeline_status": {"deadline": "2026-07-02T00:00:00Z", "met": True},
                "transition_log": ["PENDING → COMPLIANT"],
            },
            evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
        )
        assert verdict.status == VerdictStatus.COMPLIANT
        assert verdict.is_final is True

    def test_pending_verdict_is_not_final(self):
        verdict = ComplianceVerdict(
            obligation_ref="CIRC-2024-001-CL-03",
            broker_id="B-12345",
            fsm_ref="FSM-A1B2C3D4E5F6",
            status=VerdictStatus.PENDING,
            current_state="PENDING",
        )
        assert verdict.is_final is False

    def test_verdict_id_auto_generated(self):
        verdict = ComplianceVerdict(
            obligation_ref="CIRC-2024-001-CL-03",
            broker_id="B-12345",
            fsm_ref="FSM-A1B2C3D4E5F6",
            status=VerdictStatus.COMPLIANT,
            current_state="COMPLIANT",
        )
        assert verdict.verdict_id.startswith("VER-")

    def test_evaluated_at_defaults_to_now(self):
        verdict = ComplianceVerdict(
            obligation_ref="CIRC-2024-001-CL-03",
            broker_id="B-12345",
            fsm_ref="FSM-A1B2C3D4E5F6",
            status=VerdictStatus.COMPLIANT,
            current_state="COMPLIANT",
        )
        assert verdict.evaluated_at is not None

    def test_evidence_defaults_to_empty_dict(self):
        verdict = ComplianceVerdict(
            obligation_ref="CIRC-2024-001-CL-03",
            broker_id="B-12345",
            fsm_ref="FSM-A1B2C3D4E5F6",
            status=VerdictStatus.COMPLIANT,
            current_state="COMPLIANT",
        )
        assert verdict.evidence == {}


# ====================================================================
# Scoreboard models
# ====================================================================


class TestHashLink:
    """Tests for HashLink."""

    def test_valid_hash_link(self):
        link = HashLink(
            index=0,
            data_hash="a" * 64,
            previous_hash="0" * 64,
            link_hash="b" * 64,
        )
        assert link.index == 0
        assert len(link.data_hash) == 64

    def test_hash_length_enforced(self):
        with pytest.raises(ValidationError):
            HashLink(
                index=0,
                data_hash="too_short",
                previous_hash="0" * 64,
                link_hash="b" * 64,
            )

    def test_index_non_negative(self):
        with pytest.raises(ValidationError):
            HashLink(
                index=-1,
                data_hash="a" * 64,
                previous_hash="0" * 64,
                link_hash="b" * 64,
            )


class TestHashChain:
    """Tests for HashChain."""

    def test_empty_chain(self):
        chain = HashChain(root_hash="0" * 64, chain=[])
        assert chain.length == 0
        assert chain.last_link is None

    def test_chain_with_links(self):
        links = [
            HashLink(index=0, data_hash="a" * 64, previous_hash="0" * 64, link_hash="b" * 64),
            HashLink(index=1, data_hash="c" * 64, previous_hash="b" * 64, link_hash="d" * 64),
        ]
        chain = HashChain(root_hash="b" * 64, chain=links)
        assert chain.length == 2
        assert chain.last_link.index == 1
        assert chain.verified_at is None


class TestObligationResult:
    """Tests for ObligationResult."""

    def test_valid_result(self):
        result = ObligationResult(
            obligation_ref="CIRC-2024-001-CL-03",
            fsm_ref="FSM-A1B2C3D4E5F6",
            status=VerdictStatus.COMPLIANT,
            current_state="COMPLIANT",
            evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
            evidence_summary="Margin report filed within T+1 deadline.",
        )
        assert result.status == VerdictStatus.COMPLIANT


class TestBrokerScore:
    """Tests for BrokerScore."""

    def test_valid_broker_score(self):
        score = BrokerScore(
            broker_id="B-12345",
            total_obligations=3,
            compliant=2,
            non_compliant=0,
            pending=1,
            compliance_rate=1.0,  # 2 / (3-1) = 1.0
            obligation_details=[
                ObligationResult(
                    obligation_ref="CL-01", fsm_ref="FSM-01",
                    status=VerdictStatus.COMPLIANT, current_state="COMPLIANT",
                    evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                ),
                ObligationResult(
                    obligation_ref="CL-02", fsm_ref="FSM-02",
                    status=VerdictStatus.COMPLIANT, current_state="COMPLIANT",
                    evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                ),
                ObligationResult(
                    obligation_ref="CL-03", fsm_ref="FSM-03",
                    status=VerdictStatus.PENDING, current_state="PENDING",
                    evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                ),
            ],
        )
        assert score.compliance_rate == 1.0

    def test_count_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="Count mismatch"):
            BrokerScore(
                broker_id="B-12345",
                total_obligations=5,
                compliant=2,
                non_compliant=1,
                pending=1,
                compliance_rate=0.5,
                obligation_details=[],  # 0 ≠ 5
            )

    def test_detail_count_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="obligation_details count"):
            BrokerScore(
                broker_id="B-12345",
                total_obligations=1,
                compliant=1,
                non_compliant=0,
                pending=0,
                compliance_rate=1.0,
                obligation_details=[],  # empty but total=1
            )

    def test_compliance_rate_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="compliance_rate"):
            BrokerScore(
                broker_id="B-12345",
                total_obligations=3,
                compliant=1,
                non_compliant=1,
                pending=1,
                compliance_rate=0.9,  # should be 0.5
                obligation_details=[
                    ObligationResult(
                        obligation_ref="CL-01", fsm_ref="FSM-01",
                        status=VerdictStatus.COMPLIANT, current_state="COMPLIANT",
                        evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                    ),
                    ObligationResult(
                        obligation_ref="CL-02", fsm_ref="FSM-02",
                        status=VerdictStatus.NON_COMPLIANT, current_state="NON_COMPLIANT",
                        evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                    ),
                    ObligationResult(
                        obligation_ref="CL-03", fsm_ref="FSM-03",
                        status=VerdictStatus.PENDING, current_state="PENDING",
                        evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                    ),
                ],
            )

    def test_all_pending_compliance_rate_is_one(self):
        score = BrokerScore(
            broker_id="B-12345",
            total_obligations=2,
            compliant=0,
            non_compliant=0,
            pending=2,
            compliance_rate=1.0,
            obligation_details=[
                ObligationResult(
                    obligation_ref="CL-01", fsm_ref="FSM-01",
                    status=VerdictStatus.PENDING, current_state="PENDING",
                    evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                ),
                ObligationResult(
                    obligation_ref="CL-02", fsm_ref="FSM-02",
                    status=VerdictStatus.PENDING, current_state="PENDING",
                    evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                ),
            ],
        )
        assert score.compliance_rate == 1.0

    def test_compliance_rate_bounds_enforced(self):
        with pytest.raises(ValidationError):
            BrokerScore(
                broker_id="B-12345",
                total_obligations=1,
                compliant=0,
                non_compliant=1,
                pending=0,
                compliance_rate=1.5,  # > 1.0
                obligation_details=[
                    ObligationResult(
                        obligation_ref="CL-01", fsm_ref="FSM-01",
                        status=VerdictStatus.NON_COMPLIANT, current_state="NON_COMPLIANT",
                        evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                    ),
                ],
            )


class TestScoreboard:
    """Tests for Scoreboard."""

    def test_valid_empty_scoreboard(self):
        sb = Scoreboard(circular_id="SEBI/HO/MIRSD/2024/001")
        assert sb.scoreboard_id.startswith("SB-")
        assert sb.broker_summaries == []
        assert sb.hash_chain is None

    def test_scoreboard_with_broker_summaries(self):
        sb = Scoreboard(
            circular_id="SEBI/HO/MIRSD/2024/001",
            broker_summaries=[
                BrokerScore(
                    broker_id="B-12345",
                    total_obligations=1,
                    compliant=1,
                    non_compliant=0,
                    pending=0,
                    compliance_rate=1.0,
                    obligation_details=[
                        ObligationResult(
                            obligation_ref="CL-01", fsm_ref="FSM-01",
                            status=VerdictStatus.COMPLIANT, current_state="COMPLIANT",
                            evaluated_at=datetime(2026, 7, 3, 10, 0, 0),
                        ),
                    ],
                ),
            ],
        )
        assert len(sb.broker_summaries) == 1
        assert sb.broker_summaries[0].broker_id == "B-12345"


# ====================================================================
# Pipeline state models
# ====================================================================


class TestPipelineStatus:
    """Tests for PipelineStatus enum."""

    def test_all_expected_statuses(self):
        expected = {
            "created", "parsing", "parsed", "extracting_fsm", "fsm_extracted",
            "awaiting_approval", "approved", "evaluating", "evaluated",
            "generating_scoreboard", "completed", "rejected", "failed",
        }
        actual = {s.value for s in PipelineStatus}
        assert actual == expected


class TestPipelineError:
    """Tests for PipelineError."""

    def test_valid_error(self):
        err = PipelineError(node="parser", message="Failed to extract text from PDF")
        assert err.node == "parser"
        assert err.timestamp is not None

    def test_error_with_detail(self):
        err = PipelineError(
            node="evaluator",
            message="FSM evaluation failed",
            detail="KeyError: 'trigger_event' not found in telemetry payload",
        )
        assert err.detail is not None


class TestCompliancePipelineState:
    """Tests for CompliancePipelineState."""

    def test_minimal_state(self):
        state = CompliancePipelineState(
            run_id="RUN-20260703-001",
            circular_id="SEBI/HO/MIRSD/2024/001",
        )
        assert state.run_id == "RUN-20260703-001"
        assert state.status == PipelineStatus.CREATED
        assert state.obligation_clauses == []
        assert state.extracted_fsms == []
        assert state.telemetry_events == []
        assert state.is_complete is False
        assert state.has_errors is False

    def test_state_awaiting_approval(self):
        state = CompliancePipelineState(
            run_id="RUN-001",
            circular_id="SEBI/HO/MIRSD/2024/001",
            status=PipelineStatus.AWAITING_APPROVAL,
        )
        assert state.is_awaiting_approval is True

    def test_state_with_errors(self):
        state = CompliancePipelineState(
            run_id="RUN-001",
            circular_id="SEBI/HO/MIRSD/2024/001",
            errors=[PipelineError(node="parser", message="PDF not found")],
        )
        assert state.has_errors is True

    def test_completed_state(self):
        state = CompliancePipelineState(
            run_id="RUN-001",
            circular_id="SEBI/HO/MIRSD/2024/001",
            status=PipelineStatus.COMPLETED,
        )
        assert state.is_complete is True

    def test_full_pipeline_state_roundtrip(self):
        """All optional fields populated — full pipeline snapshot."""
        state = CompliancePipelineState(
            run_id="RUN-20260703-001",
            circular_id="SEBI/HO/MIRSD/2024/001",
            circular_path="/data/circulars/sebi_2024_001.pdf",
            status=PipelineStatus.COMPLETED,
            raw_text="Extracted circular text...",
            obligation_clauses=[
                ObligationClause(
                    clause_id="CL-01",
                    circular_ref="SEBI/HO/MIRSD/2024/001",
                    clause_text="Brokers shall file margin reports within T+1 day.",
                    obligation_type=ObligationType.TIMELINE,
                    timeline_params=TimelineParams(offset=1),
                ),
            ],
            extracted_fsms=[
                HybridFSM(
                    obligation_ref="CL-01",
                    circular_ref="SEBI/HO/MIRSD/2024/001",
                    states=[FSMState(name="PENDING"), FSMState(name="COMPLIANT")],
                    initial_state="PENDING",
                ),
            ],
            locked_fsms=[
                HybridFSM(
                    obligation_ref="CL-01",
                    circular_ref="SEBI/HO/MIRSD/2024/001",
                    states=[FSMState(name="PENDING"), FSMState(name="COMPLIANT")],
                    initial_state="PENDING",
                ),
            ],
            approved_by="shashank",
            approved_at=datetime(2026, 7, 3, 10, 0, 0),
            telemetry_events=[
                TelemetryEvent(
                    broker_id="B-12345",
                    event_type="margin_report_filed",
                    timestamp=datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc),
                ),
            ],
            compliance_verdicts=[
                ComplianceVerdict(
                    obligation_ref="CL-01",
                    broker_id="B-12345",
                    fsm_ref="FSM-01",
                    status=VerdictStatus.COMPLIANT,
                    current_state="COMPLIANT",
                ),
            ],
            scoreboard=Scoreboard(circular_id="SEBI/HO/MIRSD/2024/001"),
            hash_chain_root="a" * 64,
            node_timings={"parser": 1.5, "fsm_extractor": 3.2, "evaluator": 0.8, "scoreboard": 0.3},
            metadata={"pipeline_version": "1.0.0"},
        )
        assert len(state.obligation_clauses) == 1
        assert len(state.extracted_fsms) == 1
        assert len(state.locked_fsms) == 1
        assert len(state.compliance_verdicts) == 1
        assert state.scoreboard is not None
        assert state.hash_chain_root is not None
        assert state.approved_by == "shashank"


# ====================================================================
# Hash chain utility (M0 interface — functional verification)
# ====================================================================


class TestHashChainUtility:
    """Tests for the hash_chain utility module.

    While full implementation is in M3, the M0 interface must be functional
    (compute_hash, link, verify_chain, build_chain) because the data structures
    depend on it.
    """

    def test_compute_hash_bytes(self):
        digest = compute_hash(b"hello world")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_compute_hash_dict(self):
        data = {"broker_id": "B-12345", "status": "compliant"}
        digest = compute_hash(data)
        assert len(digest) == 64

    def test_compute_hash_deterministic(self):
        """Same input must always produce the same hash."""
        data = {"a": 1, "b": 2}
        h1 = compute_hash(data)
        h2 = compute_hash(data)
        assert h1 == h2

    def test_compute_hash_dict_key_order_independent(self):
        """Dicts with different insertion order but same content should match."""
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 2, "a": 1}
        assert compute_hash(d1) == compute_hash(d2)

    def test_compute_hash_invalid_type(self):
        with pytest.raises(TypeError, match="expects bytes, dict, or str"):
            compute_hash(12345)  # type: ignore[arg-type]

    def test_link_genesis(self):
        """Creating a link with previous_link=None produces a genesis link."""
        data = {"fsm_id": "FSM-001", "approved": True}
        genesis = link(None, data)
        assert genesis.index == 0
        assert genesis.previous_hash == "0" * 64
        assert len(genesis.link_hash) == 64
        assert len(genesis.data_hash) == 64

    def test_link_chain(self):
        """Creating multiple links in sequence produces a valid chain."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        l3 = link(l2, {"step": 3})

        assert g.index == 0
        assert l2.index == 1
        assert l3.index == 2
        assert l2.previous_hash == g.link_hash
        assert l3.previous_hash == l2.link_hash

    def test_verify_chain_valid(self):
        """A properly constructed chain must verify as valid."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        l3 = link(l2, {"step": 3})
        chain = [g, l2, l3]

        assert verify_chain(chain) is True

    def test_verify_chain_empty(self):
        """An empty chain is vacuously valid."""
        assert verify_chain([]) is True

    def test_verify_chain_single_link(self):
        """A single-link chain should verify."""
        g = link(None, {"step": 1})
        assert verify_chain([g]) is True

    def test_verify_chain_tampered_data(self):
        """Tampering with a link's data_hash must be detected."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        chain = [g, l2]

        # Tamper with l2's data_hash
        tampered = HashLink(
            index=l2.index,
            data_hash="f" * 64,  # changed!
            previous_hash=l2.previous_hash,
            link_hash=l2.link_hash,
        )
        assert verify_chain([g, tampered]) is False

    def test_verify_chain_broken_link(self):
        """A link whose previous_hash doesn't match must be detected."""
        g = link(None, {"step": 1})
        l2_broken = HashLink(
            index=1,
            data_hash="a" * 64,
            previous_hash="0" * 64,  # should be g.link_hash, not genesis
            link_hash="b" * 64,       # will mismatch when recomputed
        )
        assert verify_chain([g, l2_broken]) is False

    def test_verify_chain_reordered(self):
        """Reordered links must be detected via index check."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        # Swap order
        assert verify_chain([l2, g]) is False

    def test_verify_chain_hash_chain_object(self):
        """verify_chain should accept a HashChain object."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        chain_obj = HashChain(root_hash=g.link_hash, chain=[g, l2])
        assert verify_chain(chain_obj) is True

    def test_build_chain(self):
        """build_chain helper should produce a valid chain."""
        data_items = [{"broker": "B-1"}, {"broker": "B-2"}, {"broker": "B-3"}]
        chain = build_chain(data_items)
        assert chain.length == 3
        assert verify_chain(chain) is True

    def test_build_chain_empty(self):
        """build_chain with no data should produce an empty chain."""
        chain = build_chain([])
        assert chain.length == 0
        assert verify_chain(chain) is True

    def test_verify_chain_wrong_genesis_previous(self):
        """First link must have previous_hash = 64 zeros."""
        bad_genesis = HashLink(
            index=0,
            data_hash="a" * 64,
            previous_hash="b" * 64,  # not genesis anchor
            link_hash="c" * 64,
        )
        assert verify_chain([bad_genesis]) is False


# ====================================================================
# CANONICAL_STATES
# ====================================================================


def test_canonical_states_set():
    """Verify the expected canonical state names are defined."""
    assert CANONICAL_STATES == {"PENDING", "DUE", "COMPLIANT", "LATE", "NON_COMPLIANT"}
