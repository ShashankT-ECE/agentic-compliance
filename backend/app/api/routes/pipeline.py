"""
API routes for pipeline execution and HITL review.

Exposes endpoints to:
  - List FSMs pending human review
  - Get individual FSM details
  - Approve, reject, or amend FSMs
  - Retrieve review history

All HITL endpoints operate on LockedFSM records persisted under
``data/locked_fsms/{run_id}/``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.fsm import HybridFSM
from app.models.locked_fsm import LockedFSM, LockStatus
from app.models.scoreboard import HashLink
from app.pipeline.nodes.hitl_gate import (
    amend_fsm,
    approve_fsm,
    build_hitl_hash_chain,
    load_locked_fsms,
    persist_locked_fsms,
    reject_fsm,
    verify_locked_fsm_integrity,
    verify_chain,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# ---------------------------------------------------------------------------
# Data directory (overridable for testing)
# ---------------------------------------------------------------------------

_LOCKED_DATA_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "locked_fsms"


def _get_data_dir() -> Path:
    """Return the data directory for LockedFSM records.

    Override by setting the module attribute directly:
        pipeline._LOCKED_DATA_DIR = Path("/tmp/test_dir")
    """
    return _LOCKED_DATA_DIR


def _load_demo_telemetry() -> list[Any]:
    """Load the demo telemetry fixture used by scripts/run_demo.sh.

    Returns the same 10-event dataset covering 3 brokers (COMPLIANT,
    LATE, MISSING) used in integration tests and the CLI demo script.
    If the fixture file is missing (e.g. production deployment), returns
    an empty list so the pipeline runs with zero events — which is the
    safe default (all verdicts will be PENDING).

    This function lives here because it is only needed by the trigger
    endpoint.  It deliberately does NOT import from tests/ — it reads the
    JSON fixture file directly, same as the demo script and conftest.py.
    """
    import json as _json

    from app.models.telemetry import TelemetryEvent

    fixture_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "tests" / "fixtures" / "sample_telemetry.json"
    )

    if not fixture_path.exists():
        logger.warning("Demo telemetry fixture not found at %s — pipeline will run with 0 events", fixture_path)
        return []

    try:
        data = _json.loads(fixture_path.read_text(encoding="utf-8"))
        records = data.get("records", [])
        return [TelemetryEvent.model_validate(r) for r in records]
    except Exception:
        logger.exception("Failed to load demo telemetry from %s", fixture_path)
        return []


class ReviewAction(BaseModel):
    """Request body for approve / reject actions."""

    reviewer: str = Field(..., min_length=1, description="Identity of the human reviewer")
    review_comments: str | None = Field(default=None, description="Optional notes (required for rejection)")


class AmendAction(BaseModel):
    """Request body for amend action."""

    reviewer: str = Field(..., min_length=1, description="Identity of the human reviewer")
    review_comments: str = Field(..., min_length=1, description="Description of what was changed and why")
    corrected_fsm: Any = Field(..., description="The corrected HybridFSM JSON (object or JSON string)")


class FsmSummary(BaseModel):
    """Lightweight FSM summary for the pending-FSMs list."""

    locked_fsm_id: str
    fsm_id: str
    obligation_ref: str
    status: str
    version: int


class PendingFsmsResponse(BaseModel):
    """Response for GET /pipeline/{run_id}/fsms."""

    run_id: str
    circular_ref: str
    status: str
    total_fsms: int
    pending: int
    approved: int
    rejected: int
    amended: int
    fsms: list[dict[str, Any]]


class ReviewHistoryEntry(BaseModel):
    """A single entry in the review audit trail."""

    locked_fsm_id: str
    fsm_id: str
    obligation_ref: str
    action: str
    reviewer: str | None
    timestamp: str | None
    comments: str | None


class ReviewHistoryResponse(BaseModel):
    """Response for GET /pipeline/{run_id}/review-history."""

    run_id: str
    circular_ref: str
    entries: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_run_dir(run_id: str) -> Path:
    """Resolve and validate the run directory."""
    run_dir = _get_data_dir() / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")
    return run_dir


def _find_fsm(locked_fsms: list[LockedFSM], locked_fsm_id: str) -> LockedFSM:
    """Find a LockedFSM by ID, raising 404 if not found."""
    for lfsm in locked_fsms:
        if lfsm.locked_fsm_id == locked_fsm_id:
            return lfsm
    raise HTTPException(status_code=404, detail=f"LockedFSM '{locked_fsm_id}' not found in run")


def _check_pending(lfsm: LockedFSM) -> None:
    """Raise 409 if the LockedFSM is already resolved."""
    if lfsm.status != LockStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"LockedFSM '{lfsm.locked_fsm_id}' is already resolved (status: {lfsm.status.value})",
        )


# ---------------------------------------------------------------------------
# GET — List pending FSMs
# ---------------------------------------------------------------------------


@router.get("/{run_id}/fsms", response_model=PendingFsmsResponse)
def list_fsms(run_id: str) -> dict[str, Any]:
    """List all FSMs for a pipeline run with their review status."""
    run_dir = _get_run_dir(run_id)

    try:
        locked_fsms = load_locked_fsms(run_id, data_dir=_get_data_dir())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load FSMs: {exc}")

    if not locked_fsms:
        raise HTTPException(status_code=404, detail=f"No FSMs found for run '{run_id}'")

    circular_ref = locked_fsms[0].circular_ref if locked_fsms else "UNKNOWN"

    counts = {
        "pending": sum(1 for f in locked_fsms if f.status == LockStatus.PENDING_REVIEW),
        "approved": sum(1 for f in locked_fsms if f.status == LockStatus.APPROVED),
        "rejected": sum(1 for f in locked_fsms if f.status == LockStatus.REJECTED),
        "amended": sum(1 for f in locked_fsms if f.status == LockStatus.AMENDED),
    }

    return {
        "run_id": run_id,
        "circular_ref": circular_ref,
        "status": "awaiting_approval" if counts["pending"] > 0 else "resolved",
        "total_fsms": len(locked_fsms),
        **counts,
        "fsms": [f.model_dump(mode="json", exclude_none=True) for f in locked_fsms],
    }


# ---------------------------------------------------------------------------
# GET — Single FSM by ID
# ---------------------------------------------------------------------------


@router.get("/{run_id}/fsms/{locked_fsm_id}")
def get_fsm(run_id: str, locked_fsm_id: str) -> dict[str, Any]:
    """Retrieve a single LockedFSM with full details."""
    _get_run_dir(run_id)

    try:
        locked_fsms = load_locked_fsms(run_id, data_dir=_get_data_dir())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load FSMs: {exc}")

    lfsm = _find_fsm(locked_fsms, locked_fsm_id)
    return lfsm.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# POST — Approve FSM
# ---------------------------------------------------------------------------


@router.post("/{run_id}/fsms/{locked_fsm_id}/approve")
def approve_fsm_endpoint(run_id: str, locked_fsm_id: str, action: ReviewAction) -> dict[str, Any]:
    """Approve a single FSM as-is. Seals it into the hash chain."""
    _get_run_dir(run_id)

    try:
        locked_fsms = load_locked_fsms(run_id, data_dir=_get_data_dir())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load FSMs: {exc}")

    lfsm = _find_fsm(locked_fsms, locked_fsm_id)
    _check_pending(lfsm)

    # Determine the previous hash link from the existing chain
    hash_chain = build_hitl_hash_chain(locked_fsms)
    previous = hash_chain.last_link

    try:
        updated = approve_fsm(
            locked_fsm=lfsm,
            reviewer=action.reviewer,
            comments=action.review_comments,
            previous_hash_link=previous,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Persist the updated record
    _replace_in_list(locked_fsms, updated)
    persist_locked_fsms(locked_fsms, run_id, output_dir=_get_data_dir())

    return updated.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# POST — Reject FSM
# ---------------------------------------------------------------------------


@router.post("/{run_id}/fsms/{locked_fsm_id}/reject")
def reject_fsm_endpoint(run_id: str, locked_fsm_id: str, action: ReviewAction) -> dict[str, Any]:
    """Reject a single FSM with mandatory rationale."""
    _get_run_dir(run_id)

    if not action.review_comments or not action.review_comments.strip():
        raise HTTPException(status_code=400, detail="review_comments is required for rejection")

    try:
        locked_fsms = load_locked_fsms(run_id, data_dir=_get_data_dir())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load FSMs: {exc}")

    lfsm = _find_fsm(locked_fsms, locked_fsm_id)
    _check_pending(lfsm)

    try:
        updated = reject_fsm(
            locked_fsm=lfsm,
            reviewer=action.reviewer,
            comments=action.review_comments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _replace_in_list(locked_fsms, updated)
    persist_locked_fsms(locked_fsms, run_id, output_dir=_get_data_dir())

    return updated.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# POST — Amend FSM
# ---------------------------------------------------------------------------


@router.post("/{run_id}/fsms/{locked_fsm_id}/amend")
def amend_fsm_endpoint(run_id: str, locked_fsm_id: str, action: AmendAction) -> dict[str, Any]:
    """Submit a corrected FSM. The original is preserved in amendment history."""
    _get_run_dir(run_id)

    # Validate the corrected FSM through Pydantic
    corrected_data = action.corrected_fsm
    if isinstance(corrected_data, str):
        try:
            import json as _json
            corrected_data = _json.loads(corrected_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON in corrected_fsm")
    if not isinstance(corrected_data, dict):
        raise HTTPException(status_code=400, detail="corrected_fsm must be a JSON object")
    try:
        corrected_fsm = HybridFSM.model_validate(corrected_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid corrected FSM: {exc}")

    try:
        locked_fsms = load_locked_fsms(run_id, data_dir=_get_data_dir())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load FSMs: {exc}")

    lfsm = _find_fsm(locked_fsms, locked_fsm_id)
    _check_pending(lfsm)

    # Determine the previous hash link
    hash_chain = build_hitl_hash_chain(locked_fsms)
    previous = hash_chain.last_link

    try:
        updated = amend_fsm(
            locked_fsm=lfsm,
            corrected_fsm=corrected_fsm,
            reviewer=action.reviewer,
            comments=action.review_comments,
            previous_hash_link=previous,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _replace_in_list(locked_fsms, updated)
    persist_locked_fsms(locked_fsms, run_id, output_dir=_get_data_dir())

    return updated.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# GET — Review history
# ---------------------------------------------------------------------------


@router.get("/{run_id}/review-history", response_model=ReviewHistoryResponse)
def get_review_history(run_id: str) -> dict[str, Any]:
    """Retrieve the complete review audit trail for a pipeline run."""
    _get_run_dir(run_id)

    try:
        locked_fsms = load_locked_fsms(run_id, data_dir=_get_data_dir())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load FSMs: {exc}")

    if not locked_fsms:
        raise HTTPException(status_code=404, detail=f"No FSMs found for run '{run_id}'")

    circular_ref = locked_fsms[0].circular_ref
    entries: list[dict[str, Any]] = []

    for lfsm in locked_fsms:
        if lfsm.is_resolved:
            entries.append({
                "locked_fsm_id": lfsm.locked_fsm_id,
                "fsm_id": lfsm.fsm_id,
                "obligation_ref": lfsm.obligation_ref,
                "action": lfsm.status.value,
                "reviewer": lfsm.reviewer,
                "timestamp": lfsm.reviewed_at.isoformat() if lfsm.reviewed_at else None,
                "comments": lfsm.review_comments,
            })

    return {
        "run_id": run_id,
        "circular_ref": circular_ref,
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _replace_in_list(locked_fsms: list[LockedFSM], updated: LockedFSM) -> None:
    """Replace a LockedFSM in the list by matching locked_fsm_id."""
    for i, lfsm in enumerate(locked_fsms):
        if lfsm.locked_fsm_id == updated.locked_fsm_id:
            locked_fsms[i] = updated
            return


# =========================================================================
# M7 — Pipeline trigger, status, result endpoints
# =========================================================================


class TriggerRequest(BaseModel):
    """Request body for POST /pipeline/trigger."""

    circular_path: str = Field(..., min_length=1, description="Filesystem path to the SEBI circular PDF")
    circular_id: str = Field(..., min_length=1, description="SEBI circular reference number")
    telemetry: list[dict[str, Any]] = Field(default_factory=list, description="Optional initial telemetry events")
    use_rag: bool = Field(default=False, description="Use RAG retrieval instead of full PDF extraction (V2 M1)")


class TriggerResponse(BaseModel):
    """Response for POST /pipeline/trigger."""

    run_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    """Response for GET /pipeline/status/{run_id}."""

    run_id: str
    circular_id: str
    status: str
    total_fsms: int
    pending: int
    approved: int
    rejected: int
    amended: int
    verdict_count: int
    scoreboard_id: str | None
    created_at: str | None


class ResultResponse(BaseModel):
    """Response for GET /pipeline/result/{run_id}."""

    run_id: str
    circular_id: str
    status: str
    verdicts: list[dict[str, Any]]
    scoreboard: dict[str, Any] | None


@router.post("/trigger", response_model=TriggerResponse, status_code=201)
async def trigger_pipeline(request: TriggerRequest) -> dict[str, Any]:
    """Start a new compliance pipeline run.

    Parses the SEBI circular PDF, extracts FSMs, and pauses at the HITL
    gate for human review.  Returns immediately with the run_id.

    When called without telemetry events, automatically loads the demo
    telemetry fixture so the evaluator receives real broker event data
    rather than producing all-PENDING verdicts against an empty dataset.
    Explicit user-supplied telemetry always takes precedence.
    """
    import asyncio

    from app.api.deps import get_runner
    from app.models.telemetry import TelemetryEvent

    runner = get_runner()

    # Convert telemetry dicts to TelemetryEvent models
    telemetry_events: list[TelemetryEvent] = []
    for t in request.telemetry:
        try:
            telemetry_events.append(TelemetryEvent.model_validate(t))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid telemetry event: {t}")

    # ── Demo fallback: auto-load fixture telemetry when none provided ──────
    if not telemetry_events:
        telemetry_events = _load_demo_telemetry()
        if telemetry_events:
            logger.info(
                "Trigger '%s': loaded %d demo telemetry event(s) (no user telemetry provided)",
                request.circular_id,
                len(telemetry_events),
            )

    # ── RAG retrieval (V2 M1) ────────────────────────────────────────────
    chunks: list[str] | None = None
    if request.use_rag:
        try:
            from app.rag.retrieval import RetrievalPipeline
            rag = RetrievalPipeline()
            if await rag.is_indexed(request.circular_id):
                rag_text = await rag.get_text_for_parser(request.circular_id)
                if rag_text:
                    chunks = rag_text.split("\n\n")
                    logger.info(
                        "RAG retrieval: %d chunks (%d chars) for '%s'",
                        len(chunks),
                        len(rag_text),
                        request.circular_id,
                    )
                else:
                    logger.warning(
                        "RAG retrieval returned empty text for '%s' — "
                        "falling back to full PDF extraction",
                        request.circular_id,
                    )
            else:
                logger.warning(
                    "Circular '%s' not indexed in RAG store — "
                    "falling back to full PDF extraction. "
                    "Run 'python -m app.cli index' first.",
                    request.circular_id,
                )
        except Exception:
            logger.exception(
                "RAG retrieval failed for '%s' — falling back to full PDF extraction",
                request.circular_id,
            )

    try:
        state = await runner.start(
            circular_path=request.circular_path,
            circular_id=request.circular_id,
            telemetry_events=telemetry_events,
            chunks=chunks,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Pipeline trigger failed")
        raise HTTPException(status_code=500, detail=f"Pipeline trigger failed: {exc}")

    return {
        "run_id": state.run_id,
        "status": str(state.status.value),
        "message": "Pipeline started. FSM extraction complete — awaiting human review at HITL gate.",
    }


@router.get("/status/{run_id}", response_model=StatusResponse)
def get_pipeline_status(run_id: str) -> dict[str, Any]:
    """Get the current status of a pipeline run."""
    from app.api.deps import get_run
    from app.pipeline.nodes.hitl_gate import load_locked_fsms
    from app.models.locked_fsm import LockStatus

    state = get_run(run_id)

    # ── Fallback: run not in memory — try disk ──────────────────────────
    if state is None:
        try:
            locked_fsms = load_locked_fsms(run_id)
        except Exception:
            raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")

        counts = _count_fsms(locked_fsms)
        return {
            "run_id": run_id,
            "circular_id": locked_fsms[0].circular_ref if locked_fsms else "UNKNOWN",
            "status": "awaiting_approval" if counts["pending"] > 0 else "resolved",
            "total_fsms": len(locked_fsms),
            **counts,
            "verdict_count": 0,
            "scoreboard_id": None,
            "created_at": None,
        }

    # ── Run is in memory ────────────────────────────────────────────────
    status_val = str(state.status.value)

    # When awaiting approval, locked_fsms in state is intentionally empty
    # (populated on resume).  Load counts from disk for accurate reporting.
    if status_val == "awaiting_approval" and not state.locked_fsms:
        try:
            locked_fsms = load_locked_fsms(run_id)
            counts = _count_fsms(locked_fsms)
        except Exception:
            counts = {"pending": 0, "approved": 0, "rejected": 0, "amended": 0}

        return {
            "run_id": run_id,
            "circular_id": state.circular_id,
            "status": status_val,
            "total_fsms": sum(counts.values()),
            **counts,
            "verdict_count": 0,
            "scoreboard_id": None,
            "created_at": state.metadata.get("started_at", ""),
        }

    # ── Normal path: state has locked_fsms (post-resume or completed) ───
    verdicts = state.compliance_verdicts
    scoreboard = state.scoreboard

    locked = state.locked_fsms
    counts = {
        "pending": sum(1 for f in locked if _status_str(f) == "pending_review"),
        "approved": sum(1 for f in locked if _status_str(f) == "approved"),
        "rejected": sum(1 for f in locked if _status_str(f) == "rejected"),
        "amended": sum(1 for f in locked if _status_str(f) == "amended"),
    }

    return {
        "run_id": run_id,
        "circular_id": state.circular_id,
        "status": status_val,
        "total_fsms": len(locked),
        **counts,
        "verdict_count": len(verdicts),
        "scoreboard_id": scoreboard.scoreboard_id if scoreboard else None,
        "created_at": state.metadata.get("started_at", ""),
    }


@router.get("/result/{run_id}", response_model=ResultResponse)
def get_pipeline_result(run_id: str) -> dict[str, Any]:
    """Get the complete result of a pipeline run (verdicts + scoreboard)."""
    from app.api.deps import get_run

    state = get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")

    status = str(state.status.value)
    if status not in ("completed", "evaluated", "generating_scoreboard"):
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline run '{run_id}' is not complete (status: {status})",
        )

    verdicts = state.compliance_verdicts
    scoreboard = state.scoreboard

    return {
        "run_id": run_id,
        "circular_id": state.circular_id,
        "status": status,
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "scoreboard": scoreboard.model_dump(mode="json", exclude_none=True) if scoreboard else None,
    }


# =========================================================================
# M7 — Resume endpoint
# =========================================================================


class ResumeResponse(BaseModel):
    """Response for POST /pipeline/{run_id}/resume."""

    run_id: str
    status: str
    verdict_count: int
    scoreboard_id: str | None
    message: str


@router.post("/{run_id}/resume", response_model=ResumeResponse)
async def resume_pipeline(run_id: str) -> dict[str, Any]:
    """Resume a paused pipeline after all FSMs have been reviewed.

    Loads approved/amended LockedFSMs from disk, merges telemetry from the
    global ingest store, and runs the evaluator → scoreboard to completion.

    Requires all FSMs to be reviewed (no PENDING_REVIEW remaining).
    Falls back to disk-based state reconstruction when the in-memory state
    is unavailable (e.g. after server restart).
    """
    from app.api.deps import get_run, get_runner
    from app.api.routes.telemetry import _get_telemetry_store
    from app.models.locked_fsm import LockStatus
    from app.pipeline.state import CompliancePipelineState, PipelineStatus

    # 1. Load locked FSMs from disk
    try:
        locked_fsms = load_locked_fsms(run_id, data_dir=_get_data_dir())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")

    if not locked_fsms:
        raise HTTPException(status_code=404, detail=f"No FSMs found for run '{run_id}'")

    # 2. Check for pending FSMs
    pending = [f for f in locked_fsms if f.status == LockStatus.PENDING_REVIEW]
    if pending:
        raise HTTPException(
            status_code=400,
            detail=f"{len(pending)} FSM(s) still pending review. Review all FSMs before resuming.",
        )

    # 3. Filter to approved/amended
    active = [f for f in locked_fsms if f.status in (LockStatus.APPROVED, LockStatus.AMENDED)]
    if not active:
        raise HTTPException(status_code=400, detail="No approved or amended FSMs to evaluate")

    # 4. Get in-memory state (or reconstruct from disk)
    state = get_run(run_id)
    if state is not None:
        current_status = str(state.status.value)
        if current_status in ("completed", "evaluated", "generating_scoreboard"):
            raise HTTPException(
                status_code=400,
                detail=f"Pipeline run '{run_id}' is already completed (status: {current_status})",
            )

    if state is None:
        # ── Disk fallback: reconstruct minimal state ──────────────────────
        logger.info("Run '%s' not in memory — reconstructing from disk", run_id)
        from app.pipeline.runner import _get_store
        from datetime import datetime, timezone

        state = CompliancePipelineState(
            run_id=run_id,
            circular_id=locked_fsms[0].circular_ref,
            telemetry_events=[],
            metadata={
                "started_at": datetime.now(timezone.utc).isoformat(),
                "reconstructed_from_disk": True,
            },
        )
        state.status = PipelineStatus.AWAITING_APPROVAL
        # Seed the runner's store so resume() can find it
        store = _get_store()
        store[run_id] = type(
            "RunRecord",
            (),
            {"state": state, "created_at": datetime.now(timezone.utc).isoformat()},
        )()

    # 5. Merge telemetry from the global ingest store into pipeline state
    telemetry_store = _get_telemetry_store()
    existing_ids = {e.event_id for e in state.telemetry_events}
    for broker_events in telemetry_store.values():
        for ev in broker_events:
            if ev.event_id not in existing_ids:
                state.telemetry_events.append(ev)
                existing_ids.add(ev.event_id)

    logger.info(
        "Resuming run '%s': %d approved FSM(s), %d telemetry event(s)",
        run_id,
        len(active),
        len(state.telemetry_events),
    )

    # 6. Resume through evaluator → scoreboard
    runner = get_runner()
    try:
        final_state = await runner.resume(run_id, active)
    except Exception as exc:
        logger.exception("Resume failed for run '%s'", run_id)
        raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {exc}")

    scoreboard = final_state.scoreboard

    return {
        "run_id": run_id,
        "status": str(final_state.status.value),
        "verdict_count": len(final_state.compliance_verdicts),
        "scoreboard_id": scoreboard.scoreboard_id if scoreboard else None,
        "message": (
            f"Pipeline completed with {len(final_state.compliance_verdicts)} verdict(s). "
            f"Report can now be generated."
        ),
    }


# =========================================================================
# M7 — Simplified HITL endpoints (operate on the most recent run by default)
# =========================================================================


class HitlListResponse(BaseModel):
    """Response for GET /pipeline/hitl."""

    runs: list[dict[str, Any]]


@router.get("/hitl")
def list_hitl_runs(run_id: str | None = None) -> dict[str, Any]:
    """List HITL review items.

    If run_id is provided, returns FSMs for that specific run.
    Otherwise scans disk for all runs with pending obligations.
    Disk is the authoritative source — the in-memory store is volatile.
    """
    if run_id:
        return _get_hitl_for_run(run_id)

    # Scan disk for runs with pending FSMs — disk is the source of truth
    awaiting: list[dict[str, Any]] = []
    data_dir = _get_data_dir()
    if data_dir.exists():
        import json as _json
        for run_dir in sorted(data_dir.iterdir()):
            if not run_dir.is_dir():
                continue

            # Skip empty directories (orphaned or cleaned up)
            fsm_files = sorted(run_dir.glob("LOCKED-*.json"))
            if not fsm_files:
                continue

            # Read pipeline state for counts
            state_path = run_dir / "_pipeline_state.json"
            pending_count = 0
            total_fsms = len(fsm_files)
            if state_path.exists():
                try:
                    state_data = _json.loads(state_path.read_text(encoding="utf-8"))
                    pending_count = state_data.get("pending", 0)
                    total_fsms = state_data.get("total_fsms", total_fsms)
                except Exception:
                    logger.warning("Failed to read pipeline state from %s", state_path)

            # Determine pending count from actual files if state file is stale
            if pending_count == 0:
                # Re-count from file contents
                for fpath in fsm_files:
                    try:
                        lfsm_data = _json.loads(fpath.read_text(encoding="utf-8"))
                        if lfsm_data.get("status") == "pending_review":
                            pending_count += 1
                    except Exception:
                        pass

            # Only include runs with at least one pending obligation
            if pending_count == 0:
                continue

            # Get circular_ref from the first LockedFSM file
            circular_ref = "UNKNOWN"
            for fpath in fsm_files:
                try:
                    lfsm_data = _json.loads(fpath.read_text(encoding="utf-8"))
                    circular_ref = lfsm_data.get("circular_ref", "UNKNOWN")
                    break
                except Exception:
                    pass

            awaiting.append({
                "run_id": run_dir.name,
                "circular_ref": circular_ref,
                "total_fsms": total_fsms,
                "pending": pending_count,
                "status": "awaiting_approval",
            })

    return {"runs": awaiting}


def _get_hitl_for_run(run_id: str) -> dict[str, Any]:
    """Get HITL details for a specific run."""
    from app.pipeline.nodes.hitl_gate import load_locked_fsms

    try:
        locked_fsms = load_locked_fsms(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")

    if not locked_fsms:
        raise HTTPException(status_code=404, detail=f"No FSMs found for run '{run_id}'")

    pending_count = sum(1 for f in locked_fsms if f.status == LockStatus.PENDING_REVIEW)

    return {
        "run_id": run_id,
        "circular_ref": locked_fsms[0].circular_ref,
        "total_fsms": len(locked_fsms),
        "pending": pending_count,
        "fsms": [f.model_dump(mode="json", exclude_none=True) for f in locked_fsms],
    }


@router.post("/hitl/{fsm_id}/approve")
def hitl_approve(fsm_id: str, run_id: str, action: ReviewAction) -> dict[str, Any]:
    """Approve a LockedFSM by its fsm_id (simplified route)."""
    # Delegate to the existing approve endpoint
    return approve_fsm_endpoint(run_id, fsm_id, action)


@router.post("/hitl/{fsm_id}/reject")
def hitl_reject(fsm_id: str, run_id: str, action: ReviewAction) -> dict[str, Any]:
    """Reject a LockedFSM by its fsm_id (simplified route)."""
    if not action.review_comments or not action.review_comments.strip():
        raise HTTPException(status_code=400, detail="review_comments is required for rejection")
    return reject_fsm_endpoint(run_id, fsm_id, action)


@router.post("/hitl/{fsm_id}/amend")
def hitl_amend(fsm_id: str, run_id: str, action: AmendAction) -> dict[str, Any]:
    """Amend a LockedFSM by its fsm_id (simplified route)."""
    return amend_fsm_endpoint(run_id, fsm_id, action)


# =========================================================================
# Helpers
# =========================================================================


def _count_fsms(locked_fsms: list[Any]) -> dict[str, int]:
    """Count FSMs by status."""
    return {
        "pending": sum(1 for f in locked_fsms if _status_str(f) == "pending_review"),
        "approved": sum(1 for f in locked_fsms if _status_str(f) == "approved"),
        "rejected": sum(1 for f in locked_fsms if _status_str(f) == "rejected"),
        "amended": sum(1 for f in locked_fsms if _status_str(f) == "amended"),
    }


def _status_str(f: Any) -> str:
    """Extract the status value string from a LockedFSM or dict."""
    try:
        return str(f.status.value)
    except AttributeError:
        return str(f.get("status", "unknown"))


def _serialize_verdict(verdict: Any) -> dict[str, Any]:
    """Serialize a ComplianceVerdict to a JSON-safe dict."""
    try:
        return verdict.model_dump(mode="json", exclude_none=True)
    except AttributeError:
        return dict(verdict)
