"""
Pipeline node — Scoreboard Generator (Node 4).

Aggregates ComplianceVerdicts from Node 3 into a structured Scoreboard
with per-broker summaries, compliance rates, and a hash-chain integrity seal.

Architecture: Formatting and aggregation only — no LLM, no business logic.
All business logic belongs in Node 3 (Evaluator).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from app.models.scoreboard import BrokerScore, HashChain, ObligationResult, Scoreboard
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.utils.hash_chain import build_chain, compute_hash

logger = logging.getLogger(__name__)


def generate_scoreboard(
    verdicts: list[ComplianceVerdict],
    circular_id: str,
    metadata: dict[str, Any] | None = None,
) -> Scoreboard:
    """Generate a compliance Scoreboard from a list of ComplianceVerdicts.

    Aggregates verdicts by broker, computes per-broker compliance rates and
    obligation-level details, then seals the result with a hash chain for
    audit integrity.

    Processing steps:
        1. Group verdicts by broker_id.
        2. For each broker: count by VerdictStatus, build ObligationResult
           records, compute compliance_rate.
        3. Build a HashChain from the serialized broker summaries.
        4. Wrap everything in a Scoreboard model.

    Args:
        verdicts: List of ComplianceVerdict objects from Node 3 (Evaluator).
        circular_id: SEBI circular reference this scoreboard covers.
        metadata: Optional dict of pipeline run metadata (run_id, version, etc.).

    Returns:
        A Scoreboard with per-broker summaries and hash-chain integrity.

    Raises:
        ValueError: Never raised directly — BrokerScore model validators
            enforce count/rate consistency (raises on bad construction).
    """
    if not verdicts:
        logger.info("generate_scoreboard: empty verdicts — returning empty scoreboard")
        return Scoreboard(
            circular_id=circular_id,
            metadata=metadata or {},
        )

    # ── 1. Group verdicts by broker_id ─────────────────────────────
    by_broker: dict[str, list[ComplianceVerdict]] = defaultdict(list)
    for v in verdicts:
        by_broker[v.broker_id].append(v)

    logger.debug(
        "generate_scoreboard: %d verdict(s) across %d broker(s)",
        len(verdicts), len(by_broker),
    )

    # ── 2. Build per-broker BrokerScore ────────────────────────────
    broker_scores: list[BrokerScore] = []
    for broker_id, broker_verdicts in sorted(by_broker.items()):
        score = _build_broker_score(broker_id, broker_verdicts)
        broker_scores.append(score)

    # ── 3. Build hash chain from broker summaries ─────────────────
    hash_chain = _build_scoreboard_chain(broker_scores)

    # ── 4. Assemble Scoreboard ────────────────────────────────────
    return Scoreboard(
        circular_id=circular_id,
        broker_summaries=broker_scores,
        hash_chain=hash_chain,
        metadata=metadata or {},
    )


# ── Broker-level aggregation ─────────────────────────────────────────


def _build_broker_score(
    broker_id: str,
    verdicts: list[ComplianceVerdict],
) -> BrokerScore:
    """Build a BrokerScore from one broker's ComplianceVerdicts.

    Args:
        broker_id: The broker identifier.
        verdicts: All verdicts for this broker.

    Returns:
        A validated BrokerScore model.
    """
    total = len(verdicts)
    compliant = sum(1 for v in verdicts if v.status == VerdictStatus.COMPLIANT)
    non_compliant = sum(1 for v in verdicts if v.status == VerdictStatus.NON_COMPLIANT)
    pending = total - compliant - non_compliant

    # compliance_rate = compliant / (total - pending), or 1.0 if all pending
    evaluated = total - pending
    rate = compliant / evaluated if evaluated > 0 else 1.0

    # Build obligation detail records
    details: list[ObligationResult] = [
        ObligationResult(
            obligation_ref=v.obligation_ref,
            fsm_ref=v.fsm_ref,
            status=v.status,
            current_state=v.current_state,
            evidence_summary=_summarize_evidence(v.evidence),
            evaluated_at=v.evaluated_at,
        )
        for v in verdicts
    ]

    logger.debug(
        "Broker '%s': %d total, %d compliant, %d non_compliant, %d pending, rate=%.2f",
        broker_id, total, compliant, non_compliant, pending, rate,
    )

    return BrokerScore(
        broker_id=broker_id,
        total_obligations=total,
        compliant=compliant,
        non_compliant=non_compliant,
        pending=pending,
        compliance_rate=round(rate, 4),
        obligation_details=details,
    )


# ── Evidence summarization ───────────────────────────────────────────


def _summarize_evidence(evidence: dict[str, Any]) -> str:
    """Extract a human-readable summary from the evidence trail dict.

    The evidence dict (produced by Node 3) contains:
        matched_events: list of {event_index, event_type, matched, ...}
        transition_log: list of transition records
        timeline_status: list of timeline rule evaluation results

    Returns:
        A compact summary string suitable for ObligationResult.evidence_summary.
    """
    matched_events = evidence.get("matched_events", [])
    transition_log = evidence.get("transition_log", [])
    timeline_status = evidence.get("timeline_status", [])

    total_events = len(matched_events)
    matched_count = sum(1 for e in matched_events if e.get("matched"))
    transition_count = len(transition_log)

    # Timeline status: aggregate deadline_met values
    timeline_parts: list[str] = []
    if timeline_status:
        for ts in timeline_status:
            if ts.get("start_event_matched") is False:
                timeline_parts.append("start_event_not_matched")
            elif ts.get("deadline_met") is True:
                timeline_parts.append("deadline_met")
            elif ts.get("deadline_met") is False:
                timeline_parts.append("deadline_missed")
            else:
                timeline_parts.append("timeline_none")
    else:
        timeline_parts.append("no_timeline_rules")

    timeline_str = ", ".join(timeline_parts)

    return (
        f"{matched_count}/{total_events} events matched, "
        f"{transition_count} transitions, "
        f"timeline: {timeline_str}"
    )


# ── Hash chain construction ──────────────────────────────────────────


def _build_scoreboard_chain(
    broker_scores: list[BrokerScore],
) -> HashChain | None:
    """Build a hash chain from broker score summaries.

    Each broker summary is serialized to a canonical dict and sealed
    into the chain. An empty chain is None.

    Args:
        broker_scores: Ordered list of BrokerScore models.

    Returns:
        A HashChain if there are broker scores, None otherwise.
    """
    if not broker_scores:
        return None

    data_items: list[dict[str, Any]] = []
    for bs in broker_scores:
        data_items.append({
            "broker_id": bs.broker_id,
            "total_obligations": bs.total_obligations,
            "compliant": bs.compliant,
            "non_compliant": bs.non_compliant,
            "pending": bs.pending,
            "compliance_rate": bs.compliance_rate,
            "data_hash": compute_hash(
                {o.obligation_ref: o.status.value for o in bs.obligation_details}
            ),
        })

    chain = build_chain(data_items)
    logger.debug("Built hash chain with %d link(s)", chain.length)
    return chain
