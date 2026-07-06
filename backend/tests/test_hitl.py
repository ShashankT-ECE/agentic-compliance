"""
Tests for M4 — HITL Gate (LockedFSM creation, review, hash chain, persistence, API).

Covers:
  - LockedFSM model validation (Pydantic)
  - create_locked_fsms() from extracted HybridFSMs
  - approve_fsm / reject_fsm / amend_fsm
  - Hash chain integration (integrity_hash, hash_link, verify_chain)
  - Persistence (persist_locked_fsms / load_locked_fsms roundtrip)
  - API endpoints (list, get, approve, reject, amend, review history)
  - Edge cases: invalid reviewer, duplicate approval, invalid amendment
  - Pipeline pause / resume (hitl_gate_node)
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.fsm import CANONICAL_STATES, FSMState, FSMTransition, HybridFSM, TimelineRule
from app.models.locked_fsm import AmendmentRecord, LockedFSM, LockStatus
from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.models.scoreboard import HashChain, HashLink
from app.pipeline.nodes.hitl_gate import (
    amend_fsm,
    approve_fsm,
    build_hitl_hash_chain,
    create_locked_fsms,
    hitl_gate_node,
    load_locked_fsms,
    persist_locked_fsms,
    reject_fsm,
    verify_locked_fsm_integrity,
)
from app.utils.hash_chain import compute_hash, link, verify_chain

# ═══════════════════════════════════════════════════════════════════════
# Shared fixtures
# ═══════════════════════════════════════════════════════════════════════

CIRCULAR_REF = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"
RUN_ID = "RUN-20260703-001"


def _make_test_fsm(obligation_ref: str = "CIRC-2025-057-CL-01") -> HybridFSM:
    """Build a minimal valid HybridFSM for testing."""
    return HybridFSM(
        obligation_ref=obligation_ref,
        circular_ref=CIRCULAR_REF,
        states=[
            FSMState(name="PENDING", description="Awaiting action"),
            FSMState(name="DUE", description="Deadline approaching"),
            FSMState(name="COMPLIANT", description="Action completed"),
            FSMState(name="LATE", description="Deadline missed"),
            FSMState(name="NON_COMPLIANT", description="Breach confirmed"),
        ],
        initial_state="PENDING",
        transitions=[
            FSMTransition(from_state="PENDING", to_state="COMPLIANT", trigger_event="margin_collected"),
            FSMTransition(from_state="PENDING", to_state="DUE", trigger_event="settlement_day_approaching"),
            FSMTransition(from_state="PENDING", to_state="LATE", trigger_event="deadline_elapsed"),
            FSMTransition(from_state="DUE", to_state="COMPLIANT", trigger_event="margin_collected"),
            FSMTransition(from_state="DUE", to_state="LATE", trigger_event="deadline_elapsed"),
            FSMTransition(from_state="LATE", to_state="NON_COMPLIANT", trigger_event="grace_expired"),
        ],
        timeline_rules=[
            TimelineRule(start_event="trade_executed", deadline_offset=1),
        ],
    )


def _make_extracted_fsms(count: int = 4) -> list[HybridFSM]:
    """Build multiple test FSMs matching the canonical circular obligations."""
    refs = [
        "CIRC-2025-057-CL-01",
        "CIRC-2025-057-CL-02",
        "CIRC-2025-057-CL-03",
        "CIRC-2025-057-CL-04",
    ]
    return [_make_test_fsm(ref) for ref in refs[:count]]


# ═══════════════════════════════════════════════════════════════════════
# LockedFSM model validation
# ═══════════════════════════════════════════════════════════════════════


class TestLockedFSMModel:
    """Pydantic validation of LockedFSM."""

    def test_create_pending_locked_fsm(self):
        fsm = _make_test_fsm()
        locked = LockedFSM(
            fsm_id=fsm.fsm_id,
            obligation_ref=fsm.obligation_ref,
            circular_ref=CIRCULAR_REF,
            original_fsm=fsm,
        )
        assert locked.status == LockStatus.PENDING_REVIEW
        assert locked.version == 1
        assert locked.locked_fsm_id.startswith("LOCKED-")
        assert locked.integrity_hash is None
        assert locked.hash_link is None
        assert locked.amendment_history == []
        assert locked.is_resolved is False
        assert locked.is_approved_or_amended is False

    def test_approved_requires_reviewer(self):
        fsm = _make_test_fsm()
        with pytest.raises(ValueError, match="reviewer is required"):
            LockedFSM(
                fsm_id=fsm.fsm_id,
                obligation_ref=fsm.obligation_ref,
                circular_ref=CIRCULAR_REF,
                original_fsm=fsm,
                status=LockStatus.APPROVED,
                integrity_hash="a" * 64,
                hash_link=HashLink(index=0, data_hash="b" * 64, previous_hash="0" * 64, link_hash="c" * 64),
            )

    def test_rejected_requires_review_comments(self):
        fsm = _make_test_fsm()
        with pytest.raises(ValueError, match="review_comments is required"):
            LockedFSM(
                fsm_id=fsm.fsm_id,
                obligation_ref=fsm.obligation_ref,
                circular_ref=CIRCULAR_REF,
                original_fsm=fsm,
                status=LockStatus.REJECTED,
                reviewer="shashank",
                reviewed_at=datetime.now(),
            )

    def test_approved_requires_integrity_hash(self):
        fsm = _make_test_fsm()
        with pytest.raises(ValueError, match="integrity_hash is required"):
            LockedFSM(
                fsm_id=fsm.fsm_id,
                obligation_ref=fsm.obligation_ref,
                circular_ref=CIRCULAR_REF,
                original_fsm=fsm,
                status=LockStatus.APPROVED,
                reviewer="shashank",
                reviewed_at=datetime.now(),
                hash_link=HashLink(index=0, data_hash="b" * 64, previous_hash="0" * 64, link_hash="c" * 64),
            )

    def test_approved_requires_hash_link(self):
        fsm = _make_test_fsm()
        with pytest.raises(ValueError, match="hash_link is required"):
            LockedFSM(
                fsm_id=fsm.fsm_id,
                obligation_ref=fsm.obligation_ref,
                circular_ref=CIRCULAR_REF,
                original_fsm=fsm,
                status=LockStatus.APPROVED,
                reviewer="shashank",
                reviewed_at=datetime.now(),
                integrity_hash="a" * 64,
            )

    def test_fsm_id_must_match_original(self):
        fsm = _make_test_fsm()
        with pytest.raises(ValueError, match="does not match"):
            LockedFSM(
                fsm_id="WRONG-ID",
                obligation_ref=fsm.obligation_ref,
                circular_ref=CIRCULAR_REF,
                original_fsm=fsm,
            )


# ═══════════════════════════════════════════════════════════════════════
# LockedFSM creation
# ═══════════════════════════════════════════════════════════════════════


class TestCreateLockedFsms:
    """Tests for create_locked_fsms()."""

    def test_creates_one_per_fsm(self):
        fsms = _make_extracted_fsms(4)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)
        assert len(locked) == 4
        for lfsm in locked:
            assert lfsm.status == LockStatus.PENDING_REVIEW
            assert lfsm.circular_ref == CIRCULAR_REF
            assert lfsm.version == 1

    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="extracted_fsms is empty"):
            create_locked_fsms([], CIRCULAR_REF)

    def test_preserves_obligation_refs(self):
        fsms = _make_extracted_fsms(3)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)
        refs = {l.obligation_ref for l in locked}
        assert refs == {"CIRC-2025-057-CL-01", "CIRC-2025-057-CL-02", "CIRC-2025-057-CL-03"}


# ═══════════════════════════════════════════════════════════════════════
# Review actions — approve, reject, amend
# ═══════════════════════════════════════════════════════════════════════


class TestApproveFsm:
    """Tests for approve_fsm()."""

    def test_approve_sets_status_and_hash(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        result = approve_fsm(locked, "shashank", "Looks correct.")

        assert result.status == LockStatus.APPROVED
        assert result.reviewer == "shashank"
        assert result.reviewed_at is not None
        assert result.integrity_hash is not None
        assert len(result.integrity_hash) == 64
        assert result.hash_link is not None
        assert result.hash_link.index == 0  # genesis
        assert result.hash_link.previous_hash == "0" * 64

    def test_approve_chains_links_sequentially(self):
        fsms = _make_extracted_fsms(2)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)

        r1 = approve_fsm(locked[0], "shashank")
        r2 = approve_fsm(locked[1], "shashank", previous_hash_link=r1.hash_link)

        assert r1.hash_link.index == 0
        assert r2.hash_link.index == 1
        assert r2.hash_link.previous_hash == r1.hash_link.link_hash

    def test_approve_non_pending_raises(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]
        approved = approve_fsm(locked, "shashank")

        with pytest.raises(ValueError, match="status is 'approved'"):
            approve_fsm(approved, "shashank")  # double-approve

    def test_integrity_hash_is_deterministic(self):
        """Same FSM content approved twice should produce the same integrity_hash."""
        fsms = _make_extracted_fsms(1)
        locked1 = create_locked_fsms(fsms, CIRCULAR_REF)[0]
        locked2 = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        r1 = approve_fsm(locked1, "shashank")
        r2 = approve_fsm(locked2, "shashank")

        assert r1.integrity_hash == r2.integrity_hash


class TestRejectFsm:
    """Tests for reject_fsm()."""

    def test_reject_sets_status(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        result = reject_fsm(locked, "shashank", "start_event is wrong — should be trade_executed")

        assert result.status == LockStatus.REJECTED
        assert result.reviewer == "shashank"
        assert result.review_comments == "start_event is wrong — should be trade_executed"
        assert result.integrity_hash is None  # no hash for rejected FSMs

    def test_reject_requires_comments(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        with pytest.raises(ValueError, match="review_comments is required"):
            reject_fsm(locked, "shashank", "")

    def test_reject_non_pending_raises(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]
        approved = approve_fsm(locked, "shashank")

        with pytest.raises(ValueError, match="status is 'approved'"):
            reject_fsm(approved, "shashank", "Changed my mind")


class TestAmendFsm:
    """Tests for amend_fsm()."""

    def test_amend_increments_version(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        corrected = _make_test_fsm("CIRC-2025-057-CL-01")
        result = amend_fsm(locked, corrected, "shashank", "Fixed start_event to trade_executed")

        assert result.status == LockStatus.AMENDED
        assert result.version == 2
        assert len(result.amendment_history) == 1
        assert result.amendment_history[0].version == 1
        assert result.amendment_history[0].prior_fsm == locked.original_fsm

    def test_amend_sets_new_hash(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        corrected = _make_test_fsm("CIRC-2025-057-CL-01")
        result = amend_fsm(locked, corrected, "shashank", "Fixed")

        assert result.integrity_hash is not None
        assert len(result.integrity_hash) == 64
        assert result.hash_link is not None

    def test_amend_requires_comments(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        with pytest.raises(ValueError, match="review_comments is required"):
            amend_fsm(locked, _make_test_fsm(), "shashank", "")

    def test_amend_non_pending_raises(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]
        approved = approve_fsm(locked, "shashank")

        with pytest.raises(ValueError, match="status is 'approved'"):
            amend_fsm(approved, _make_test_fsm(), "shashank", "Try to amend approved")

    def test_multiple_amendments_preserve_full_history(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]

        # First amendment
        v2 = amend_fsm(locked, _make_test_fsm(), "shashank", "Fix 1")
        # Second amendment — amending v2 as if it were still pending
        # (simulate: create new PENDING, then amend)
        locked_v2 = LockedFSM(
            fsm_id=v2.original_fsm.fsm_id,
            obligation_ref=v2.obligation_ref,
            circular_ref=CIRCULAR_REF,
            version=v2.version,
            original_fsm=v2.original_fsm,
            amendment_history=v2.amendment_history,
        )
        v3 = amend_fsm(locked_v2, _make_test_fsm(), "friend", "Fix 2")

        assert v3.version == 3
        assert len(v3.amendment_history) == 2


# ═══════════════════════════════════════════════════════════════════════
# Integrity verification
# ═══════════════════════════════════════════════════════════════════════


class TestIntegrityVerification:
    """Tests for verify_locked_fsm_integrity and hash chain integration."""

    def test_verify_valid_integrity(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]
        approved = approve_fsm(locked, "shashank")
        assert verify_locked_fsm_integrity(approved) is True

    def test_verify_tampered_fsm_detected(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]
        approved = approve_fsm(locked, "shashank")

        # Tamper with the FSM content
        tampered_fsm = approved.original_fsm.model_copy(deep=True)
        tampered_fsm.states[0].description = "TAMPERED"
        tampered = approved.model_copy(deep=True)
        tampered.original_fsm = tampered_fsm

        assert verify_locked_fsm_integrity(tampered) is False

    def test_verify_no_integrity_hash_returns_false(self):
        fsms = _make_extracted_fsms(1)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)[0]
        assert verify_locked_fsm_integrity(locked) is False

    def test_hash_chain_verifies_after_approvals(self):
        fsms = _make_extracted_fsms(3)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)

        prev: HashLink | None = None
        approved: list[LockedFSM] = []
        for lfsm in locked:
            result = approve_fsm(lfsm, "shashank", previous_hash_link=prev)
            approved.append(result)
            prev = result.hash_link

        chain = build_hitl_hash_chain(approved)
        assert chain.length == 3
        assert verify_chain(chain) is True


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════


class TestPersistence:
    """Tests for persist_locked_fsms and load_locked_fsms."""

    def test_persist_and_reload_roundtrip(self):
        fsms = _make_extracted_fsms(4)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)

        # Approve 3, reject 1
        locked[0] = approve_fsm(locked[0], "shashank")
        locked[1] = approve_fsm(locked[1], "shashank", previous_hash_link=locked[0].hash_link)
        locked[2] = reject_fsm(locked[2], "shashank", "Needs correction")
        locked[3] = approve_fsm(locked[3], "shashank", previous_hash_link=locked[1].hash_link)

        with tempfile.TemporaryDirectory() as tmpdir:
            persist_locked_fsms(locked, RUN_ID, output_dir=tmpdir)

            # Verify files exist
            run_dir = Path(tmpdir) / RUN_ID
            assert run_dir.exists()
            assert (run_dir / "_pipeline_state.json").exists()
            assert (run_dir / "_review_log.json").exists()
            assert (run_dir / "_hash_chain.json").exists()

            for lfsm in locked:
                assert (run_dir / f"{lfsm.locked_fsm_id}.json").exists()

            # Reload and verify
            reloaded = load_locked_fsms(RUN_ID, data_dir=tmpdir)
            assert len(reloaded) == 4

            # Verify statuses preserved
            statuses = {f.locked_fsm_id: f.status for f in reloaded}
            for lfsm in locked:
                assert statuses[lfsm.locked_fsm_id] == lfsm.status

    def test_reloaded_fsms_pass_integrity_check(self):
        fsms = _make_extracted_fsms(2)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)
        locked[0] = approve_fsm(locked[0], "shashank")
        locked[1] = approve_fsm(locked[1], "shashank", previous_hash_link=locked[0].hash_link)

        with tempfile.TemporaryDirectory() as tmpdir:
            persist_locked_fsms(locked, RUN_ID, output_dir=tmpdir)
            reloaded = load_locked_fsms(RUN_ID, data_dir=tmpdir)

            for r in reloaded:
                if r.is_approved_or_amended:
                    assert verify_locked_fsm_integrity(r) is True

    def test_load_nonexistent_run_raises(self):
        with pytest.raises(FileNotFoundError):
            load_locked_fsms("NONEXISTENT-RUN")

    def test_persist_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = persist_locked_fsms([], RUN_ID, output_dir=tmpdir)
            assert run_dir.exists()
            assert (run_dir / "_pipeline_state.json").exists()
            # Reload empty
            reloaded = load_locked_fsms(RUN_ID, data_dir=tmpdir)
            assert len(reloaded) == 0

    def test_review_log_contains_all_actions(self):
        fsms = _make_extracted_fsms(2)
        locked = create_locked_fsms(fsms, CIRCULAR_REF)
        locked[0] = approve_fsm(locked[0], "shashank", "OK")
        locked[1] = reject_fsm(locked[1], "shashank", "Bad transition")

        with tempfile.TemporaryDirectory() as tmpdir:
            persist_locked_fsms(locked, RUN_ID, output_dir=tmpdir)
            log_path = Path(tmpdir) / RUN_ID / "_review_log.json"
            log_data = json.loads(log_path.read_text())
            assert len(log_data) == 2
            actions = {e["action"] for e in log_data}
            assert actions == {"approved", "rejected"}


# ═══════════════════════════════════════════════════════════════════════
# Pipeline node
# ═══════════════════════════════════════════════════════════════════════


class TestHitlGateNode:
    """Tests for hitl_gate_node()."""

    def test_node_creates_locked_fsms_and_pauses(self):
        fsms = _make_extracted_fsms(4)
        state = {
            "run_id": RUN_ID,
            "circular_id": CIRCULAR_REF,
            "extracted_fsms": fsms,
            "status": "fsm_extracted",
        }

        import app.pipeline.nodes.hitl_gate as hmod
        _saved_dir = hmod._LOCKED_DATA_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                hmod._LOCKED_DATA_DIR = Path(tmpdir)
                result = hitl_gate_node(state)

                assert result["status"].value == "awaiting_approval"
                assert result["locked_fsms"] == []  # not populated until approved

                # Verify files were persisted
                run_dir = Path(tmpdir) / RUN_ID
                assert run_dir.exists()
                assert len(list(run_dir.glob("LOCKED-*.json"))) == 4
            finally:
                hmod._LOCKED_DATA_DIR = _saved_dir

    def test_node_empty_fsms_raises(self):
        state = {
            "run_id": RUN_ID,
            "circular_id": CIRCULAR_REF,
            "extracted_fsms": [],
        }
        with pytest.raises(ValueError, match="no 'extracted_fsms'"):
            hitl_gate_node(state)


# ═══════════════════════════════════════════════════════════════════════
# API endpoint tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def api_client() -> TestClient:
    """Create a FastAPI TestClient with the pipeline router mounted."""
    from fastapi import FastAPI

    from app.api.routes.pipeline import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def seeded_run(api_client: TestClient, tmp_path: Path) -> tuple[str, Path]:
    """Create a run directory with 4 PENDING LockedFSMs in tmp_path. Returns (run_id, data_dir)."""
    fsms = _make_extracted_fsms(4)
    locked = create_locked_fsms(fsms, CIRCULAR_REF)
    persist_locked_fsms(locked, RUN_ID, output_dir=tmp_path)
    return RUN_ID, tmp_path


class TestApiListFsms:
    """Tests for GET /api/pipeline/{run_id}/fsms."""

    def test_list_fsms(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp = api_client.get(f"/api/pipeline/{run_id}/fsms")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_fsms"] == 4
        assert data["pending"] == 4
        assert len(data["fsms"]) == 4

    def test_list_nonexistent_run(self, api_client):
        resp = api_client.get("/api/pipeline/NONEXISTENT/fsms")
        assert resp.status_code == 404


class TestApiGetFsm:
    """Tests for GET /api/pipeline/{run_id}/fsms/{locked_fsm_id}."""

    def test_get_single_fsm(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        resp = api_client.get(f"/api/pipeline/{run_id}/fsms/{fsm_id}")
        assert resp.status_code == 200
        assert resp.json()["locked_fsm_id"] == fsm_id

    def test_get_nonexistent_fsm(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp = api_client.get(f"/api/pipeline/{run_id}/fsms/LOCKED-NONEXISTENT")
        assert resp.status_code == 404


class TestApiApprove:
    """Tests for POST /api/pipeline/{run_id}/fsms/{locked_fsm_id}/approve."""

    def test_approve_fsm(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        resp = api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/approve",
            json={"reviewer": "shashank", "review_comments": "Looks correct"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["integrity_hash"] is not None
        assert data["hash_link"] is not None

    def test_approve_missing_reviewer(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        resp = api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/approve",
            json={"reviewer": ""},
        )
        assert resp.status_code == 422

    def test_double_approve_returns_409(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/approve",
            json={"reviewer": "shashank"},
        )
        resp = api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/approve",
            json={"reviewer": "shashank"},
        )
        assert resp.status_code == 409
        assert "already resolved" in resp.json()["detail"]


class TestApiReject:
    """Tests for POST /api/pipeline/{run_id}/fsms/{locked_fsm_id}/reject."""

    def test_reject_fsm(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        resp = api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/reject",
            json={"reviewer": "shashank", "review_comments": "Wrong start_event"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_reject_without_comments(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        resp = api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/reject",
            json={"reviewer": "shashank", "review_comments": ""},
        )
        assert resp.status_code == 400


class TestApiAmend:
    """Tests for POST /api/pipeline/{run_id}/fsms/{locked_fsm_id}/amend."""

    def test_amend_fsm(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        corrected = _make_test_fsm("CIRC-2025-057-CL-01")
        resp = api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/amend",
            json={
                "reviewer": "shashank",
                "review_comments": "Fixed start_event to trade_executed",
                "corrected_fsm": json.loads(corrected.model_dump_json()),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "amended"
        assert data["version"] == 2
        assert len(data["amendment_history"]) == 1

    def test_amend_invalid_fsm(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsm_id = resp_list.json()["fsms"][0]["locked_fsm_id"]

        resp = api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsm_id}/amend",
            json={
                "reviewer": "shashank",
                "review_comments": "Bad FSM",
                "corrected_fsm": {"not": "a valid fsm"},
            },
        )
        assert resp.status_code == 400
        assert "Invalid corrected FSM" in resp.json()["detail"]


class TestApiReviewHistory:
    """Tests for GET /api/pipeline/{run_id}/review-history."""

    def test_review_history(self, api_client, seeded_run, monkeypatch):
        run_id, tmpdir = seeded_run
        monkeypatch.setattr("app.api.routes.pipeline._LOCKED_DATA_DIR", tmpdir)
        resp_list = api_client.get(f"/api/pipeline/{run_id}/fsms")
        fsms = resp_list.json()["fsms"]

        api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsms[0]['locked_fsm_id']}/approve",
            json={"reviewer": "shashank"},
        )
        api_client.post(
            f"/api/pipeline/{run_id}/fsms/{fsms[1]['locked_fsm_id']}/reject",
            json={"reviewer": "shashank", "review_comments": "Needs fix"},
        )

        resp = api_client.get(f"/api/pipeline/{run_id}/review-history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 2
        actions = {e["action"] for e in data["entries"]}
        assert actions == {"approved", "rejected"}

    def test_history_nonexistent_run(self, api_client):
        resp = api_client.get("/api/pipeline/NONEXISTENT/review-history")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# LockStatus enum
# ═══════════════════════════════════════════════════════════════════════


def test_lock_status_values():
    assert LockStatus.PENDING_REVIEW.value == "pending_review"
    assert LockStatus.APPROVED.value == "approved"
    assert LockStatus.REJECTED.value == "rejected"
    assert LockStatus.AMENDED.value == "amended"
