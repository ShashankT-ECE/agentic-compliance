"""
FSM (Finite State Machine) data models.

Defines the Hybrid FSM schemas — the central abstraction of the compliance pipeline.
Each FSM represents one compliance obligation as a state machine with embedded timeline
conditions.

Hybrid FSM = State machine (states + transitions) + Timeline rules (deadlines).

These are the output of Node 2 (FSM Extractor) and the input to Node 3 (Evaluator),
after passing through the HITL gate.
"""

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Canonical FSM state names (V1 — timeline obligations)
# ---------------------------------------------------------------------------

CANONICAL_STATES: set[str] = {
    "PENDING",
    "DUE",
    "COMPLIANT",
    "LATE",
    "NON_COMPLIANT",
}


class FSMState(BaseModel):
    """A single state in the compliance FSM.

    Canonical states for timeline obligations:
      - PENDING: obligation period has begun, deadline not yet reached
      - DUE: deadline window is open (within grace period)
      - COMPLIANT: required action was completed on time
      - LATE: required action was completed but after the deadline
      - NON_COMPLIANT: deadline passed with no compliant action
    """

    name: str = Field(
        ...,
        min_length=1,
        description="State name (canonical: PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT)",
    )
    description: str = Field(
        default="",
        description="Human-readable description of what this state represents",
    )


class FSMTransition(BaseModel):
    """A transition between FSM states triggered by an event or condition.

    Example:
      from_state="PENDING", to_state="COMPLIANT",
      trigger_event="margin_report_filed",
      conditions={"report_type": "daily"}
    """

    from_state: str = Field(..., min_length=1, description="Source state name")
    to_state: str = Field(..., min_length=1, description="Target state name")
    trigger_event: str = Field(
        ...,
        min_length=1,
        description="Event type that triggers this transition (e.g., 'margin_report_filed')",
    )
    conditions: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional constraints that must be satisfied for this transition",
    )

    @model_validator(mode="after")
    def validate_distinct_states(self) -> "FSMTransition":
        """Ensure from_state and to_state are different."""
        if self.from_state == self.to_state:
            raise ValueError(
                f"Transition from_state and to_state must differ: both are '{self.from_state}'"
            )
        return self


class TimelineRule(BaseModel):
    """A time-based condition embedded in the FSM.

    Describes a deadline relative to a start event. When the deadline elapses
    without the required action, an automatic transition fires (e.g., PENDING → LATE).

    Example: "File report within T+1 day of trade execution" →
        start_event="trade_executed", deadline_offset=1, grace_period=0, time_unit="days"
    """

    start_event: str = Field(
        ...,
        min_length=1,
        description="Event type that starts the countdown (e.g., 'trade_executed')",
    )
    deadline_offset: int = Field(
        ...,
        ge=0,
        description="Number of time units from start_event before the deadline",
    )
    grace_period: int = Field(
        default=0,
        ge=0,
        description="Additional grace period in the same time unit",
    )
    time_unit: str = Field(
        default="days",
        description="Time unit for offset and grace period",
        pattern=r"^(days|hours|months)$",
    )
    overdue_transition: str = Field(
        default="LATE",
        description="Target state when the deadline elapses without compliance (default: LATE)",
    )


class HybridFSM(BaseModel):
    """A hybrid finite state machine representing one compliance obligation.

    Combines a classic state machine (states + event-driven transitions) with
    timeline rules (time-driven auto-transitions). This is the central data
    structure of the compliance pipeline.

    Each HybridFSM links back to its source ObligationClause for auditability.
    """

    fsm_id: str = Field(
        default_factory=lambda: f"FSM-{uuid4().hex[:12].upper()}",
        description="Unique FSM identifier",
    )
    obligation_ref: str = Field(
        ...,
        description="References the source ObligationClause.clause_id",
    )
    circular_ref: str = Field(
        ...,
        description="References the source SEBI circular",
    )
    states: list[FSMState] = Field(
        ...,
        min_length=2,
        description="All states in this FSM (minimum 2: start + terminal)",
    )
    initial_state: str = Field(
        ...,
        min_length=1,
        description="Name of the initial state (must exist in states list)",
    )
    transitions: list[FSMTransition] = Field(
        default_factory=list,
        description="Event-driven transitions between states",
    )
    timeline_rules: list[TimelineRule] = Field(
        default_factory=list,
        description="Time-driven auto-transition rules (deadlines)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provenance: source clause text, extraction confidence, model version, etc.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def validate_initial_state_exists(self) -> "HybridFSM":
        """Ensure initial_state is present in the states list."""
        state_names = {s.name for s in self.states}
        if self.initial_state not in state_names:
            raise ValueError(
                f"initial_state '{self.initial_state}' not found in states: {sorted(state_names)}"
            )
        return self

    @model_validator(mode="after")
    def validate_transition_states_exist(self) -> "HybridFSM":
        """Ensure all transition from/to states exist in the states list."""
        state_names = {s.name for s in self.states}
        for t in self.transitions:
            if t.from_state not in state_names:
                raise ValueError(
                    f"Transition from_state '{t.from_state}' not found in FSM states"
                )
            if t.to_state not in state_names:
                raise ValueError(
                    f"Transition to_state '{t.to_state}' not found in FSM states"
                )
        return self

    @model_validator(mode="after")
    def validate_timeline_rule_states_exist(self) -> "HybridFSM":
        """Ensure timeline rule overdue_transition targets exist in states."""
        state_names = {s.name for s in self.states}
        for rule in self.timeline_rules:
            if rule.overdue_transition not in state_names:
                raise ValueError(
                    f"TimelineRule overdue_transition '{rule.overdue_transition}' "
                    f"not found in FSM states"
                )
        return self

    @model_validator(mode="after")
    def validate_obligation_ref_format(self) -> "HybridFSM":
        """Ensure obligation_ref is not empty or whitespace-only."""
        if not self.obligation_ref.strip():
            raise ValueError("obligation_ref must not be empty or whitespace-only")
        return self

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def state_names(self) -> set[str]:
        """Return the set of state names in this FSM."""
        return {s.name for s in self.states}

    @property
    def terminal_states(self) -> set[str]:
        """Return states that have no outgoing transitions."""
        sources = {t.from_state for t in self.transitions}
        return self.state_names - sources

    @property
    def is_valid_canonical(self) -> bool:
        """Check whether all states use canonical names."""
        return self.state_names.issubset(CANONICAL_STATES)
