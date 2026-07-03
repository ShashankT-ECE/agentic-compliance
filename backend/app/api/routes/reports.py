"""
API routes for compliance reports (M7).

Endpoints for generating and retrieving compliance audit reports
from completed pipeline runs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])

# In-memory report store (V1)
_report_store: dict[str, dict[str, Any]] = {}


def _get_report_store() -> dict[str, dict[str, Any]]:
    """Return the report store (overridable for testing)."""
    return _report_store


def _set_report_store(store: dict[str, dict[str, Any]]) -> None:
    """Override the report store (for testing)."""
    global _report_store
    _report_store = store


# =========================================================================
# Response models
# =========================================================================


class ReportResponse(BaseModel):
    """Response for GET /reports/{report_id}."""

    report_id: str
    run_id: str
    circular_id: str
    generated_at: str
    summary: dict[str, Any]
    scoreboard: dict[str, Any] | None
    verdicts: list[dict[str, Any]]


class GenerateResponse(BaseModel):
    """Response for GET /reports/generate/{run_id}."""

    report_id: str
    run_id: str
    circular_id: str
    generated_at: str
    message: str


# =========================================================================
# GET /reports/generate/{run_id}
# =========================================================================


@router.get("/generate/{run_id}", response_model=GenerateResponse)
def generate_report(run_id: str) -> dict[str, Any]:
    """Generate a compliance report from a completed pipeline run.

    Retrieves the scoreboard and verdicts from the completed run and
    stores them as an immutable report.
    """
    from app.pipeline.runner import get_run_state

    state = get_run_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")

    status = str(state.status.value)
    if status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline run '{run_id}' is not complete (status: {status}). Cannot generate report.",
        )

    report_id = f"RPT-{uuid4().hex[:12].upper()}"
    now = datetime.now(timezone.utc)

    scoreboard = state.scoreboard
    verdicts = state.compliance_verdicts

    # Build summary
    verdict_count = len(verdicts)
    compliant_count = sum(1 for v in verdicts if _get_status(v) == "compliant")
    non_compliant_count = sum(1 for v in verdicts if _get_status(v) == "non_compliant")
    pending_count = sum(1 for v in verdicts if _get_status(v) == "pending")

    summary = {
        "total_verdicts": verdict_count,
        "compliant": compliant_count,
        "non_compliant": non_compliant_count,
        "pending": pending_count,
        "compliance_pct": round(compliant_count / max(verdict_count, 1) * 100, 2),
    }

    report = {
        "report_id": report_id,
        "run_id": run_id,
        "circular_id": state.circular_id,
        "generated_at": now.isoformat(),
        "summary": summary,
        "scoreboard": scoreboard.model_dump(mode="json", exclude_none=True) if scoreboard else None,
        "verdicts": [_serialize_verdict(v) for v in verdicts],
    }

    store = _get_report_store()
    store[report_id] = report

    logger.info("Generated report '%s' for run '%s'", report_id, run_id)

    return {
        "report_id": report_id,
        "run_id": run_id,
        "circular_id": state.circular_id,
        "generated_at": now.isoformat(),
        "message": f"Report generated with {verdict_count} verdicts across {len(summary)} metrics",
    }


# =========================================================================
# GET /reports/{report_id}
# =========================================================================


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: str) -> dict[str, Any]:
    """Retrieve a previously generated compliance report by ID."""
    store = _get_report_store()
    report = store.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")

    return report


# =========================================================================
# Helpers
# =========================================================================


def _get_status(verdict: Any) -> str:
    """Extract the status string from a ComplianceVerdict."""
    try:
        return str(verdict.status.value)
    except AttributeError:
        return str(verdict.get("status", "unknown"))


def _serialize_verdict(verdict: Any) -> dict[str, Any]:
    """Serialize a ComplianceVerdict to a JSON-safe dict."""
    try:
        return verdict.model_dump(mode="json", exclude_none=True)
    except AttributeError:
        return dict(verdict)
