"""
Locked FSM repository — V2 M4 Phase 4.

PostgreSQL-backed repository for ``locked_fsms``.
Replaces ``data/locked_fsms/{run_id}/LOCKED-*.json`` disk files.

All public methods are async.  The disk-files path remains as a fallback
for backward compatibility and server startup before PG is available.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LockedFsmModel
from app.db.repos.base import BaseRepository

logger = logging.getLogger(__name__)


class LockedFsmRepo(BaseRepository):
    """Repository for ``locked_fsms`` table."""

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save_batch(self, locked_fsms: list, run_id: str) -> int:
        """Insert or update a batch of LockedFSM records (upsert).

        Called when the HITL gate first creates FSMs, and after each
        approve/reject/amend action re-saves the entire batch.

        Returns the number of rows affected.
        """
        if not locked_fsms:
            return 0

        now = datetime.now(timezone.utc)
        values = [self._to_db_dict(lf, run_id, now) for lf in locked_fsms]

        stmt = pg_insert(LockedFsmModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["locked_fsm_id"],
            set_={
                "status": stmt.excluded.status,
                "version": stmt.excluded.version,
                "reviewer": stmt.excluded.reviewer,
                "reviewed_at": stmt.excluded.reviewed_at,
                "review_comments": stmt.excluded.review_comments,
                "integrity_hash": stmt.excluded.integrity_hash,
                "original_fsm": stmt.excluded.original_fsm,
                "amendment_history": stmt.excluded.amendment_history,
                "hash_link": stmt.excluded.hash_link,
            },
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        logger.info("Saved %d locked FSM(s) for run '%s'", len(values), run_id)
        return result.rowcount

    async def update_one(self, locked_fsm, run_id: str) -> None:
        """Update a single LockedFSM record (optimistic — no full batch save)."""
        now = datetime.now(timezone.utc)
        values = self._to_db_dict(locked_fsm, run_id, now)
        stmt = (
            update(LockedFsmModel)
            .where(LockedFsmModel.locked_fsm_id == locked_fsm.locked_fsm_id)
            .values(**{
                k: v for k, v in values.items()
                if k in (
                    "status", "version", "reviewer", "reviewed_at",
                    "review_comments", "integrity_hash", "original_fsm",
                    "amendment_history", "hash_link",
                )
            })
        )
        await self._session.execute(stmt)
        await self._session.flush()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_run(self, run_id: str) -> list:
        """Return all LockedFSM records for a pipeline run."""
        stmt = (
            select(LockedFsmModel)
            .where(LockedFsmModel.pipeline_run_id == run_id)
            .order_by(LockedFsmModel.created_at)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._to_pydantic(r) for r in rows]

    async def get_one(self, locked_fsm_id: str) -> dict | None:
        """Return a single LockedFSM as a dict, or None."""
        row = await self._session.get(LockedFsmModel, locked_fsm_id)
        if row is None:
            # Also try scanning by run? No — the caller must know the ID.
            return None
        return self._to_pydantic(row).model_dump(mode="json", exclude_none=True)

    async def count_pending(self, run_id: str) -> int:
        """Return the number of FSM records still PENDING_REVIEW for a run."""
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(LockedFsmModel)
            .where(
                LockedFsmModel.pipeline_run_id == run_id,
                LockedFsmModel.status == "pending_review",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def has_pending(self, run_id: str) -> bool:
        """Return True if any FSM for the run is still PENDING_REVIEW."""
        return await self.count_pending(run_id) > 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pydantic(row: LockedFsmModel):
        """Convert ORM row → Pydantic LockedFSM."""
        from app.models.locked_fsm import LockedFSM, LockStatus
        from app.models.fsm import HybridFSM

        original_fsm = row.original_fsm if isinstance(row.original_fsm, dict) else {}
        try:
            fsm = HybridFSM.model_validate(original_fsm)
        except Exception:
            fsm = HybridFSM(
                fsm_id=row.fsm_id,
                obligation_ref=row.obligation_ref,
                circular_ref=row.circular_ref,
                initial_state="PENDING",
                states=[
                    {"name": "PENDING"}, {"name": "DUE"},
                    {"name": "COMPLIANT"}, {"name": "LATE"}, {"name": "NON_COMPLIANT"},
                ],
                transitions=[
                    {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "start"},
                    {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "complied"},
                ],
            )

        status = LockStatus.PENDING_REVIEW
        try:
            status = LockStatus(row.status)
        except ValueError:
            pass

        return LockedFSM(
            locked_fsm_id=row.locked_fsm_id,
            fsm_id=row.fsm_id,
            obligation_ref=row.obligation_ref,
            circular_ref=row.circular_ref,
            version=row.version,
            original_fsm=fsm,
            status=status,
            reviewer=row.reviewer,
            reviewed_at=row.reviewed_at,
            review_comments=row.review_comments,
            integrity_hash=row.integrity_hash,
            amendment_history=row.amendment_history if isinstance(row.amendment_history, list) else [],
            hash_link=row.hash_link if isinstance(row.hash_link, dict) else None,
        )

    @staticmethod
    def _to_db_dict(lf, run_id: str, now: datetime) -> dict:
        """Convert LockedFSM Pydantic → DB column dict."""
        status_str = lf.status.value if hasattr(lf.status, 'value') else str(lf.status)
        return {
            "locked_fsm_id": lf.locked_fsm_id,
            "pipeline_run_id": run_id,
            "fsm_id": lf.fsm_id,
            "obligation_ref": lf.obligation_ref,
            "circular_ref": lf.circular_ref,
            "version": lf.version,
            "status": status_str,
            "reviewer": lf.reviewer,
            "reviewed_at": lf.reviewed_at,
            "review_comments": lf.review_comments,
            "integrity_hash": lf.integrity_hash,
            "original_fsm": lf.original_fsm.model_dump(mode="json", exclude_none=True),
            "amendment_history": [
                a.model_dump(mode="json", exclude_none=True) if hasattr(a, 'model_dump') else a
                for a in (lf.amendment_history or [])
            ],
            "hash_link": lf.hash_link.model_dump(mode="json", exclude_none=True) if lf.hash_link else None,
            "created_at": now,
        }
