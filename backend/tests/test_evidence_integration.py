"""
Integration tests for evidence pipeline — V2 M3 / M4.

Verifies that EvidenceService is automatically invoked during pipeline
execution, evidence_map is populated with EvidenceReference objects,
and the evidence API returns real data after pipeline completion.
"""

from __future__ import annotations

import asyncio

import pytest

from app.models.evidence import EvidenceReference
from app.models.fsm import FSMState, FSMTransition, HybridFSM, TimelineRule
from app.models.locked_fsm import LockStatus, LockedFSM
from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.models.telemetry import TelemetryEvent
from app.models.verdict import ComplianceVerdict, VerdictStatus
from app.pipeline.runner import PipelineRunner, _get_store, _set_store
from app.pipeline.state import CompliancePipelineState, PipelineStatus
from app.rag.schemas import Chunk, ChunkMetadata


# =============================================================================
# Helpers
# =============================================================================


def _make_chunk(chunk_id: str, text: str, start_page: int = 1, end_page: int = 1, topic: int = 1) -> dict:
    """Build a serialized Chunk dict (matching what trigger_pipeline stores)."""
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            circular_ref="SEBI/TEST/001",
            start_page=start_page,
            end_page=end_page,
            topic_number=topic,
            section_path=f"I.{topic}",
            char_count=len(text),
        ),
    ).model_dump(mode="json")


def _make_obligation(clause_id: str, text: str = "") -> ObligationClause:
    return ObligationClause(
        clause_id=clause_id,
        circular_ref="SEBI/TEST/001",
        obligation_type=ObligationType.TIMELINE,
        clause_text=text or f"Obligation {clause_id}",
        timeline_params=TimelineParams(offset=1, unit="days"),
    )


def _make_verdict(verdict_id: str, obligation_ref: str, fsm_ref: str, status: VerdictStatus = VerdictStatus.COMPLIANT) -> ComplianceVerdict:
    return ComplianceVerdict(
        verdict_id=verdict_id,
        obligation_ref=obligation_ref,
        broker_id="B-TEST-001",
        fsm_ref=fsm_ref,
        status=status,
        current_state="COMPLIANT",
        evidence={"matched_events": 1, "transition_log": []},
        evaluated_at="2026-07-09T12:00:00Z",
    )


def _make_locked_fsm(
    locked_fsm_id: str = "LOCKED-001",
    fsm_id: str = "FSM-001",
    obligation_ref: str = "CL-01",
    status: LockStatus = LockStatus.APPROVED,
) -> LockedFSM:
    from app.models.scoreboard import HashLink
    fsm = HybridFSM(
        fsm_id=fsm_id,
        obligation_ref=obligation_ref,
        circular_ref="SEBI/TEST/001",
        initial_state="PENDING",
        states=[
            FSMState(name="PENDING"),
            FSMState(name="DUE"),
            FSMState(name="COMPLIANT"),
            FSMState(name="LATE"),
            FSMState(name="NON_COMPLIANT"),
        ],
        transitions=[
            FSMTransition(from_state="PENDING", to_state="DUE", trigger_event="trade_executed"),
            FSMTransition(from_state="DUE", to_state="COMPLIANT", trigger_event="margin_collected"),
            FSMTransition(from_state="DUE", to_state="LATE", trigger_event="deadline_passed"),
        ],
        timeline_rules=[
            TimelineRule(
                start_event="trade_executed",
                deadline_offset=1,
                grace_period=0,
                time_unit="days",
                overdue_transition="LATE",
            ),
        ],
    )
    link = HashLink(index=0, data_hash="a" * 64, previous_hash="0" * 64, link_hash="b" * 64)
    return LockedFSM(
        locked_fsm_id=locked_fsm_id,
        fsm_id=fsm_id,
        obligation_ref=obligation_ref,
        circular_ref="SEBI/TEST/001",
        version=1,
        original_fsm=fsm,
        status=status,
        reviewer="test_reviewer",
        reviewed_at="2026-07-09T10:00:00Z",
        integrity_hash="i" * 64,
        hash_link=link,
    )


# =============================================================================
# Evidence assembly in the runner
# =============================================================================


class TestEvidenceAssembly:
    """EvidenceService is called automatically during pipeline execution."""

    def test_assemble_evidence_populates_evidence_map(self) -> None:
        """After _assemble_evidence, state.evidence_map has entries."""
        _set_store({})

        state = CompliancePipelineState(
            run_id="run-test-ev",
            circular_id="SEBI/TEST/001",
            circular_path="/fake/path.pdf",
            chunk_objects=[
                _make_chunk("chunk-0", "Stock brokers shall collect margins by T+1 day.", topic=1),
                _make_chunk("chunk-1", "Audit shall be conducted half-yearly.", topic=2),
            ],
            obligation_clauses=[
                _make_obligation("CL-01", "Collect margins by T+1"),
                _make_obligation("CL-02", "Conduct half-yearly audit"),
            ],
            compliance_verdicts=[
                _make_verdict("VER-01", "CL-01", "FSM-01"),
                _make_verdict("VER-02", "CL-02", "FSM-02"),
            ],
        )

        runner = PipelineRunner(llm_client=None)

        async def _run():
            await runner._assemble_evidence(state)

        asyncio.run(_run())

        assert len(state.evidence_map) == 2
        assert "VER-01" in state.evidence_map
        assert "VER-02" in state.evidence_map

        ev1 = state.evidence_map["VER-01"]
        assert ev1["verdict_id"] == "VER-01"
        assert ev1["attribution_method"] == "conservative"
        assert ev1["pipeline_run_id"] == "run-test-ev"
        assert len(ev1["fsm_provenance"]["obligation_source"]["source_chunks"]) == 2  # conservative: all→all

    def test_skips_when_no_chunk_objects(self) -> None:
        """V1 path (no RAG chunks) skips evidence assembly gracefully."""
        _set_store({})

        state = CompliancePipelineState(
            run_id="run-test-v1",
            circular_id="SEBI/TEST/001",
            circular_path="/fake/path.pdf",
            chunk_objects=[],  # V1: no chunks
            obligation_clauses=[_make_obligation("CL-01")],
            compliance_verdicts=[_make_verdict("VER-01", "CL-01", "FSM-01")],
        )

        runner = PipelineRunner(llm_client=None)

        async def _run():
            await runner._assemble_evidence(state)

        asyncio.run(_run())

        assert state.evidence_map == {}  # Skipped gracefully

    def test_skips_when_no_verdicts(self) -> None:
        """No verdicts → no evidence to assemble."""
        _set_store({})

        state = CompliancePipelineState(
            run_id="run-test-no-v",
            circular_id="SEBI/TEST/001",
            circular_path="/fake/path.pdf",
            chunk_objects=[_make_chunk("chunk-0", "text")],
            obligation_clauses=[_make_obligation("CL-01")],
            compliance_verdicts=[],  # No verdicts
        )

        runner = PipelineRunner(llm_client=None)

        async def _run():
            await runner._assemble_evidence(state)

        asyncio.run(_run())

        assert state.evidence_map == {}

    def test_evidence_attribution_is_conservative(self) -> None:
        """Attribution method is recorded as 'conservative'."""
        _set_store({})

        state = CompliancePipelineState(
            run_id="run-test-att",
            circular_id="SEBI/TEST/001",
            circular_path="/fake/path.pdf",
            chunk_objects=[
                _make_chunk("chunk-0", "Margin collection requirement text.", topic=1),
                _make_chunk("chunk-1", "KYC verification requirement text.", topic=2),
                _make_chunk("chunk-2", "Audit frequency requirement text.", topic=3),
            ],
            obligation_clauses=[
                _make_obligation("CL-01", "Collect margins"),
            ],
            compliance_verdicts=[
                _make_verdict("VER-01", "CL-01", "FSM-01"),
            ],
        )

        runner = PipelineRunner(llm_client=None)

        async def _run():
            await runner._assemble_evidence(state)

        asyncio.run(_run())

        ev = state.evidence_map["VER-01"]
        src = ev["fsm_provenance"]["obligation_source"]
        assert src["attribution_method"] == "conservative"
        assert len(src["source_chunks"]) == 3  # All chunks attributed to the single obligation

    def test_chunk_provenance_metadata_preserved(self) -> None:
        """ChunkCitation carries correct page_range from ChunkMetadata."""
        _set_store({})

        state = CompliancePipelineState(
            run_id="run-test-prov",
            circular_id="SEBI/TEST/001",
            circular_path="/fake/path.pdf",
            chunk_objects=[
                _make_chunk("chunk-p3", "Text on page 3.", start_page=3, end_page=3, topic=5),
                _make_chunk("chunk-p5", "Text spanning pages 5-6.", start_page=5, end_page=6, topic=7),
            ],
            obligation_clauses=[_make_obligation("CL-01")],
            compliance_verdicts=[_make_verdict("VER-01", "CL-01", "FSM-01")],
        )

        runner = PipelineRunner(llm_client=None)

        async def _run():
            await runner._assemble_evidence(state)

        asyncio.run(_run())

        chunks = state.evidence_map["VER-01"]["fsm_provenance"]["obligation_source"]["source_chunks"]
        pages = sorted((c["page_range"][0], c["page_range"][1]) for c in chunks)
        assert (3, 3) in pages
        assert (5, 6) in pages


# =============================================================================
# Evidence API with real data
# =============================================================================


class TestEvidenceAPIWithData:
    """GET /api/evidence/{verdict_id} returns real data after pipeline run."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Seed the run store with a completed pipeline run that has evidence."""
        from app.pipeline.runner import _set_store, RunRecord
        _set_store({})

        state = CompliancePipelineState(
            run_id="run-test-api",
            circular_id="SEBI/TEST/001",
            circular_path="/fake/path.pdf",
            status=PipelineStatus.COMPLETED,
            chunk_objects=[
                _make_chunk("chunk-api-0", "Regulatory text about margin collection.", topic=1),
            ],
            obligation_clauses=[_make_obligation("CL-API", "Collect margins")],
            compliance_verdicts=[
                _make_verdict("VER-API-001", "CL-API", "FSM-API"),
            ],
        )

        # Manually call evidence assembly to populate evidence_map
        runner = PipelineRunner(llm_client=None)

        async def _assemble():
            await runner._assemble_evidence(state)

        asyncio.run(_assemble())

        store = _get_store()
        store["run-test-api"] = RunRecord(state=state, created_at="2026-07-09T12:00:00Z")

        yield
        _set_store({})

    def test_evidence_endpoint_returns_real_data(self, setup) -> None:
        """GET /api/evidence/{verdict_id} returns 200 with evidence data."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/api/evidence/VER-API-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict_id"] == "VER-API-001"
        assert data["evidence_id"].startswith("EV-")
        assert data["attribution_method"] == "conservative"
        assert data["pipeline_run_id"] == "run-test-api"

    def test_evidence_endpoint_404_for_unknown_verdict(self, setup) -> None:
        """Unknown verdict returns 404."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/api/evidence/NONEXISTENT-VERDICT")
        assert resp.status_code == 404

    def test_evidence_endpoint_404_for_verdict_without_evidence(self, setup) -> None:
        """Verdict exists but no evidence assembled → 404."""
        from fastapi.testclient import TestClient
        from app.main import app

        # Add a second verdict to the state that was NOT processed by evidence assembly
        store = _get_store()
        state = store["run-test-api"].state
        state.compliance_verdicts.append(
            _make_verdict("VER-NO-EVIDENCE", "CL-OTHER", "FSM-OTHER")
        )

        client = TestClient(app)
        resp = client.get("/api/evidence/VER-NO-EVIDENCE")
        assert resp.status_code == 404
        detail = resp.json().get("detail", "")
        assert "not yet assembled" in detail.lower() or "not found" in detail.lower()


# =============================================================================
# Backward compatibility
# =============================================================================


class TestBackwardCompatibility:
    """V1 path and existing APIs are unchanged."""

    def test_use_rag_false_no_chunk_objects(self) -> None:
        """When use_rag=False, chunk_objects is empty (default)."""
        state = CompliancePipelineState(
            run_id="run-v1",
            circular_id="SEBI/TEST",
            circular_path="/fake/path.pdf",
        )
        assert state.chunk_objects == []
        assert state.evidence_map == {}

    def test_chunks_field_unchanged(self) -> None:
        """The existing chunks: list[str] field still works as before."""
        state = CompliancePipelineState(
            run_id="run-v1",
            circular_id="SEBI/TEST",
            circular_path="/fake/path.pdf",
            chunks=["chunk text 1", "chunk text 2"],
        )
        assert len(state.chunks) == 2
        assert state.chunk_objects == []  # Not populated in V1 path

    def test_state_serializable(self) -> None:
        """State with evidence_map can be serialized (model_dump)."""
        state = CompliancePipelineState(
            run_id="run-ser",
            circular_id="SEBI/TEST",
            circular_path="/fake/path.pdf",
            evidence_map={
                "VER-01": {"verdict_id": "VER-01", "evidence_id": "EV-01"},
            },
        )
        data = state.model_dump(mode="json")
        assert data["evidence_map"]["VER-01"]["verdict_id"] == "VER-01"

    def test_existing_pipeline_tests_unchanged(self) -> None:
        """Sanity: the orchestrator module still imports cleanly."""
        from app.pipeline.runner import PipelineRunner, get_run_state, get_all_runs
        assert PipelineRunner is not None
        assert get_run_state is not None
        assert get_all_runs is not None


# =============================================================================
# EvidenceService integration
# =============================================================================


class TestEvidenceServiceIntegration:
    """EvidenceService.build_evidence() produces correct output."""

    def test_empty_verdicts_returns_empty(self) -> None:
        from app.pipeline.evidence_service import EvidenceService
        service = EvidenceService()
        result = service.build_evidence(
            verdicts=[],
            chunks=[],
            obligations=[],
            circular_ref="TEST",
            pdf_path="/fake.pdf",
        )
        assert result == {}

    def test_run_id_recorded_in_evidence(self) -> None:
        from app.pipeline.evidence_service import EvidenceService

        chunks = [
            Chunk(chunk_id="c1", text="text", metadata=ChunkMetadata(circular_ref="TEST", char_count=4)),
        ]
        obligations = [_make_obligation("CL-01")]
        verdicts = [_make_verdict("VER-01", "CL-01", "FSM-01")]

        service = EvidenceService()
        result = service.build_evidence(
            verdicts=verdicts,
            chunks=chunks,
            obligations=obligations,
            circular_ref="TEST",
            pdf_path="/fake.pdf",
            run_id="my-run-id",
        )
        assert result["VER-01"].pipeline_run_id == "my-run-id"

    def test_enrich_bbox_does_not_crash_on_fake_pdf(self) -> None:
        """bbox enrichment graciously handles missing PDF."""
        from app.pipeline.evidence_service import EvidenceService

        chunks = [
            Chunk(chunk_id="c1", text="text", metadata=ChunkMetadata(circular_ref="TEST", char_count=4)),
        ]
        obligations = [_make_obligation("CL-01")]
        verdicts = [_make_verdict("VER-01", "CL-01", "FSM-01")]

        service = EvidenceService()
        result = service.build_evidence(
            verdicts=verdicts,
            chunks=chunks,
            obligations=obligations,
            circular_ref="TEST",
            pdf_path="/nonexistent.pdf",
            enrich_bbox=True,
        )
        # Should not raise — enriches gracefully
        assert result["VER-01"].verdict_id == "VER-01"
        # page_regions should still be empty (PDF not found)
        for src in result["VER-01"].fsm_provenance.obligation_source.source_chunks:
            assert src.page_regions == []
