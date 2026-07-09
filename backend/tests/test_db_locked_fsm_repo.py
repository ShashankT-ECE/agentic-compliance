"""
Tests for LockedFsmRepo and HitlReviewRepo — V2 M4 Phase 4.

Uses in-memory async SQLite.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.db.repos.locked_fsm_repo import LockedFsmRepo
from app.db.repos.hitl_review_repo import HitlReviewRepo
from app.models.fsm import FSMState, FSMTransition, HybridFSM, TimelineRule
from app.models.locked_fsm import LockStatus, LockedFSM
from app.models.scoreboard import HashLink

pytestmark = pytest.mark.asyncio


# =============================================================================
# Helpers
# =============================================================================


def _make_fsm(fsm_id: str = "FSM-001", obligation_ref: str = "OBL-001") -> HybridFSM:
    return HybridFSM(
        fsm_id=fsm_id, obligation_ref=obligation_ref, circular_ref="SEBI/TEST/001",
        initial_state="PENDING",
        states=[
            FSMState(name="PENDING"), FSMState(name="DUE"),
            FSMState(name="COMPLIANT"), FSMState(name="LATE"), FSMState(name="NON_COMPLIANT"),
        ],
        transitions=[
            FSMTransition(from_state="PENDING", to_state="DUE", trigger_event="trade_executed"),
            FSMTransition(from_state="DUE", to_state="COMPLIANT", trigger_event="margin_collected"),
        ],
        timeline_rules=[
            TimelineRule(start_event="trade_executed", deadline_offset=1, time_unit="days", overdue_transition="LATE"),
        ],
    )


def _make_locked_fsm(
    locked_fsm_id: str = "LOCKED-001", fsm_id: str = "FSM-001",
    obligation_ref: str = "OBL-001", status: LockStatus = LockStatus.PENDING_REVIEW,
) -> LockedFSM:
    link = HashLink(index=0, data_hash="a" * 64, previous_hash="0" * 64, link_hash="b" * 64)
    from datetime import datetime, timezone
    kwargs: dict = dict(
        locked_fsm_id=locked_fsm_id, fsm_id=fsm_id, obligation_ref=obligation_ref,
        circular_ref="SEBI/TEST/001", version=1, original_fsm=_make_fsm(fsm_id, obligation_ref),
        status=status, hash_link=link,
    )
    if status in (LockStatus.APPROVED, LockStatus.AMENDED):
        kwargs["reviewer"] = "test_reviewer"
        kwargs["reviewed_at"] = datetime.now(timezone.utc)
        kwargs["integrity_hash"] = "i" * 64
    if status == LockStatus.REJECTED:
        kwargs["reviewer"] = "test_reviewer"
        kwargs["reviewed_at"] = datetime.now(timezone.utc)
        kwargs["review_comments"] = "Rejection reason."
    return LockedFSM(**kwargs)


class _TestDB:
    def __init__(self):
        self._engine = None
        self._factory = None
        self._session = None
        self.locked_fsm = None
        self.hitl = None

    async def __aenter__(self):
        self._engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._factory = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)
        self._session = self._factory()
        self.locked_fsm = LockedFsmRepo(self._session)
        self.hitl = HitlReviewRepo(self._session)
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
        self.locked_fsm = LockedFsmRepo(self._session)
        self.hitl = HitlReviewRepo(self._session)


# =============================================================================
# LockedFsmRepo tests
# =============================================================================


class TestLockedFsmSaveBatch:
    async def test_save_and_retrieve(self):
        async with _TestDB() as db:
            lf = _make_locked_fsm("LOCKED-S1")
            await db.locked_fsm.save_batch([lf], "run-001")
            await db.commit()
            await db.reopen()
            rows = await db.locked_fsm.get_by_run("run-001")
            assert len(rows) == 1
            assert rows[0].locked_fsm_id == "LOCKED-S1"

    async def test_save_multiple(self):
        async with _TestDB() as db:
            fsms = [
                _make_locked_fsm("LOCKED-M1", "FSM-01", "OBL-01"),
                _make_locked_fsm("LOCKED-M2", "FSM-02", "OBL-02"),
                _make_locked_fsm("LOCKED-M3", "FSM-03", "OBL-03"),
            ]
            await db.locked_fsm.save_batch(fsms, "run-multi")
            await db.commit()
            await db.reopen()
            assert len(await db.locked_fsm.get_by_run("run-multi")) == 3

    async def test_batch_upserts_status_change(self):
        """Re-saving with updated status works."""
        from datetime import datetime, timezone
        async with _TestDB() as db:
            lf = _make_locked_fsm("LOCKED-U1", status=LockStatus.PENDING_REVIEW)
            await db.locked_fsm.save_batch([lf], "run-upsert")
            await db.commit()
            await db.reopen()

            lf = lf.model_copy(update={
                "status": LockStatus.APPROVED,
                "reviewer": "approver_1",
                "reviewed_at": datetime.now(timezone.utc),
                "integrity_hash": "i" * 64,
            })
            await db.locked_fsm.save_batch([lf], "run-upsert")
            await db.commit()
            await db.reopen()

            rows = await db.locked_fsm.get_by_run("run-upsert")
            assert rows[0].status == LockStatus.APPROVED
            assert rows[0].reviewer == "approver_1"


class TestLockedFsmGetByRun:
    async def test_empty(self):
        async with _TestDB() as db:
            assert await db.locked_fsm.get_by_run("nonexistent") == []

    async def test_only_returns_target_run(self):
        async with _TestDB() as db:
            await db.locked_fsm.save_batch([_make_locked_fsm("L-A")], "run-A")
            await db.locked_fsm.save_batch([_make_locked_fsm("L-B")], "run-B")
            await db.commit()
            await db.reopen()
            assert len(await db.locked_fsm.get_by_run("run-A")) == 1
            assert len(await db.locked_fsm.get_by_run("run-B")) == 1


class TestLockedFsmCountPending:
    async def test_all_pending(self):
        async with _TestDB() as db:
            await db.locked_fsm.save_batch([
                _make_locked_fsm("L-P1", status=LockStatus.PENDING_REVIEW),
                _make_locked_fsm("L-P2", status=LockStatus.PENDING_REVIEW),
            ], "run-pend")
            await db.commit()
            assert await db.locked_fsm.count_pending("run-pend") == 2
            assert await db.locked_fsm.has_pending("run-pend") is True

    async def test_none_pending(self):
        async with _TestDB() as db:
            await db.locked_fsm.save_batch([
                _make_locked_fsm("L-A1", status=LockStatus.APPROVED),
            ], "run-nopend")
            await db.commit()
            assert await db.locked_fsm.count_pending("run-nopend") == 0
            assert await db.locked_fsm.has_pending("run-nopend") is False


class TestLockedFsmFKConstraint:
    async def test_missing_pipeline_run(self):
        """LockedFSM references a run that doesn't exist. FK may fail in PG, SQLite ignores by default."""
        async with _TestDB() as db:
            lf = _make_locked_fsm("LOCKED-FK")
            # Save against a nonexistent run_id — FK constraint in PG would reject this
            await db.locked_fsm.save_batch([lf], "run-nonexistent")
            await db.commit()
            await db.reopen()
            # In SQLite with foreign keys off, this silently succeeds
            rows = await db.locked_fsm.get_by_run("run-nonexistent")
            assert len(rows) == 1


# =============================================================================
# HitlReviewRepo tests
# =============================================================================


class TestHitlReviewAppend:
    async def test_append_and_retrieve(self):
        async with _TestDB() as db:
            await db.hitl.append(
                pipeline_run_id="run-001", locked_fsm_id="LOCKED-1",
                fsm_id="FSM-1", obligation_ref="OBL-1",
                action="approved", reviewer="auditor_1", comments="Looks correct.",
            )
            await db.commit()
            await db.reopen()
            entries = await db.hitl.get_by_run("run-001")
            assert len(entries) == 1
            e = entries[0]
            assert e["action"] == "approved"
            assert e["reviewer"] == "auditor_1"
            assert e["comments"] == "Looks correct."

    async def test_append_multiple(self):
        async with _TestDB() as db:
            await db.hitl.append(
                pipeline_run_id="run-multi", locked_fsm_id="LOCKED-1",
                fsm_id="FSM-1", obligation_ref="OBL-1",
                action="approved", reviewer="a1",
            )
            await db.hitl.append(
                pipeline_run_id="run-multi", locked_fsm_id="LOCKED-2",
                fsm_id="FSM-2", obligation_ref="OBL-2",
                action="rejected", reviewer="a1", comments="Not enough evidence.",
            )
            await db.hitl.append(
                pipeline_run_id="run-multi", locked_fsm_id="LOCKED-1",
                fsm_id="FSM-1", obligation_ref="OBL-1",
                action="amended", reviewer="a2", comments="Corrected timeline.",
            )
            await db.commit()
            await db.reopen()
            entries = await db.hitl.get_by_run("run-multi")
            assert len(entries) == 3
            actions = [e["action"] for e in entries]
            assert actions == ["approved", "rejected", "amended"]

    async def test_empty_run(self):
        async with _TestDB() as db:
            assert await db.hitl.get_by_run("nonexistent") == []

    async def test_chronological_order(self):
        """Entries are returned in insertion order."""
        async with _TestDB() as db:
            for i in range(5):
                await db.hitl.append(
                    pipeline_run_id="run-seq", locked_fsm_id=f"LOCKED-{i}",
                    fsm_id=f"FSM-{i}", obligation_ref=f"OBL-{i}",
                    action="approved", reviewer=f"r{i}",
                )
            await db.commit()
            await db.reopen()
            entries = await db.hitl.get_by_run("run-seq")
            # Must be in insertion order
            assert [e["locked_fsm_id"] for e in entries] == [f"LOCKED-{i}" for i in range(5)]


# =============================================================================
# Backward compatibility
# =============================================================================


class TestBackwardCompatibility:
    async def test_locked_fsm_round_trip(self):
        """LockedFSM → DB → Pydantic preserves all fields."""
        lf = _make_locked_fsm("LOCKED-RT", "FSM-RT", "OBL-RT", status=LockStatus.APPROVED)
        lf = lf.model_copy(update={"review_comments": "All good."})
        async with _TestDB() as db:
            await db.locked_fsm.save_batch([lf], "run-rt")
            await db.commit()
            await db.reopen()
            rows = await db.locked_fsm.get_by_run("run-rt")
            rt = rows[0]
            assert rt.locked_fsm_id == "LOCKED-RT"
            assert rt.fsm_id == "FSM-RT"
            assert rt.status == LockStatus.APPROVED
            assert rt.reviewer == "test_reviewer"
            assert rt.review_comments == "All good."
            assert rt.original_fsm.states[0].name == "PENDING"
