"""
Pipeline node — Obligation evaluator (Node 3).

Evaluates compliance status by matching broker telemetry data against
approved LockedFSM definitions. Produces per-obligation ComplianceVerdicts
with complete evidence trails for auditability.

CRITICAL ARCHITECTURAL CONSTRAINT
---------------------------------
Node 3 is 100% DETERMINISTIC. It MUST NEVER call an LLM or make HTTP
requests to external services. All evaluation is done by matching
telemetry events against FSM state transitions using pure Python.

Forbidden:
    - OpenAI / Anthropic / DeepSeek / any LLM API
    - LangChain LLMs or agents
    - Prompt templates or AI reasoning
    - HTTP calls (requests, httpx, urllib)
    - Any non-deterministic operation

Same LockedFSMs + same TelemetryEvents MUST always produce identical verdicts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.fsm import HybridFSM
from app.models.locked_fsm import LockedFSM, LockStatus
from app.models.telemetry import TelemetryEvent
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.utils.state_machine import StateMachine
from app.utils.timeline_evaluator import TimelineEvaluator, _parse_timestamp

logger = logging.getLogger(__name__)


def evaluate_compliance(
    locked_fsms: list[LockedFSM],
    telemetry_events: list[TelemetryEvent],
) -> list[ComplianceVerdict]:
    """Evaluate compliance by matching telemetry events against approved LockedFSMs.

    Completely deterministic: for each approved/amended LockedFSM, walks
    state transitions using telemetry events as triggers, evaluates timeline
    constraints, and produces a ComplianceVerdict with a full evidence trail.

    Processing steps:
        1. Filter LockedFSMs to only approved or amended status.
        2. Convert TelemetryEvents to dicts and sort by timestamp.
        3. For each LockedFSM:
           a. Initialise a StateMachine from its wrapped HybridFSM.
           b. Process every event — match event_type against transitions.
           c. Evaluate timeline rules if the FSM defines any.
           d. Determine canonical compliance status.
           e. Map to VerdictStatus.
           f. Build evidence trail.
           g. Produce a ComplianceVerdict.

    Args:
        locked_fsms: List of LockedFSM records with status APPROVED or AMENDED.
            FSMs with other statuses are silently skipped.
        telemetry_events: List of TelemetryEvent records from broker systems.

    Returns:
        List of ComplianceVerdict objects (one per approved/amended LockedFSM).
        Returns empty list if no approved LockedFSMs are provided.

    Raises:
        ValueError: If an FSM definition is structurally invalid.
    """
    # Filter to approved / amended only
    active_fsms = [
        lf for lf in locked_fsms
        if lf.status in (LockStatus.APPROVED, LockStatus.AMENDED)
    ]

    if not active_fsms:
        logger.info("evaluate_compliance: no approved/amended LockedFSMs — returning []")
        return []

    # ── Convert telemetry to dicts and sort chronologically ──────────
    event_dicts = [_event_to_dict(e) for e in telemetry_events]
    sorted_events = _sort_by_timestamp(event_dicts)

    logger.debug(
        "evaluate_compliance: processing %d LockedFSM(s) against %d event(s)",
        len(active_fsms), len(sorted_events),
    )

    # Extract broker_id(s) from events
    broker_ids = sorted({e.get("broker_id", "") for e in sorted_events if e.get("broker_id")})
    broker_id = next(iter(broker_ids), "UNKNOWN")

    verdicts: list[ComplianceVerdict] = []

    for lf in active_fsms:
        try:
            verdict = _evaluate_single_fsm(lf, sorted_events, broker_id)
            verdicts.append(verdict)
        except Exception:
            logger.exception(
                "Failed to evaluate LockedFSM '%s' (fsm_id='%s')",
                lf.locked_fsm_id, lf.fsm_id,
            )
            verdicts.append(
                ComplianceVerdict(
                    obligation_ref=lf.obligation_ref,
                    broker_id=broker_id,
                    fsm_ref=lf.fsm_id,
                    status=VerdictStatus.PENDING,
                    current_state="ERROR",
                    evidence={"error": "Evaluation failed — see logs"},
                )
            )

    return verdicts


# ── Per-FSM evaluation ───────────────────────────────────────────────


def _evaluate_single_fsm(
    lf: LockedFSM,
    sorted_events: list[dict],
    broker_id: str,
) -> ComplianceVerdict:
    """Evaluate a single LockedFSM against the sorted telemetry events.

    Args:
        lf: An approved/amended LockedFSM.
        sorted_events: Telemetry events sorted by timestamp ascending.
        broker_id: Broker identifier for the verdict.

    Returns:
        A ComplianceVerdict with full evidence.
    """
    fsm: HybridFSM = lf.original_fsm

    # 1. Initialise and run state machine
    sm = StateMachine(fsm)
    sm.apply_events(sorted_events)

    # 2. Evaluate timeline rules
    timeline_results = _evaluate_timeline_rules(fsm, sorted_events)

    # 3. Check if any timeline rule indicates a missed deadline
    deadline_met = _aggregate_deadline(timeline_results)

    # 4. Determine canonical compliance status
    canonical_status = sm.determine_compliance_status(deadline_met=deadline_met)

    # 5. Map canonical status to VerdictStatus
    verdict_status = _map_status(canonical_status)

    # 6. Build evidence
    evidence = _build_evidence(sorted_events, sm.history, timeline_results)

    logger.debug(
        "FSM '%s': final_state=%s canonical=%s verdict=%s",
        fsm.fsm_id, sm.current_state, canonical_status, verdict_status.value,
    )

    return ComplianceVerdict(
        obligation_ref=lf.obligation_ref,
        broker_id=broker_id,
        fsm_ref=lf.fsm_id,
        status=verdict_status,
        current_state=sm.current_state,
        evidence=evidence,
    )


# ── Timeline evaluation helpers ──────────────────────────────────────


def _evaluate_timeline_rules(
    fsm: HybridFSM,
    sorted_events: list[dict],
) -> list[dict]:
    """Evaluate all timeline rules defined in the FSM.

    Args:
        fsm: The HybridFSM containing timeline_rules.
        sorted_events: Chronologically sorted event dicts.

    Returns:
        List of timeline evaluation result dicts, one per rule.
    """
    results: list[dict] = []
    for rule in fsm.timeline_rules:
        result = TimelineEvaluator.evaluate_timeline_rule(sorted_events, rule)
        results.append(result)
    return results


def _aggregate_deadline(timeline_results: list[dict]) -> bool | None:
    """Aggregate timeline evaluation results into a single deadline_met value.

    Returns:
        True if all rules with a matched start_event have deadline_met=True.
        False if any rule has deadline_met=False.
        None if no rules exist or no start_events were matched.
    """
    if not timeline_results:
        return None

    evaluated = [r for r in timeline_results if r.get("deadline_met") is not None]
    if not evaluated:
        return None

    return all(r["deadline_met"] for r in evaluated)


# ── Status mapping ───────────────────────────────────────────────────


def _map_status(canonical: str) -> VerdictStatus:
    """Map a canonical 5-state compliance status to a VerdictStatus.

    Mapping:
        COMPLIANT      → COMPLIANT
        DUE            → PENDING (awaits more events)
        PENDING        → PENDING
        LATE           → NON_COMPLIANT
        NON_COMPLIANT  → NON_COMPLIANT
    """
    if canonical == StateMachine.STATUS_COMPLIANT:
        return VerdictStatus.COMPLIANT
    elif canonical in (StateMachine.STATUS_DUE, StateMachine.STATUS_PENDING):
        return VerdictStatus.PENDING
    elif canonical in (StateMachine.STATUS_LATE, StateMachine.STATUS_NON_COMPLIANT):
        return VerdictStatus.NON_COMPLIANT
    return VerdictStatus.PENDING


# ── Evidence trail ───────────────────────────────────────────────────


def _build_evidence(
    sorted_events: list[dict],
    transition_history: list[dict],
    timeline_results: list[dict] | None = None,
) -> dict:
    """Build the evidence trail dict for a verdict.

    Args:
        sorted_events: Chronologically sorted telemetry events.
        transition_history: Complete transition records from the StateMachine.
        timeline_results: Optional timeline rule evaluation results.

    Returns:
        Evidence dict with matched_events, transition_log, and timeline_status.
    """
    # Build set of (event_index, trigger) pairs that matched
    matched_set: set[tuple[int, str]] = set()
    for t in transition_history:
        matched_set.add((t.get("event_index", -1), t.get("trigger", "")))

    matched_events: list[dict] = []
    for i, event in enumerate(sorted_events):
        event_index = i + 1  # 1-based to match StateMachine
        matched = (event_index, event.get("event_type", "")) in matched_set
        matched_events.append({
            "event_index": i,
            "timestamp": _serialize_ts(event.get("timestamp")),
            "event_type": event.get("event_type"),
            "broker_id": event.get("broker_id"),
            "matched": matched,
        })

    return {
        "matched_events": matched_events,
        "transition_log": transition_history,
        "timeline_status": timeline_results or [],
    }


# ── Event conversion and sorting ─────────────────────────────────────


def _event_to_dict(event: TelemetryEvent) -> dict:
    """Convert a TelemetryEvent Pydantic model to a plain dict for the
    state machine engine.
    """
    return {
        "event_id": event.event_id,
        "broker_id": event.broker_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "payload": event.payload,
    }


def _sort_by_timestamp(events: list[dict]) -> list[dict]:
    """Sort event dicts chronologically by timestamp.

    Stable sort preserves insertion order for events with identical timestamps.
    Unparseable timestamps sort last.
    """
    if not events:
        return []

    def _key(record: dict) -> datetime:
        ts = record.get("timestamp")
        try:
            return _parse_timestamp(ts)
        except Exception:
            logger.warning("Unparseable timestamp: %r", ts)
            return datetime.max.replace(tzinfo=timezone.utc)

    return sorted(events, key=_key)


def _serialize_ts(ts: object) -> str:
    """Serialize a timestamp to ISO-8601 string for evidence output."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return str(ts)
