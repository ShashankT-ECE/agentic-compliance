"""
Pipeline state management.

Defines the CompliancePipelineState — the shared state object that flows through
every node in the LangGraph pipeline. This is the single source of truth for all
pipeline data at every stage of execution.

Pipeline flow:
  [Node 1: Parser] → [Node 2: FSM Extractor] → [HITL Gate] → [Node 3: Evaluator] → [Node 4: Scoreboard]
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.fsm import HybridFSM
from app.models.obligation import ObligationClause
from app.models.scoreboard import Scoreboard
from app.models.telemetry import TelemetryEvent
from app.models.verdict import ComplianceVerdict


# ---------------------------------------------------------------------------
# Pipeline status
# ---------------------------------------------------------------------------


class PipelineStatus(str, Enum):
    """Execution status of the compliance pipeline.

    The pipeline progresses through these states as each node completes.
    HITL gate pauses execution at AWAITING_APPROVAL until human review.
    """

    CREATED = "created"
    PARSING = "parsing"
    PARSED = "parsed"
    EXTRACTING_FSM = "extracting_fsm"
    FSM_EXTRACTED = "fsm_extracted"
    AWAITING_APPROVAL = "awaiting_approval"  # HITL gate active
    APPROVED = "approved"                     # FSMs locked, proceeding
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    GENERATING_SCOREBOARD = "generating_scoreboard"
    COMPLETED = "completed"
    REJECTED = "rejected"                     # HITL gate — back to FSM extraction
    FAILED = "failed"


class PipelineError(BaseModel):
    """Records an error that occurred during pipeline execution."""

    node: str = Field(
        ...,
        description="Name of the pipeline node where the error occurred",
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
    detail: str | None = Field(
        default=None,
        description="Optional technical detail (traceback, input snippet, etc.)",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of the error",
    )


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------


class CompliancePipelineState(BaseModel):
    """Shared state that flows through the LangGraph compliance pipeline.

    Each node reads its inputs from this state and writes its outputs back.
    The state accumulates data as it progresses through the 4-node DAG.

    Fields are Optional because they are populated incrementally — a field
    is None until its producing node has executed.
    """

    # ------------------------------------------------------------------
    # Run identity
    # ------------------------------------------------------------------

    run_id: str = Field(
        ...,
        description="Unique identifier for this pipeline run",
    )
    status: PipelineStatus = Field(
        default=PipelineStatus.CREATED,
        description="Current execution status of the pipeline",
    )

    # ------------------------------------------------------------------
    # Input fields
    # ------------------------------------------------------------------

    circular_id: str = Field(
        ...,
        description="SEBI circular reference number being evaluated",
    )
    circular_path: str | None = Field(
        default=None,
        description="Filesystem path to the source circular PDF (input to Node 1)",
    )
    telemetry_events: list[TelemetryEvent] = Field(
        default_factory=list,
        description="Broker telemetry events — external input to the pipeline",
    )

    # ------------------------------------------------------------------
    # Node 1 output — PDF Parser
    # ------------------------------------------------------------------

    raw_text: str | None = Field(
        default=None,
        description="Raw text extracted from the circular PDF (Node 1 output)",
    )
    obligation_clauses: list[ObligationClause] = Field(
        default_factory=list,
        description="Structured obligations parsed from the circular (Node 1 output)",
    )

    # ------------------------------------------------------------------
    # Node 2 output — FSM Extractor
    # ------------------------------------------------------------------

    extracted_fsms: list[HybridFSM] = Field(
        default_factory=list,
        description="Hybrid FSMs extracted from obligation clauses (Node 2 output)",
    )

    # ------------------------------------------------------------------
    # HITL gate output — Locked FSMs
    # ------------------------------------------------------------------

    locked_fsms: list[HybridFSM] = Field(
        default_factory=list,
        description="Human-approved FSMs, ready for deterministic evaluation",
    )
    approved_by: str | None = Field(
        default=None,
        description="Identity of the human who approved the FSMs",
    )
    approved_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of FSM approval",
    )
    hitl_notes: str | None = Field(
        default=None,
        description="Reviewer notes, amendments, or rejection reasons",
    )

    # ------------------------------------------------------------------
    # Node 3 output — Assertion Evaluator (deterministic, NO LLM)
    # ------------------------------------------------------------------

    compliance_verdicts: list[ComplianceVerdict] = Field(
        default_factory=list,
        description="Per-obligation, per-broker compliance verdicts (Node 3 output)",
    )

    # ------------------------------------------------------------------
    # Node 4 output — Scoreboard Generator
    # ------------------------------------------------------------------

    scoreboard: Scoreboard | None = Field(
        default=None,
        description="Final aggregated compliance scoreboard (Node 4 output)",
    )

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    hash_chain_root: str | None = Field(
        default=None,
        description="Root hash of the integrity chain (set after FSM locking and scoreboard generation)",
    )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    errors: list[PipelineError] = Field(
        default_factory=list,
        description="Error log for observability and debugging",
    )
    node_timings: dict[str, float] = Field(
        default_factory=dict,
        description="Per-node execution time in seconds (node_name → elapsed_seconds)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary pipeline metadata (version, config, flags)",
    )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def is_awaiting_approval(self) -> bool:
        """True when the pipeline is at the HITL gate waiting for human review."""
        return self.status == PipelineStatus.AWAITING_APPROVAL

    @property
    def is_complete(self) -> bool:
        """True when the pipeline has finished successfully."""
        return self.status == PipelineStatus.COMPLETED

    @property
    def has_errors(self) -> bool:
        """True if any errors were recorded during execution."""
        return len(self.errors) > 0
