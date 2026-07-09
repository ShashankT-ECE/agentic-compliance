"""
Pipeline run repository — V2 M4 Phase 3.

PostgreSQL-backed repository for ``pipeline_runs`` — the primary
aggregate root for the execution layer.  A pipeline run owns its
verdicts and evidence references; they are persisted together in
a single transaction at completion time.

Checkpoint saves (parser → FSM → HITL) write only the run row so
the pipeline can be resumed after a server restart.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    EvidenceReferenceModel,
    PipelineRunModel,
    VerdictModel,
)
from app.db.repos.base import BaseRepository
from app.pipeline.state import CompliancePipelineState

logger = logging.getLogger(__name__)


class PipelineRunRepo(BaseRepository):
    """Repository for the ``pipeline_runs`` aggregate root.

    Owns ``verdicts`` and ``evidence_references`` — they are saved
    together with the run in a single transaction at completion.
    """

    # ------------------------------------------------------------------
    # Checkpoint save — run metadata only
    # ------------------------------------------------------------------

    async def save_checkpoint(self, state: CompliancePipelineState) -> None:
        """Persist the pipeline run row (checkpoint).

        Called at each node transition so the pipeline state survives
        server restarts.  Only the run row is written; verdicts and
        evidence are saved separately at completion time via
        :meth:`save_completed_run`.
        """
        values = self._state_to_db(state)
        stmt = pg_insert(PipelineRunModel).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id"],
            set_={
                "status": stmt.excluded.status,
                "state_blob": stmt.excluded.state_blob,
                "hash_chain_root": stmt.excluded.hash_chain_root,
                "approved_by": stmt.excluded.approved_by,
                "approved_at": stmt.excluded.approved_at,
                "hitl_notes": stmt.excluded.hitl_notes,
                "completed_at": stmt.excluded.completed_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()
        logger.debug("Checkpoint saved for run '%s' [%s]", state.run_id, state.status.value)

    # ------------------------------------------------------------------
    # Completed run — run + verdicts + evidence (single transaction)
    # ------------------------------------------------------------------

    async def save_completed_run(self, state: CompliancePipelineState) -> None:
        """Persist the complete pipeline execution.

        Writes the run row, all verdicts, and all evidence references
        in a single transaction.  If any write fails, the entire
        transaction is rolled back — no orphaned rows.

        The caller owns the transaction boundary (commit/rollback).
        """
        now = datetime.now(timezone.utc)

        # 1. Run row
        values = self._state_to_db(state)
        values["completed_at"] = now
        values["updated_at"] = now
        stmt = pg_insert(PipelineRunModel).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["run_id"],
            set_={
                "status": stmt.excluded.status,
                "state_blob": stmt.excluded.state_blob,
                "hash_chain_root": stmt.excluded.hash_chain_root,
                "completed_at": stmt.excluded.completed_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)

        # 2. Verdicts — batch upsert
        if state.compliance_verdicts:
            verdict_values = [
                self._verdict_to_db(v, state.run_id) for v in state.compliance_verdicts
            ]
            v_stmt = pg_insert(VerdictModel).values(verdict_values)
            v_stmt = v_stmt.on_conflict_do_update(
                index_elements=["verdict_id"],
                set_={
                    "status": v_stmt.excluded.status,
                    "current_state": v_stmt.excluded.current_state,
                    "evidence": v_stmt.excluded.evidence,
                },
            )
            await self._session.execute(v_stmt)

        # 3. Evidence references — batch upsert
        if state.evidence_map:
            ev_values = [
                self._evidence_to_db(ev_dict, state.run_id)
                for ev_dict in state.evidence_map.values()
            ]
            ev_stmt = pg_insert(EvidenceReferenceModel).values(ev_values)
            ev_stmt = ev_stmt.on_conflict_do_update(
                index_elements=["evidence_id"],
                set_={
                    "fsm_provenance": ev_stmt.excluded.fsm_provenance,
                    "attribution_method": ev_stmt.excluded.attribution_method,
                },
            )
            await self._session.execute(ev_stmt)

        await self._session.flush()
        logger.info(
            "Run '%s' persisted: %d verdict(s), %d evidence ref(s)",
            state.run_id,
            len(state.compliance_verdicts),
            len(state.evidence_map),
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str) -> dict | None:
        """Return the state_blob for a run, or None.

        Does NOT load verdicts/evidence separately — the full state is
        serialized in ``state_blob``.
        """
        row = await self._session.get(PipelineRunModel, run_id)
        if row is None:
            return None
        return row.state_blob if isinstance(row.state_blob, dict) else {}

    async def get_scalar(self, run_id: str) -> PipelineRunModel | None:
        """Return the ORM row (scalar fields only, no state_blob join)."""
        stmt = select(PipelineRunModel).where(PipelineRunModel.run_id == run_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_runs(self) -> list[dict]:
        """Return summaries of all runs (no state_blob)."""
        stmt = select(PipelineRunModel).order_by(PipelineRunModel.created_at.desc())
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "run_id": r.run_id,
                "circular_id": r.circular_id,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "updated_at": r.updated_at.isoformat() if r.updated_at else "",
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _state_to_db(state: CompliancePipelineState) -> dict:
        """Convert pipeline state → DB column dict."""
        return {
            "run_id": state.run_id,
            "circular_id": state.circular_id,
            "circular_path": state.circular_path,
            "status": state.status.value,
            "state_blob": state.model_dump(mode="json"),
            "hash_chain_root": state.hash_chain_root,
            "approved_by": state.approved_by,
            "approved_at": state.approved_at,
            "hitl_notes": state.hitl_notes,
            "updated_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def _verdict_to_db(v, run_id: str) -> dict:
        return {
            "verdict_id": v.verdict_id,
            "pipeline_run_id": run_id,
            "obligation_ref": v.obligation_ref,
            "broker_id": v.broker_id,
            "fsm_ref": v.fsm_ref,
            "status": v.status.value,
            "current_state": v.current_state,
            "evidence": v.evidence if isinstance(v.evidence, dict) else {},
            "evaluated_at": v.evaluated_at,
        }

    @staticmethod
    def _evidence_to_db(ev_dict: dict, run_id: str) -> dict:
        evaluated_at = datetime.now(timezone.utc)
        if ev_dict.get("evaluated_at"):
            try:
                evaluated_at = datetime.fromisoformat(ev_dict["evaluated_at"])
            except (ValueError, TypeError):
                pass
        return {
            "evidence_id": ev_dict["evidence_id"],
            "verdict_id": ev_dict["verdict_id"],
            "pipeline_run_id": run_id,
            "circular_ref": ev_dict.get("circular_ref", ""),
            "fsm_provenance": ev_dict.get("fsm_provenance", {}),
            "attribution_method": ev_dict.get("attribution_method", "conservative"),
            "evaluated_at": evaluated_at,
        }
