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
        self._pg_repo = None  # lazily created

    def _get_pg_repo(self):
        """Return a PipelineRunRepo, or None if PG is unavailable."""
        if self._pg_repo is not None:
            return self._pg_repo
        try:
            from app.database import AsyncSessionLocal
            from app.db.repos.pipeline_run_repo import PipelineRunRepo
            self._pg_repo = (AsyncSessionLocal, PipelineRunRepo)
        except Exception:
            logger.debug("PostgreSQL persistence unavailable")
        return self._pg_repo

    async def _persist_checkpoint(self, state: CompliancePipelineState) -> None:
        """Persist a checkpoint save to PostgreSQL (graceful fallback)."""
        pg = self._get_pg_repo()
        if pg is None:
            return
        SessionFactory, RepoClass = pg
        try:
            async with SessionFactory() as session:
                repo = RepoClass(session)
                await repo.save_checkpoint(state)
                await session.commit()
        except Exception:
            logger.debug("Checkpoint save failed for '%s' — continuing", state.run_id)

    async def _persist_completed(self, state: CompliancePipelineState) -> None:
        """Persist the completed run with verdicts + evidence in one transaction."""
        pg = self._get_pg_repo()
        if pg is None:
            return
        SessionFactory, RepoClass = pg
        try:
            async with SessionFactory() as session:
                repo = RepoClass(session)
                await repo.save_completed_run(state)
                await session.commit()
                logger.info("Run '%s' persisted to PostgreSQL", state.run_id)
        except Exception:
            logger.exception("Failed to persist completed run '%s'", state.run_id)

    # ── Start pipeline ───────────────────────────────────────────────

    async def start(
        self,
        circular_path: str,
        circular_id: str,
        telemetry_events: list[TelemetryEvent] | None = None,
        chunks: list[str] | None = None,
        chunk_objects: list[dict] | None = None,
    ) -> CompliancePipelineState:
        """Start a new pipeline run from scratch.

        Executes parser → fsm_extractor → hitl_gate sequentially.
        The pipeline pauses at AWAITING_APPROVAL after the HITL gate
        creates LockedFSM records.

        Args:
            circular_path: Filesystem path to the SEBI circular PDF.
            circular_id: SEBI circular reference number.
            telemetry_events: Broker telemetry events (optional at start time).
            chunks: Optional pre-retrieved RAG chunks (V2 M1).  When provided,
                    the parser uses these instead of extracting the full PDF.
            chunk_objects: Serialized Chunk objects (V2 M3).  Preserved for
                    evidence assembly after evaluation.

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
            chunks=chunks,
            chunk_objects=chunk_objects or [],
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
        evaluator → scoreboard, then assembles evidence references.
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

            # Assemble evidence (V2 M3)
            await self._assemble_evidence(state)

            state.status = PipelineStatus.COMPLETED

            # Persist completed run to PG (V2 M4)
            await self._persist_completed(state)

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
            Final pipeline state with evidence assembled.
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

            # Assemble evidence (V2 M3)
            await self._assemble_evidence(state)

            state.status = PipelineStatus.COMPLETED

            # Persist completed run to PG (V2 M4)
            await self._persist_completed(state)

        else:
            # Full run including HITL
            state = await self._run_until_hitl(state)

        store[run_id].state = state
        store[run_id].updated_at = _utcnow()

        return state

    # ── Evidence assembly (V2 M3) ────────────────────────────────────

    async def _assemble_evidence(self, state: CompliancePipelineState) -> None:
        """Build EvidenceReference objects for every verdict in *state*.

        Called after evaluator → scoreboard. Uses the EvidenceService to
        attribute input chunks to obligations and produce one
        EvidenceReference per verdict. Results are stored in
        ``state.evidence_map``.

        Skips silently when:
          - No chunk objects are available (V1 full-PDF run).
          - No verdicts were produced.
          - EvidenceService encounters an error (logged, not fatal).
        """
        if not state.chunk_objects or not state.compliance_verdicts:
            logger.info(
                "Skipping evidence assembly for run '%s' — %s",
                state.run_id,
                "no chunk objects" if not state.chunk_objects else "no verdicts",
            )
            return

        try:
            from app.models.obligation import ObligationClause
            from app.pipeline.evidence_service import EvidenceService
            from app.rag.schemas import Chunk

            # Reconstruct Chunk objects from serialized dicts
            chunks = [Chunk.model_validate(c) for c in state.chunk_objects]
            obligations = list(state.obligation_clauses)
            verdicts = list(state.compliance_verdicts)

            service = EvidenceService()
            evidence_map = service.build_evidence(
                verdicts=verdicts,
                chunks=chunks,
                obligations=obligations,
                circular_ref=state.circular_id,
                pdf_path=state.circular_path or "",
                run_id=state.run_id,
                enrich_bbox=False,  # bbox enrichment is expensive; defer to API call
            )

            # Store as dicts in the state
            state.evidence_map = {
                vid: ev.model_dump(mode="json", exclude_none=True)
                for vid, ev in evidence_map.items()
            }

            logger.info(
                "Assembled %d evidence reference(s) for run '%s'",
                len(state.evidence_map),
                state.run_id,
            )
        except Exception:
            logger.exception(
                "Evidence assembly failed for run '%s' — continuing",
                state.run_id,
            )

    # ── Internal helpers ─────────────────────────────────────────────

    async def _run_until_hitl(self, state: CompliancePipelineState) -> CompliancePipelineState:
        """Execute parser → fsm_extractor → hitl_gate sequentially."""
        from app.pipeline.graph import fsm_extractor_node, hitl_gate_node, parser_node

        state.status = PipelineStatus.PARSING
        await self._persist_checkpoint(state)

        # Node 1: Parser (async, needs LLM client)
        updates = await parser_node(state, self._llm_client)
        _apply_updates(state, updates)
        state.status = PipelineStatus.PARSED
        await self._persist_checkpoint(state)

        # Node 2: FSM Extractor (async, needs LLM client)
        state.status = PipelineStatus.EXTRACTING_FSM
        await self._persist_checkpoint(state)
        updates = await fsm_extractor_node(state, self._llm_client)
        _apply_updates(state, updates)
        state.status = PipelineStatus.FSM_EXTRACTED
        await self._persist_checkpoint(state)

        # HITL Gate (sync)
        updates = hitl_gate_node(state)
        _apply_updates(state, updates)
        state.status = PipelineStatus.AWAITING_APPROVAL
        await self._persist_checkpoint(state)

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
    """Get the current state of a pipeline run.

    Checks the in-memory store first, then falls back to PostgreSQL.
    """
    store = _get_store()
    record = store.get(run_id)
    if record and record.state:
        return record.state

    # Fallback: try PG
    return _load_state_from_pg(run_id)


def get_all_runs() -> list[dict[str, Any]]:
    """Get a summary of all pipeline runs.

    Merges in-memory and PG runs.
    """
    store = _get_store()
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()

    for run_id, record in store.items():
        state = record.state
        summaries.append({
            "run_id": run_id,
            "circular_id": state.circular_id,
            "status": str(state.status.value),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        })
        seen.add(run_id)

    # Add PG runs not already in memory
    pg_runs = _list_runs_from_pg()
    for r in pg_runs:
        if r["run_id"] not in seen:
            summaries.append(r)

    return summaries


# =========================================================================
# PG fallback helpers (V2 M4)
# =========================================================================


def _load_state_from_pg(run_id: str) -> CompliancePipelineState | None:
    """Attempt to load pipeline state from PostgreSQL."""
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.pipeline_run_repo import PipelineRunRepo

        async def _load():
            async with AsyncSessionLocal() as session:
                repo = PipelineRunRepo(session)
                blob = await repo.get_run(run_id)
                return blob

        blob = asyncio.run(_load())
        if blob:
            return CompliancePipelineState.model_validate(blob)
    except Exception:
        pass
    return None


def _list_runs_from_pg() -> list[dict[str, Any]]:
    """List runs from PostgreSQL."""
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.pipeline_run_repo import PipelineRunRepo

        async def _list():
            async with AsyncSessionLocal() as session:
                repo = PipelineRunRepo(session)
                return await repo.list_runs()

        return asyncio.run(_list())
    except Exception:
        return []
