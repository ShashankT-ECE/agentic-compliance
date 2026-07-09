"""
HITL review log repository — V2 M4 Phase 4.

PostgreSQL-backed repository for ``hitl_review_log``.
Append-only audit trail — INSERT only, never UPDATE or DELETE.

Replaces ``data/locked_fsms/{run_id}/_review_log.json``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HitlReviewLogModel
from app.db.repos.base import BaseRepository

logger = logging.getLogger(__name__)


class HitlReviewRepo(BaseRepository):
    """Repository for ``hitl_review_log`` — append-only audit trail."""

    # ------------------------------------------------------------------
    # Write (append only)
    # ------------------------------------------------------------------

    async def append(
        self,
        *,
        pipeline_run_id: str,
        locked_fsm_id: str,
        fsm_id: str,
        obligation_ref: str,
        action: str,
        reviewer: str,
        comments: str | None = None,
    ) -> None:
        """Append an immutable review log entry.

        Args:
            pipeline_run_id: Owning pipeline run.
            locked_fsm_id: The LockedFSM that was acted upon.
            fsm_id: The underlying HybridFSM ID.
            obligation_ref: Source obligation reference.
            action: 'approved', 'rejected', or 'amended'.
            reviewer: Identity of the human reviewer.
            comments: Optional rationale.
        """
        row = HitlReviewLogModel(
            pipeline_run_id=pipeline_run_id,
            locked_fsm_id=locked_fsm_id,
            fsm_id=fsm_id,
            obligation_ref=obligation_ref,
            action=action,
            reviewer=reviewer,
            comments=comments,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.flush()
        logger.debug(
            "HITL audit: %s %s by %s", action, locked_fsm_id, reviewer
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_run(self, pipeline_run_id: str) -> list[dict]:
        """Return all review log entries for a pipeline run, in order."""
        stmt = (
            select(HitlReviewLogModel)
            .where(HitlReviewLogModel.pipeline_run_id == pipeline_run_id)
            .order_by(HitlReviewLogModel.created_at)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "pipeline_run_id": r.pipeline_run_id,
                "locked_fsm_id": r.locked_fsm_id,
                "fsm_id": r.fsm_id,
                "obligation_ref": r.obligation_ref,
                "action": r.action,
                "reviewer": r.reviewer,
                "comments": r.comments,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
