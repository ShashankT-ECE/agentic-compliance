"""
Locked FSM data model.

Defines the LockedFSM — a human-reviewed, hash-sealed FSM snapshot that
passes through the HITL gate between Node 2 (FSM Extractor) and Node 3
(Assertion Evaluator).

Each LockedFSM wraps a HybridFSM with approval metadata, an integrity hash,
and a hash chain link for audit trail verifiability.

Architecture constraint: LockedFSM creation must NEVER call an LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.models.fsm import HybridFSM
from app.models.scoreboard import HashLink


# ---------------------------------------------------------------------------
# Lock status
# ---------------------------------------------------------------------------


class LockStatus(str, Enum):
    """Review status of a LockedFSM.

    Transitions are one-way:
      PENDING_REVIEW → APPROVED | REJECTED | AMENDED
    Once resolved, a LockedFSM never returns to PENDING_REVIEW.
    """

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    AMENDED = "amended"


# ---------------------------------------------------------------------------
# Amendment record
# ---------------------------------------------------------------------------


class AmendmentRecord(BaseModel):
    """A single amendment in the LockedFSM's version history.

    Each amendment preserves the prior FSM state so the full lifecycle
    of every FSM can be reconstructed for auditing.
    """

    version: int = Field(..., ge=1, description="Version number before this amendment")
    amended_by: str = Field(..., min_length=1, description="Identity of the reviewer who amended")
    amended_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the amendment",
    )
    changes: str = Field(..., min_length=1, description="Description of what was changed and why")
    prior_fsm: HybridFSM = Field(..., description="The FSM as it existed before this amendment")


# ---------------------------------------------------------------------------
# Locked FSM
# ---------------------------------------------------------------------------


class LockedFSM(BaseModel):
    """A human-reviewed, hash-sealed FSM snapshot.

    Created by the HITL gate after Node 2 extracts FSMs.  Each LockedFSM
    is individually reviewed (approved, rejected, or amended) and sealed
    into the audit hash chain.

    Once approved or amended, the LockedFSM is immutable — any post-hoc
    tampering is detected by recomputing the integrity_hash.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    locked_fsm_id: str = Field(
        default_factory=lambda: f"LOCKED-{uuid4().hex[:12].upper()}",
        description="Unique identifier for this locked record",
    )
    fsm_id: str = Field(
        ...,
        min_length=1,
        description="References the original HybridFSM.fsm_id",
    )
    obligation_ref: str = Field(
        ...,
        min_length=1,
        description="References the source ObligationClause.clause_id",
    )
    circular_ref: str = Field(
        ...,
        min_length=1,
        description="References the source SEBI circular",
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Version number; increments on each amendment",
    )

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    original_fsm: HybridFSM = Field(
        ...,
        description="The FSM content — as extracted (v1) or as amended (v2+)",
    )

    # ------------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------------

    status: LockStatus = Field(
        default=LockStatus.PENDING_REVIEW,
        description="Current review status",
    )
    reviewer: str | None = Field(
        default=None,
        description="Identity of the human reviewer (set on approve/reject/amend)",
    )
    reviewed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of the review decision",
    )
    review_comments: str | None = Field(
        default=None,
        description="Free-text rationale, notes, or rejection reason",
    )

    # ------------------------------------------------------------------
    # Amendment history
    # ------------------------------------------------------------------

    amendment_history: list[AmendmentRecord] = Field(
        default_factory=list,
        description="Ordered list of prior versions (populated on amendment)",
    )

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    integrity_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of serialized original_fsm at lock time",
    )
    hash_link: HashLink | None = Field(
        default=None,
        description="Hash chain link anchoring this locked FSM in the audit trail",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def validate_reviewer_set_when_resolved(self) -> "LockedFSM":
        """Reviewer is required when status is not PENDING_REVIEW."""
        if self.status != LockStatus.PENDING_REVIEW:
            if not self.reviewer or not self.reviewer.strip():
                raise ValueError(
                    f"LockedFSM '{self.locked_fsm_id}': "
                    f"reviewer is required when status is '{self.status.value}'"
                )
        return self

    @model_validator(mode="after")
    def validate_reviewed_at_set_when_resolved(self) -> "LockedFSM":
        """reviewed_at is required when status is not PENDING_REVIEW."""
        if self.status != LockStatus.PENDING_REVIEW:
            if self.reviewed_at is None:
                raise ValueError(
                    f"LockedFSM '{self.locked_fsm_id}': "
                    f"reviewed_at is required when status is '{self.status.value}'"
                )
        return self

    @model_validator(mode="after")
    def validate_review_comments_for_rejection(self) -> "LockedFSM":
        """review_comments is required when status is REJECTED."""
        if self.status == LockStatus.REJECTED:
            if not self.review_comments or not self.review_comments.strip():
                raise ValueError(
                    f"LockedFSM '{self.locked_fsm_id}': "
                    "review_comments is required when rejecting an FSM"
                )
        return self

    @model_validator(mode="after")
    def validate_integrity_hash_set_when_approved_or_amended(self) -> "LockedFSM":
        """integrity_hash is required when status is APPROVED or AMENDED."""
        if self.status in (LockStatus.APPROVED, LockStatus.AMENDED):
            if self.integrity_hash is None or len(self.integrity_hash) != 64:
                raise ValueError(
                    f"LockedFSM '{self.locked_fsm_id}': "
                    f"integrity_hash is required when status is '{self.status.value}'"
                )
        return self

    @model_validator(mode="after")
    def validate_hash_link_set_when_approved_or_amended(self) -> "LockedFSM":
        """hash_link is required when status is APPROVED or AMENDED."""
        if self.status in (LockStatus.APPROVED, LockStatus.AMENDED):
            if self.hash_link is None:
                raise ValueError(
                    f"LockedFSM '{self.locked_fsm_id}': "
                    f"hash_link is required when status is '{self.status.value}'"
                )
        return self

    @model_validator(mode="after")
    def validate_fsm_id_matches_original(self) -> "LockedFSM":
        """Ensure fsm_id matches the wrapped original_fsm.fsm_id."""
        if self.fsm_id != self.original_fsm.fsm_id:
            raise ValueError(
                f"LockedFSM '{self.locked_fsm_id}': "
                f"fsm_id '{self.fsm_id}' does not match original_fsm.fsm_id "
                f"'{self.original_fsm.fsm_id}'"
            )
        return self

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def is_resolved(self) -> bool:
        """True if this LockedFSM has been reviewed (approved, rejected, or amended)."""
        return self.status != LockStatus.PENDING_REVIEW

    @property
    def is_approved_or_amended(self) -> bool:
        """True if this LockedFSM is ready for Node 3 evaluation."""
        return self.status in (LockStatus.APPROVED, LockStatus.AMENDED)
