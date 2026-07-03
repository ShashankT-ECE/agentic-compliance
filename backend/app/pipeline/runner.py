"""
Pipeline runner (M7).

Orchestrates the execution of the compliance pipeline through LangGraph.
Provides functions to start, resume, and query pipeline runs with support
for the HITL pause/resume cycle.

Uses an in-memory store for run state (V1 — replace with DB in M9).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.models.telemetry import TelemetryEvent
from app.pipeline.state import CompliancePipelineState, PipelineStatus

logger = logging.getLogger(__name__)


# =========================================================================
# In-memory run store (V1 — replace with database persistence in M9)
# =========================================================================


@dataclass
class RunRecord:
    """Holds the state and metadata for one pipeline run."""

    state: CompliancePipelineState
    created_at: str = ""
    updated_at: str = ""


_run_store: dict[str, RunRecord] = {}


def _get_store() -> dict[str, RunRecord]:
    """Return the module-level run store (overridable for testing)."""
    return _run_store


def _set_store(store: dict[str, RunRecord]) -> None:
    """Override the run store (for testing)."""
    global _run_store
    _run_store = store


# =========================================================================
# Helpers
# =========================================================================


def _make_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================================================================
# Pipeline runner
# =========================================================================


class PipelineRunner:
    """Orchestrates pipeline execution through LangGraph.

    Usage:
        runner = PipelineRunner(llm_client)
        state = await runner.start(
            circular_path="/path/to/circular.pdf",
            circular_id="SEBI/HO/MIRSD/...",
            telemetry_events=[],
        )
        # Pipeline pauses at AWAITING_APPROVAL
        # Human reviews FSMs via API
        # Then:
        state = await runner.resume(state.run_id, approved_fsms)
    """

    def __init__(self, llm_client: Any = None) -> None:
        self._llm_client = llm_client

    # ── Start pipeline ───────────────────────────────────────────────

    async def start(
        self,
        circular_path: str,
        circular_id: str,
        telemetry_events: list[TelemetryEvent] | None = None,
    ) -> CompliancePipelineState:
        """Start a new pipeline run from scratch.

        Executes parser → fsm_extractor → hitl_gate sequentially.
        The pipeline pauses at AWAITING_APPROVAL after the HITL gate
        creates LockedFSM records.

        Args:
            circular_path: Filesystem path to the SEBI circular PDF.
            circular_id: SEBI circular reference number.
            telemetry_events: Broker telemetry events (optional at start time).

        Returns:
            The pipeline state after the HITL gate (status AWAITING_APPROVAL).
        """
        run_id = _make_run_id()
        now = _utcnow()

        state = CompliancePipelineState(
            run_id=run_id,
            circular_id=circular_id,
            circular_path=circular_path,
            telemetry_events=telemetry_events or [],
            metadata={"started_at": now},
        )

        store = _get_store()
        store[run_id] = RunRecord(state=state, created_at=now)

        logger.info("Starting pipeline run '%s' for circular '%s'", run_id, circular_id)

        # Run nodes sequentially: parser → fsm_extractor → hitl_gate
        state = await self._run_until_hitl(state)

        # Persist updated state
        store[run_id].state = state
        store[run_id].updated_at = _utcnow()

        return state

    # ── Resume after HITL ────────────────────────────────────────────

    async def resume(
        self,
        run_id: str,
        approved_fsms: list[Any],
    ) -> CompliancePipelineState:
        """Resume a paused pipeline after HITL review is complete.

        Sets locked_fsms to the approved/amended FSMs and continues through
        evaluator → scoreboard.

        Args:
            run_id: The pipeline run identifier.
            approved_fsms: List of approved/amended LockedFSM records.

        Returns:
            The final pipeline state (status COMPLETED or FAILED).
        """
        store = _get_store()
        if run_id not in store:
            raise KeyError(f"Pipeline run '{run_id}' not found")

        state = store[run_id].state

        logger.info("Resuming pipeline run '%s' with %d approved FSM(s)", run_id, len(approved_fsms))

        # Set approved FSMs
        state.locked_fsms = list(approved_fsms)

        try:
            # Run evaluator → scoreboard
            from app.pipeline.graph import evaluator_node, scoreboard_node

            updates = evaluator_node(state)
            _apply_updates(state, updates)

            updates = scoreboard_node(state)
            _apply_updates(state, updates)

            state.status = PipelineStatus.COMPLETED
        except Exception:
            logger.exception("Pipeline resume failed for run '%s'", run_id)
            state.status = PipelineStatus.FAILED

        store[run_id].state = state
        store[run_id].updated_at = _utcnow()

        return state

    # ── Run headless (no HITL pause) ─────────────────────────────────

    async def run_headless(
        self,
        circular_path: str,
        circular_id: str,
        telemetry_events: list[TelemetryEvent] | None = None,
        approved_fsms: list[Any] | None = None,
    ) -> CompliancePipelineState:
        """Run the full pipeline without pausing at the HITL gate.

        Used for testing and for scenarios where FSMs are pre-approved.
        If approved_fsms is provided, the HITL gate is bypassed.

        Args:
            circular_path: Path to the SEBI circular PDF.
            circular_id: SEBI circular reference.
            telemetry_events: Broker telemetry events.
            approved_fsms: Optional pre-approved LockedFSM records.

        Returns:
            Final pipeline state.
        """
        run_id = _make_run_id()
        now = _utcnow()

        state = CompliancePipelineState(
            run_id=run_id,
            circular_id=circular_id,
            circular_path=circular_path,
            telemetry_events=telemetry_events or [],
            metadata={"started_at": now, "headless": True},
        )

        store = _get_store()
        store[run_id] = RunRecord(state=state, created_at=now)

        logger.info("Starting headless pipeline run '%s'", run_id)

        if approved_fsms is not None:
            # Bypass HITL: run parser → fsm_extractor, then evaluator → scoreboard
            state = await self._run_until_hitl(state)
            state.locked_fsms = list(approved_fsms)

            from app.pipeline.graph import evaluator_node, scoreboard_node

            updates = evaluator_node(state)
            _apply_updates(state, updates)

            updates = scoreboard_node(state)
            _apply_updates(state, updates)

            state.status = PipelineStatus.COMPLETED
        else:
            # Full run including HITL
            state = await self._run_until_hitl(state)

        store[run_id].state = state
        store[run_id].updated_at = _utcnow()

        return state

    # ── Internal helpers ─────────────────────────────────────────────

    async def _run_until_hitl(self, state: CompliancePipelineState) -> CompliancePipelineState:
        """Execute parser → fsm_extractor → hitl_gate sequentially."""
        from app.pipeline.graph import fsm_extractor_node, hitl_gate_node, parser_node

        # Node 1: Parser (async, needs LLM client)
        updates = await parser_node(state, self._llm_client)
        _apply_updates(state, updates)

        # Node 2: FSM Extractor (async, needs LLM client)
        updates = await fsm_extractor_node(state, self._llm_client)
        _apply_updates(state, updates)

        # HITL Gate (sync)
        updates = hitl_gate_node(state)
        _apply_updates(state, updates)

        return state


# =========================================================================
# State update helper
# =========================================================================


def _apply_updates(state: CompliancePipelineState, updates: dict[str, Any]) -> None:
    """Apply a dict of updates to a CompliancePipelineState Pydantic model.

    Mutates the model in place by setting attributes for each key in updates.
    """
    for key, value in updates.items():
        if hasattr(state, key):
            setattr(state, key, value)


# =========================================================================
# Store access helpers (used by API routes)
# =========================================================================


def get_run_state(run_id: str) -> CompliancePipelineState | None:
    """Get the current state of a pipeline run."""
    store = _get_store()
    record = store.get(run_id)
    return record.state if record else None


def get_all_runs() -> list[dict[str, Any]]:
    """Get a summary of all pipeline runs."""
    store = _get_store()
    summaries: list[dict[str, Any]] = []
    for run_id, record in store.items():
        state = record.state
        summaries.append({
            "run_id": run_id,
            "circular_id": state.circular_id,
            "status": str(state.status.value),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        })
    return summaries
