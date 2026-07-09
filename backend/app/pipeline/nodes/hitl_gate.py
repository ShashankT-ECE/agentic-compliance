"""
Pipeline node — HITL Gate (Human-in-the-Loop).

Sits between Node 2 (FSM Extractor) and Node 3 (Assertion Evaluator).
Creates LockedFSM records from extracted HybridFSMs, pauses the pipeline
for human review, and releases approved/amended FSMs to the evaluator.

Architecture:
  1. Receive extracted_fsms from Node 2
  2. Create PENDING LockedFSM records
  3. Persist to data/locked_fsms/{run_id}/
  4. Pipeline PAUSES at AWAITING_APPROVAL
  5. Human reviews via API (approve / reject / amend)
  6. On all-resolved: verify hash chain, populate locked_fsms, resume → Node 3
  7. On any-rejected: route back to Node 2 with hitl_notes

⚠️  CONSTRAINT: This node must NEVER call an LLM. All logic is deterministic.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.fsm import HybridFSM
from app.models.locked_fsm import AmendmentRecord, LockedFSM, LockStatus
from app.models.scoreboard import HashChain, HashLink
from app.utils.hash_chain import GENESIS_PREVIOUS_HASH, compute_hash, link, verify_chain

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_LOCKED_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "locked_fsms"


# ---------------------------------------------------------------------------
# LockedFSM creation
# ---------------------------------------------------------------------------


def create_locked_fsms(extracted_fsms: list[HybridFSM], circular_ref: str) -> list[LockedFSM]:
    """Create PENDING LockedFSM records from extracted HybridFSMs.

    Each HybridFSM is wrapped in a LockedFSM with status=PENDING_REVIEW,
    awaiting human review.  No hash is computed yet — that happens on approval.

    Args:
        extracted_fsms: HybridFSMs from Node 2.
        circular_ref: SEBI circular reference.

    Returns:
        List of LockedFSM records, one per input FSM, all PENDING_REVIEW.

    Raises:
        ValueError: If extracted_fsms is empty.
    """
    if not extracted_fsms:
        raise ValueError("extracted_fsms is empty — cannot create LockedFSM records")

    locked_fsms: list[LockedFSM] = []
    for fsm in extracted_fsms:
        locked = LockedFSM(
            fsm_id=fsm.fsm_id,
            obligation_ref=fsm.obligation_ref,
            circular_ref=circular_ref,
            version=1,
            original_fsm=fsm,
            status=LockStatus.PENDING_REVIEW,
        )
        locked_fsms.append(locked)
        logger.debug("Created LockedFSM: %s for obligation %s", locked.locked_fsm_id, fsm.obligation_ref)

    logger.info("Created %d LockedFSM record(s) — awaiting review", len(locked_fsms))
    return locked_fsms


# ---------------------------------------------------------------------------
# Review actions
# ---------------------------------------------------------------------------


def approve_fsm(
    locked_fsm: LockedFSM,
    reviewer: str,
    comments: str | None = None,
    previous_hash_link: HashLink | None = None,
) -> LockedFSM:
    """Approve a LockedFSM as-is and seal it into the hash chain.

    Computes the integrity_hash from the original_fsm, creates a hash chain
    link, and sets status to APPROVED.

    Args:
        locked_fsm: The LockedFSM to approve (must be PENDING_REVIEW).
        reviewer: Identity of the approving human.
        comments: Optional review notes.
        previous_hash_link: The previous link in the run's hash chain (None for genesis).

    Returns:
        A new LockedFSM instance with status=APPROVED, integrity_hash set,
        and hash_link anchored.

    Raises:
        ValueError: If locked_fsm is not in PENDING_REVIEW status.
    """
    if locked_fsm.status != LockStatus.PENDING_REVIEW:
        raise ValueError(
            f"Cannot approve LockedFSM '{locked_fsm.locked_fsm_id}': "
            f"status is '{locked_fsm.status.value}', expected 'pending_review'"
        )

    # Compute integrity hash from the FSM content
    fsm_json = locked_fsm.original_fsm.model_dump_json(exclude_none=True)
    integrity_hash = compute_hash(fsm_json)

    # Create hash chain link
    link_data: dict[str, Any] = {
        "locked_fsm_id": locked_fsm.locked_fsm_id,
        "fsm_id": locked_fsm.fsm_id,
        "obligation_ref": locked_fsm.obligation_ref,
        "circular_ref": locked_fsm.circular_ref,
        "version": locked_fsm.version,
        "action": "approved",
        "reviewer": reviewer,
        "integrity_hash": integrity_hash,
    }
    hash_link = link(previous_hash_link, link_data)

    updated = locked_fsm.model_copy(deep=True)
    updated.status = LockStatus.APPROVED
    updated.reviewer = reviewer
    updated.reviewed_at = datetime.now(timezone.utc)
    updated.review_comments = comments
    updated.integrity_hash = integrity_hash
    updated.hash_link = hash_link

    logger.info(
        "Approved LockedFSM '%s' (obligation: %s, hash_link index: %d)",
        locked_fsm.locked_fsm_id,
        locked_fsm.obligation_ref,
        hash_link.index,
    )
    return updated


def reject_fsm(
    locked_fsm: LockedFSM,
    reviewer: str,
    comments: str,
) -> LockedFSM:
    """Reject a LockedFSM with mandatory rationale.

    Args:
        locked_fsm: The LockedFSM to reject (must be PENDING_REVIEW).
        reviewer: Identity of the rejecting human.
        comments: Reason for rejection (required).

    Returns:
        A new LockedFSM instance with status=REJECTED.

    Raises:
        ValueError: If locked_fsm is not PENDING_REVIEW, or comments is empty.
    """
    if locked_fsm.status != LockStatus.PENDING_REVIEW:
        raise ValueError(
            f"Cannot reject LockedFSM '{locked_fsm.locked_fsm_id}': "
            f"status is '{locked_fsm.status.value}', expected 'pending_review'"
        )
    if not comments or not comments.strip():
        raise ValueError("review_comments is required when rejecting an FSM")

    updated = locked_fsm.model_copy(deep=True)
    updated.status = LockStatus.REJECTED
    updated.reviewer = reviewer
    updated.reviewed_at = datetime.now(timezone.utc)
    updated.review_comments = comments

    logger.info(
        "Rejected LockedFSM '%s' (obligation: %s) — reason: %s",
        locked_fsm.locked_fsm_id,
        locked_fsm.obligation_ref,
        comments[:100],
    )
    return updated


def amend_fsm(
    locked_fsm: LockedFSM,
    corrected_fsm: HybridFSM,
    reviewer: str,
    comments: str,
    previous_hash_link: HashLink | None = None,
) -> LockedFSM:
    """Amend a LockedFSM with a human-corrected FSM.

    Preserves the prior FSM in amendment_history, increments the version,
    computes a new integrity_hash from the corrected FSM, and seals it
    into the hash chain.

    Args:
        locked_fsm: The LockedFSM to amend (must be PENDING_REVIEW).
        corrected_fsm: The corrected HybridFSM (must pass Pydantic validation).
        reviewer: Identity of the amending human.
        comments: Description of what was changed and why (required).
        previous_hash_link: The previous link in the run's hash chain.

    Returns:
        A new LockedFSM instance with status=AMENDED, version incremented,
        amendment_history updated, integrity_hash recomputed, and hash_link set.

    Raises:
        ValueError: If locked_fsm is not PENDING_REVIEW, or comments is empty.
    """
    if locked_fsm.status != LockStatus.PENDING_REVIEW:
        raise ValueError(
            f"Cannot amend LockedFSM '{locked_fsm.locked_fsm_id}': "
            f"status is '{locked_fsm.status.value}', expected 'pending_review'"
        )
    if not comments or not comments.strip():
        raise ValueError("review_comments is required when amending an FSM")

    # Record the prior version
    amendment = AmendmentRecord(
        version=locked_fsm.version,
        amended_by=reviewer,
        changes=comments,
        prior_fsm=locked_fsm.original_fsm,
    )

    # Compute new integrity hash from the corrected FSM
    corrected_json = corrected_fsm.model_dump_json(exclude_none=True)
    integrity_hash = compute_hash(corrected_json)

    # Create hash chain link for the amendment
    link_data: dict[str, Any] = {
        "locked_fsm_id": locked_fsm.locked_fsm_id,
        "fsm_id": locked_fsm.fsm_id,
        "obligation_ref": locked_fsm.obligation_ref,
        "circular_ref": locked_fsm.circular_ref,
        "version": locked_fsm.version + 1,
        "action": "amended",
        "reviewer": reviewer,
        "changes": comments,
        "integrity_hash": integrity_hash,
    }
    hash_link = link(previous_hash_link, link_data)

    updated = locked_fsm.model_copy(deep=True)
    updated.version = locked_fsm.version + 1
    updated.original_fsm = corrected_fsm
    updated.status = LockStatus.AMENDED
    updated.reviewer = reviewer
    updated.reviewed_at = datetime.now(timezone.utc)
    updated.review_comments = comments
    updated.amendment_history = [*locked_fsm.amendment_history, amendment]
    updated.integrity_hash = integrity_hash
    updated.hash_link = hash_link

    logger.info(
        "Amended LockedFSM '%s' (obligation: %s, version: %d → %d)",
        locked_fsm.locked_fsm_id,
        locked_fsm.obligation_ref,
        locked_fsm.version,
        updated.version,
    )
    return updated


# ---------------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------------


def verify_locked_fsm_integrity(locked_fsm: LockedFSM) -> bool:
    """Verify that a LockedFSM's integrity_hash matches its original_fsm content.

    Recomputes the hash from the stored FSM and compares it to the stored
    integrity_hash.  Detects post-approval tampering.

    Args:
        locked_fsm: A resolved LockedFSM (APPROVED or AMENDED).

    Returns:
        True if the recomputed hash matches the stored integrity_hash.
    """
    if locked_fsm.integrity_hash is None:
        logger.warning("LockedFSM '%s' has no integrity_hash", locked_fsm.locked_fsm_id)
        return False

    fsm_json = locked_fsm.original_fsm.model_dump_json(exclude_none=True)
    recomputed = compute_hash(fsm_json)
    match = recomputed == locked_fsm.integrity_hash

    if not match:
        logger.error(
            "Integrity violation: LockedFSM '%s' hash mismatch! "
            "Stored: %s, Recomputed: %s",
            locked_fsm.locked_fsm_id,
            locked_fsm.integrity_hash,
            recomputed,
        )
    return match


def build_hitl_hash_chain(locked_fsms: list[LockedFSM]) -> HashChain:
    """Build a HashChain from the hash links embedded in resolved LockedFSMs.

    Only FSMs with status APPROVED or AMENDED (which have hash_links) are
    included in the chain.

    Args:
        locked_fsms: List of LockedFSM records (mix of statuses).

    Returns:
        A HashChain containing links from all approved/amended FSMs,
        in the order they appear in the list.
    """
    resolved = [f for f in locked_fsms if f.is_approved_or_amended and f.hash_link is not None]
    links = [f.hash_link for f in resolved]  # type: ignore[misc]
    root_hash = links[0].link_hash if links else GENESIS_PREVIOUS_HASH
    return HashChain(root_hash=root_hash, chain=links)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_locked_fsms(
    locked_fsms: list[LockedFSM],
    run_id: str,
    output_dir: str | Path | None = None,
) -> Path:
    """Persist LockedFSM records and run metadata to disk.

    Writes under ``data/locked_fsms/{run_id}/``:
      - Individual LockedFSM JSON files (one per FSM)
      - ``_pipeline_state.json`` — minimal run metadata
      - ``_review_log.json`` — ordered review audit trail
      - ``_hash_chain.json`` — the full HashChain for this run

    Args:
        locked_fsms: LockedFSM records to persist.
        run_id: Pipeline run identifier (used as directory name).
        output_dir: Optional override for the output root directory.

    Returns:
        Path to the directory where records were written.

    Raises:
        OSError: If the output directory cannot be created or written to.
    """
    base_dir = Path(output_dir) if output_dir else _LOCKED_DATA_DIR
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Persisting %d LockedFSM record(s) to %s", len(locked_fsms), run_dir)

    # Write individual LockedFSM files
    for lfsm in locked_fsms:
        filepath = run_dir / f"{lfsm.locked_fsm_id}.json"
        filepath.write_text(
            lfsm.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
        logger.debug("Wrote LockedFSM: %s", filepath)

    # Write pipeline state snapshot
    state_path = run_dir / "_pipeline_state.json"
    state_data = {
        "run_id": run_id,
        "paused_at": datetime.now(timezone.utc).isoformat(),
        "total_fsms": len(locked_fsms),
        "pending": sum(1 for f in locked_fsms if f.status == LockStatus.PENDING_REVIEW),
        "approved": sum(1 for f in locked_fsms if f.status == LockStatus.APPROVED),
        "rejected": sum(1 for f in locked_fsms if f.status == LockStatus.REJECTED),
        "amended": sum(1 for f in locked_fsms if f.status == LockStatus.AMENDED),
    }
    state_path.write_text(json.dumps(state_data, indent=2, default=str), encoding="utf-8")

    # Write review log (append-only audit trail)
    log_path = run_dir / "_review_log.json"
    log_entries: list[dict[str, Any]] = []
    for lfsm in locked_fsms:
        if lfsm.is_resolved:
            log_entries.append({
                "locked_fsm_id": lfsm.locked_fsm_id,
                "fsm_id": lfsm.fsm_id,
                "obligation_ref": lfsm.obligation_ref,
                "action": lfsm.status.value,
                "reviewer": lfsm.reviewer,
                "timestamp": lfsm.reviewed_at.isoformat() if lfsm.reviewed_at else None,
                "comments": lfsm.review_comments,
            })
    log_path.write_text(json.dumps(log_entries, indent=2, default=str), encoding="utf-8")

    # Write hash chain
    chain_path = run_dir / "_hash_chain.json"
    hash_chain = build_hitl_hash_chain(locked_fsms)
    chain_path.write_text(hash_chain.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")

    logger.info("LockedFSM persistence complete: %s (%d files)", run_dir, len(locked_fsms) + 3)
    return run_dir


def load_locked_fsms(run_id: str, data_dir: str | Path | None = None) -> list[LockedFSM]:
    """Load LockedFSM records from a persisted run directory.

    Args:
        run_id: Pipeline run identifier.
        data_dir: Optional override for the data root directory.

    Returns:
        List of LockedFSM records loaded from disk.

    Raises:
        FileNotFoundError: If the run directory does not exist.
    """
    base_dir = Path(data_dir) if data_dir else _LOCKED_DATA_DIR
    run_dir = base_dir / run_id

    if not run_dir.exists():
        raise FileNotFoundError(f"LockedFSM run directory not found: {run_dir}")

    locked_fsms: list[LockedFSM] = []
    for filepath in sorted(run_dir.glob("LOCKED-*.json")):
        locked_fsms.append(LockedFSM.model_validate_json(filepath.read_text(encoding="utf-8")))

    logger.info("Loaded %d LockedFSM record(s) from %s", len(locked_fsms), run_dir)
    return locked_fsms


# ---------------------------------------------------------------------------
# Pipeline node entry point (for LangGraph integration in M7)
# ---------------------------------------------------------------------------


def hitl_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node function for the HITL Gate.

    Reads ``extracted_fsms`` and ``circular_id`` from pipeline state,
    creates LockedFSM records, persists them, and pauses the pipeline
    at AWAITING_APPROVAL.

    This function does NOT wait for human input — it sets the status
    and returns.  The API layer handles the review workflow.  When all
    FSMs are resolved, the pipeline resumes via the conditional edge.

    Args:
        state: Pipeline state dict (CompliancePipelineState-compatible).

    Returns:
        Updated state dict with status set to AWAITING_APPROVAL.
    """
    from app.pipeline.state import PipelineStatus

    extracted_fsms: list[HybridFSM] = state.get("extracted_fsms", [])
    circular_id: str = state.get("circular_id", "UNKNOWN")
    run_id: str = state.get("run_id", "UNKNOWN")

    if not extracted_fsms:
        raise ValueError("Pipeline state has no 'extracted_fsms' — cannot create LockedFSM records")

    logger.info("HITL gate: creating LockedFSM records for run '%s' (%d FSMs)", run_id, len(extracted_fsms))

    # Create PENDING LockedFSM records
    locked_fsms = create_locked_fsms(extracted_fsms, circular_id)

    # Persist to disk
    persist_locked_fsms(locked_fsms, run_id)

    # Persist to PostgreSQL (V2 M4)
    _save_locked_fsms_to_pg(locked_fsms, run_id)

    # Pause the pipeline
    state["status"] = PipelineStatus.AWAITING_APPROVAL
    state["locked_fsms"] = []  # Not yet approved — populated on resume

    logger.info("HITL gate: pipeline paused at AWAITING_APPROVAL for run '%s'", run_id)
    return state


# =============================================================================
# PG helper (V2 M4)
# =============================================================================


def _save_locked_fsms_to_pg(locked_fsms, run_id: str) -> None:
    """Persist LockedFSM records to PostgreSQL.

    Graceful fallback — if PG is unavailable, records are still on disk.
    """
    import asyncio as _asyncio
    from app.database import AsyncSessionLocal
    from app.db.repos.locked_fsm_repo import LockedFsmRepo

    async def _run():
        async with AsyncSessionLocal() as session:
            repo = LockedFsmRepo(session)
            await repo.save_batch(list(locked_fsms), run_id)
            await session.commit()

    coro = _run()
    try:
        _asyncio.run(coro)
    except Exception:
        pass  # PG unavailable — records are on disk
    finally:
        coro.close()
