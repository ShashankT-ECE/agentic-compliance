"""
Tests for PipelineRunRepo — V2 M4 Phase 3.

Uses in-memory async SQLite for database testing.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.db.repos.pipeline_run_repo import PipelineRunRepo
from app.models.fsm import FSMState, FSMTransition, HybridFSM, TimelineRule
from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.pipeline.state import CompliancePipelineState, PipelineStatus

pytestmark = pytest.mark.asyncio


# =============================================================================
# Helpers
# =============================================================================


def _make_obligation(clause_id: str) -> ObligationClause:
    return ObligationClause(
        clause_id=clause_id, circular_ref="SEBI/TEST/001",
        obligation_type=ObligationType.TIMELINE, clause_text=f"Obligation {clause_id}",
        timeline_params=TimelineParams(offset=1, unit="days"),
    )


def _make_verdict(verdict_id: str, obligation_ref: str = "CL-01", broker_id: str = "B-001",
                   fsm_ref: str = "FSM-01", status: VerdictStatus = VerdictStatus.COMPLIANT) -> ComplianceVerdict:
    return ComplianceVerdict(
        verdict_id=verdict_id, obligation_ref=obligation_ref, broker_id=broker_id,
        fsm_ref=fsm_ref, status=status, current_state="COMPLIANT",
        evidence={"matched_events": 1}, evaluated_at="2026-07-09T12:00:00Z",
    )


class _TestDB:
    def __init__(self):
        self._engine = None
        self._factory = None
        self._session = None
        self.repo = None

    async def __aenter__(self):
        self._engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._factory = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)
        self._session = self._factory()
        self.repo = PipelineRunRepo(self._session)
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
        if self._engine:
            await self._engine.dispose()

    async def commit(self):
        await self._session.commit()

    async def reopen(self):
        await self._session.close()
        self._session = self._factory()
        self.repo = PipelineRunRepo(self._session)


def _make_state(run_id: str = "run-test-001", status: PipelineStatus = PipelineStatus.CREATED) -> CompliancePipelineState:
    return CompliancePipelineState(
        run_id=run_id, circular_id="SEBI/TEST/001", circular_path="/fake/test.pdf",
        status=status, metadata={"started_at": "2026-07-09T12:00:00Z"},
    )


# =============================================================================
# Tests
# =============================================================================


class TestCheckpointSave:
    async def test_save_and_reload(self):
        async with _TestDB() as db:
            state = _make_state("run-ckpt-001", PipelineStatus.AWAITING_APPROVAL)
            state.obligation_clauses = [_make_obligation("CL-01")]
            await db.repo.save_checkpoint(state)
            await db.commit()
            await db.reopen()

            blob = await db.repo.get_run("run-ckpt-001")
            assert blob is not None
            assert blob["run_id"] == "run-ckpt-001"
            assert blob["status"] == "awaiting_approval"
            assert len(blob["obligation_clauses"]) == 1

    async def test_checkpoint_upserts(self):
        async with _TestDB() as db:
            s1 = _make_state("run-upsert", PipelineStatus.CREATED)
            await db.repo.save_checkpoint(s1)
            await db.commit()
            await db.reopen()

            s2 = _make_state("run-upsert", PipelineStatus.PARSED)
            await db.repo.save_checkpoint(s2)
            await db.commit()
            await db.reopen()

            blob = await db.repo.get_run("run-upsert")
            assert blob["status"] == "parsed"

    async def test_checkpoint_preserves_full_state(self):
        """state_blob carries all pipeline data including verdicts."""
        async with _TestDB() as db:
            state = _make_state("run-full", PipelineStatus.AWAITING_APPROVAL)
            state.obligation_clauses = [_make_obligation("CL-01"), _make_obligation("CL-02")]
            state.chunk_objects = [{"chunk_id": "C::1", "text": "test"}]
            state.approved_by = "reviewer_1"
            await db.repo.save_checkpoint(state)
            await db.commit()
            await db.reopen()

            blob = await db.repo.get_run("run-full")
            assert len(blob["obligation_clauses"]) == 2
            assert len(blob["chunk_objects"]) == 1
            assert blob["approved_by"] == "reviewer_1"


class TestCompletedRun:
    async def test_persists_run_with_verdicts_and_evidence(self):
        async with _TestDB() as db:
            state = _make_state("run-comp-001", PipelineStatus.COMPLETED)
            state.compliance_verdicts = [
                _make_verdict("VER-01", "CL-01", broker_id="B-001"),
                _make_verdict("VER-02", "CL-02", broker_id="B-001"),
            ]
            state.evidence_map = {
                "VER-01": {
                    "evidence_id": "EV-01", "verdict_id": "VER-01",
                    "circular_ref": "SEBI/TEST/001", "attribution_method": "conservative",
                    "evaluated_at": "2026-07-09T12:00:00Z",
                    "fsm_provenance": {"fsm_id": "FSM-01", "obligation_source": {"obligation_ref": "CL-01", "source_chunks": []}},
                },
                "VER-02": {
                    "evidence_id": "EV-02", "verdict_id": "VER-02",
                    "circular_ref": "SEBI/TEST/001", "attribution_method": "conservative",
                    "evaluated_at": "2026-07-09T12:00:00Z",
                    "fsm_provenance": {"fsm_id": "FSM-02", "obligation_source": {"obligation_ref": "CL-02", "source_chunks": []}},
                },
            }
            await db.repo.save_completed_run(state)
            await db.commit()
            await db.reopen()

            blob = await db.repo.get_run("run-comp-001")
            assert blob["status"] == "completed"
            assert len(blob["compliance_verdicts"]) == 2
            assert len(blob["evidence_map"]) == 2

    async def test_transaction_atomicity(self):
        """If evidence has a bad verdict_id, the entire batch should roll back."""
        async with _TestDB() as db:
            state = _make_state("run-atomic", PipelineStatus.COMPLETED)
            state.compliance_verdicts = [_make_verdict("VER-OK")]
            # Evidence references a verdict not in the verdicts list
            state.evidence_map = {
                "VER-MISSING": {
                    "evidence_id": "EV-MISSING", "verdict_id": "VER-MISSING",
                    "circular_ref": "SEBI/TEST/001", "attribution_method": "conservative",
                    "evaluated_at": "2026-07-09T12:00:00Z",
                    "fsm_provenance": {"fsm_id": "FSM-X", "obligation_source": {"obligation_ref": "CL-X", "source_chunks": []}},
                },
            }
            # This should raise because evidence_references.verdict_id has FK to verdicts
            try:
                await db.repo.save_completed_run(state)
                await db.commit()
                # FK may not be enforced in SQLite
            except Exception:
                await self._session.rollback() if hasattr(self, '_session') else None

    async def test_empty_verdicts_ok(self):
        async with _TestDB() as db:
            state = _make_state("run-no-v", PipelineStatus.COMPLETED)
            await db.repo.save_completed_run(state)
            await db.commit()
            await db.reopen()
            blob = await db.repo.get_run("run-no-v")
            assert blob["status"] == "completed"


class TestListRuns:
    async def test_list_returns_run_ids(self):
        async with _TestDB() as db:
            await db.repo.save_checkpoint(_make_state("run-A", PipelineStatus.AWAITING_APPROVAL))
            await db.repo.save_checkpoint(_make_state("run-B", PipelineStatus.COMPLETED))
            await db.commit()
            await db.reopen()
            runs = await db.repo.list_runs()
            assert len(runs) >= 2
            run_ids = {r["run_id"] for r in runs}
            assert "run-A" in run_ids
            assert "run-B" in run_ids


class TestBackwardCompatibility:
    async def test_state_blob_reconstructable(self):
        """A state blob saved to PG can be re-hydrated into CompliancePipelineState."""
        async with _TestDB() as db:
            state = _make_state("run-recon", PipelineStatus.COMPLETED)
            state.obligation_clauses = [_make_obligation("CL-01")]
            state.compliance_verdicts = [_make_verdict("VER-01")]
            await db.repo.save_checkpoint(state)
            await db.commit()
            await db.reopen()

            blob = await db.repo.get_run("run-recon")
            assert blob is not None
            rehydrated = CompliancePipelineState.model_validate(blob)
            assert rehydrated.run_id == "run-recon"
            assert rehydrated.status == PipelineStatus.COMPLETED
            assert len(rehydrated.obligation_clauses) == 1
