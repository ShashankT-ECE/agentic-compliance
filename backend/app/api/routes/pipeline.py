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
