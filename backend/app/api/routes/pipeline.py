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

_LOCKED_DATA_DIR: Path = Path(__file__).resolve().parent.parent.parent / "data" / "locked_fsms"


def _get_data_dir() -> Path:
    """Return the data directory for LockedFSM records.

    Override by setting the module attribute directly:
        pipeline._LOCKED_DATA_DIR = Path("/tmp/test_dir")
    """
    return _LOCKED_DATA_DIR


class ReviewAction(BaseModel):
    """Request body for approve / reject actions."""

    reviewer: str = Field(..., min_length=1, description="Identity of the human reviewer")
    review_comments: str | None = Field(default=None, description="Optional notes (required for rejection)")


class AmendAction(BaseModel):
    """Request body for amend action."""

    reviewer: str = Field(..., min_length=1, description="Identity of the human reviewer")
    review_comments: str = Field(..., min_length=1, description="Description of what was changed and why")
    corrected_fsm: dict[str, Any] = Field(..., description="The corrected HybridFSM JSON")


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
    try:
        corrected_fsm = HybridFSM.model_validate(action.corrected_fsm)
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

    try:
        state = await runner.start(
            circular_path=request.circular_path,
            circular_id=request.circular_id,
            telemetry_events=telemetry_events,
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

    state = get_run(run_id)
    if state is None:
        # Check if the run exists on disk (from HITL persistence)
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

    verdicts = state.compliance_verdicts
    scoreboard = state.scoreboard

    return {
        "run_id": run_id,
        "circular_id": state.circular_id,
        "status": str(state.status.value),
        "total_fsms": len(state.locked_fsms),
        "pending": 0,
        "approved": 0,
        "rejected": 0,
        "amended": 0,
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
# M7 — Simplified HITL endpoints (operate on the most recent run by default)
# =========================================================================


class HitlListResponse(BaseModel):
    """Response for GET /pipeline/hitl."""

    runs: list[dict[str, Any]]


@router.get("/hitl", response_model=HitlListResponse)
def list_hitl_runs(run_id: str | None = None) -> dict[str, Any]:
    """List HITL review items.

    If run_id is provided, returns FSMs for that specific run.
    Otherwise returns all runs with pending FSMs.
    """
    if run_id:
        return _get_hitl_for_run(run_id)

    # Scan all runs for awaiting-approval status
    from app.pipeline.runner import get_all_runs

    all_runs = get_all_runs()
    awaiting = [r for r in all_runs if r["status"] == "awaiting_approval"]
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

    pending_fsms = [f for f in locked_fsms if f.status == LockStatus.PENDING_REVIEW]

    return {
        "run_id": run_id,
        "circular_ref": locked_fsms[0].circular_ref,
        "total_fsms": len(locked_fsms),
        "pending": len(pending_fsms),
        "fsms": [f.model_dump(mode="json", exclude_none=True) for f in pending_fsms],
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
        "pending": sum(1 for f in locked_fsms if str(f.status) == "pending_review"),
        "approved": sum(1 for f in locked_fsms if str(f.status) == "approved"),
        "rejected": sum(1 for f in locked_fsms if str(f.status) == "rejected"),
        "amended": sum(1 for f in locked_fsms if str(f.status) == "amended"),
    }


def _serialize_verdict(verdict: Any) -> dict[str, Any]:
    """Serialize a ComplianceVerdict to a JSON-safe dict."""
    try:
        return verdict.model_dump(mode="json", exclude_none=True)
    except AttributeError:
        return dict(verdict)
