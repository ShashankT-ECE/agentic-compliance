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

    # Compliance percentage matches the Scoreboard formula:
    # compliant / (total - pending) — pending verdicts are not counted
    # against compliance because evaluation is not yet complete for them.
    evaluated = verdict_count - pending_count
    if evaluated > 0:
        compliance_pct = round(compliant_count / evaluated * 100, 2)
    else:
        compliance_pct = 100.0  # all pending → nothing to fail yet

    summary = {
        "total_verdicts": verdict_count,
        "compliant": compliant_count,
        "non_compliant": non_compliant_count,
        "pending": pending_count,
        "compliance_pct": compliance_pct,
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


def _derive_explanation(verdict: Any) -> str:
    """Generate a concise human-readable explanation for a verdict.

    Derives the explanation deterministically from the evidence trail
    already present in the verdict.  No LLM, no external state — pure
    function of the evidence dict.

    The explanation answers *why* the verdict reached its status and is
    included in the serialised report so the frontend can display it
    without additional API calls.
    """
    # ── extract fields from Pydantic model or plain dict ──────────
    try:
        status = str(verdict.status.value)
        current_state = str(verdict.current_state)
        evidence: dict[str, Any] = verdict.evidence
    except AttributeError:
        status = str(verdict.get("status", "unknown"))
        current_state = str(verdict.get("current_state", ""))
        evidence = verdict.get("evidence", {}) or {}

    timeline_status: list[dict[str, Any]] = evidence.get("timeline_status", []) or []
    transition_log: list[dict[str, Any]] = evidence.get("transition_log", []) or []
    matched_events: list[dict[str, Any]] = evidence.get("matched_events", []) or []

    # ── COMPLIANT ─────────────────────────────────────────────────
    if status == "compliant":
        return "All obligations met within deadline."

    # ── NON_COMPLIANT ─────────────────────────────────────────────
    if status == "non_compliant":
        # Prefer the timeline explanation — a missed deadline is the
        # most common reason for non-compliance in V1.
        for tr in timeline_status:
            if tr.get("deadline_met") is False and tr.get("start_event_matched"):
                start_event = tr.get("start_event", "unknown")
                start_ts = tr.get("start_timestamp", "")
                try:
                    dt = datetime.fromisoformat(str(start_ts).replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    date_str = str(start_ts) if start_ts else "unknown date"
                # Derive a T+N string from the deadline offset if available
                overdue = tr.get("overdue_transition", "LATE")
                return (
                    f"Deadline missed: '{start_event}' occurred on {date_str} "
                    f"but required action was not completed in time."
                )

        # Fallback — evidence-driven
        if transition_log:
            last = transition_log[-1]
            return (
                f"Non-compliant: reached state '{last.get('target', current_state)}' "
                f"via '{last.get('trigger', 'unknown')}'."
            )
        return "Non-compliant: required action not completed by deadline."

    # ── PENDING ───────────────────────────────────────────────────
    if status == "pending":
        # Case 1: timeline rule exists but start event never fired
        for tr in timeline_status:
            if tr.get("start_event_matched") is False:
                return (
                    f"Awaiting start event '{tr.get('start_event', 'unknown')}' — "
                    f"not found in telemetry data."
                )

        # Case 2: timeline rule matched but no events triggered transitions
        if not transition_log:
            pending_triggers: list[str] = []
            for tr in timeline_status:
                if tr.get("start_event_matched"):
                    pending_triggers.append(tr.get("overdue_transition", ""))
            if matched_events:
                matched_count = sum(1 for e in matched_events if e.get("matched"))
                if matched_count == 0:
                    return (
                        "No matching events found — telemetry data does not "
                        "contain events that trigger this obligation's transitions."
                    )
            return (
                "No matching telemetry events found for this obligation's "
                "transition triggers."
            )

        # Case 3: some transitions fired but not terminal
        last = transition_log[-1]
        return (
            f"In progress: reached '{last.get('target', current_state)}' — "
            f"awaiting further events to reach a terminal state."
        )

    # ── Fallback ──────────────────────────────────────────────────
    return f"Status: {status}, state: {current_state}."


def _serialize_verdict(verdict: Any) -> dict[str, Any]:
    """Serialize a ComplianceVerdict to a JSON-safe dict.

    Enriches the serialised verdict with a human-readable
    ``explanation`` field derived from the evidence trail.
    """
    try:
        data = verdict.model_dump(mode="json", exclude_none=True)
    except AttributeError:
        data = dict(verdict)
    # Attach the explanation — deterministic, derived from evidence
    data["explanation"] = _derive_explanation(verdict)
    return data
