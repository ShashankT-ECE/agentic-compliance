"""
Tests for evidence models — V2 M3.

Covers Rectangle, PageRegion, ChunkCitation, ObligationSource,
FSMProvenance, EvidenceReference, and the updated ChunkMetadata fields.
"""

from __future__ import annotations

import pytest

from app.models.evidence import (
    ChunkCitation,
    EvidenceReference,
    FSMProvenance,
    ObligationSource,
    PageRegion,
    Rectangle,
)
from app.rag.schemas import ChunkMetadata


# =============================================================================
# Rectangle
# =============================================================================


class TestRectangle:
    def test_valid_rectangle(self) -> None:
        r = Rectangle(x0=72.0, y0=100.0, x1=432.0, y1=122.0)
        assert r.x0 == 72.0
        assert r.y0 == 100.0
        assert r.x1 == 432.0
        assert r.y1 == 122.0

    def test_coordinates_must_be_non_negative(self) -> None:
        with pytest.raises(Exception):
            Rectangle(x0=-1.0, y0=1, x1=10, y1=10)

    def test_json_roundtrip(self) -> None:
        r = Rectangle(x0=10.5, y0=20.5, x1=100.5, y1=50.5)
        data = r.model_dump(mode="json")
        parsed = Rectangle.model_validate(data)
        assert parsed.x0 == 10.5
        assert parsed.y0 == 20.5


# =============================================================================
# PageRegion
# =============================================================================


class TestPageRegion:
    def test_single_rectangle(self) -> None:
        rect = Rectangle(x0=10, y0=20, x1=100, y1=30)
        region = PageRegion(page_number=3, rectangles=[rect])
        assert region.page_number == 3
        assert len(region.rectangles) == 1
        assert region.rectangles[0].x0 == 10

    def test_multiple_rectangles(self) -> None:
        rects = [
            Rectangle(x0=10, y0=20, x1=100, y1=30),
            Rectangle(x0=10, y0=50, x1=200, y1=60),
        ]
        region = PageRegion(page_number=5, rectangles=rects)
        assert region.page_number == 5
        assert len(region.rectangles) == 2

    def test_empty_rectangles_ok(self) -> None:
        region = PageRegion(page_number=1)
        assert region.rectangles == []

    def test_page_number_must_be_positive(self) -> None:
        with pytest.raises(Exception):
            PageRegion(page_number=0)

    def test_json_roundtrip(self) -> None:
        region = PageRegion(
            page_number=2,
            rectangles=[Rectangle(x0=1, y0=2, x1=3, y1=4)],
        )
        data = region.model_dump(mode="json")
        parsed = PageRegion.model_validate(data)
        assert parsed.page_number == 2
        assert len(parsed.rectangles) == 1


# =============================================================================
# ChunkCitation
# =============================================================================


class TestChunkCitation:
    def test_minimal_citation(self) -> None:
        c = ChunkCitation(chunk_id="C::1")
        assert c.chunk_id == "C::1"
        assert c.citation_text == ""
        assert c.page_range == (1, 1)
        assert c.page_regions == []

    def test_full_citation(self) -> None:
        regions = [
            PageRegion(
                page_number=3,
                rectangles=[Rectangle(x0=10, y0=20, x1=100, y1=30)],
            ),
            PageRegion(
                page_number=3,
                rectangles=[Rectangle(x0=10, y0=40, x1=200, y1=50)],
            ),
        ]
        c = ChunkCitation(
            chunk_id="SEBI::chunk::39::000",
            citation_text="Stock brokers shall collect margins...",
            page_range=(3, 3),
            page_regions=regions,
        )
        assert c.chunk_id == "SEBI::chunk::39::000"
        assert c.citation_text.startswith("Stock brokers")
        assert c.page_range == (3, 3)
        assert len(c.page_regions) == 2

    def test_default_page_range(self) -> None:
        c = ChunkCitation(chunk_id="X")
        assert c.page_range == (1, 1)

    def test_page_regions_initially_empty(self) -> None:
        """Bounding boxes are populated lazily after bbox extraction."""
        c = ChunkCitation(chunk_id="C::1")
        assert c.page_regions == []


# =============================================================================
# ObligationSource
# =============================================================================


class TestObligationSource:
    def test_minimal(self) -> None:
        o = ObligationSource(obligation_ref="CL-01")
        assert o.obligation_ref == "CL-01"
        assert o.source_chunks == []
        assert o.attribution_method == "conservative"

    def test_with_chunks(self) -> None:
        chunks = [
            ChunkCitation(chunk_id="A::0", page_range=(1, 1)),
            ChunkCitation(chunk_id="A::1", page_range=(2, 2)),
        ]
        o = ObligationSource(
            obligation_ref="CL-02",
            source_chunks=chunks,
            attribution_method="conservative",
        )
        assert len(o.source_chunks) == 2
        assert o.source_chunks[1].page_range == (2, 2)


# =============================================================================
# FSMProvenance
# =============================================================================


class TestFSMProvenance:
    def test_minimal(self) -> None:
        f = FSMProvenance(fsm_id="FSM-01")
        assert f.fsm_id == "FSM-01"
        assert f.locked_fsm_id is None
        assert f.obligation_source.obligation_ref == ""

    def test_with_locked_fsm(self) -> None:
        f = FSMProvenance(
            fsm_id="FSM-02",
            locked_fsm_id="LOCKED-02",
            obligation_source=ObligationSource(obligation_ref="CL-03"),
        )
        assert f.locked_fsm_id == "LOCKED-02"
        assert f.obligation_source.obligation_ref == "CL-03"


# =============================================================================
# EvidenceReference
# =============================================================================


class TestEvidenceReference:
    def test_minimal(self) -> None:
        e = EvidenceReference(verdict_id="VER-01", circular_ref="SEBI/1")
        assert e.verdict_id == "VER-01"
        assert e.circular_ref == "SEBI/1"
        assert e.evidence_id.startswith("EV-")
        assert len(e.evidence_id) == 15
        assert e.attribution_method == "conservative"

    def test_evidence_id_unique(self) -> None:
        ids = {EvidenceReference(verdict_id=f"V-{i}", circular_ref="X").evidence_id for i in range(20)}
        assert len(ids) == 20

    def test_full_chain(self) -> None:
        """Construct the complete provenance chain end-to-end."""
        region = PageRegion(
            page_number=3,
            rectangles=[Rectangle(x0=10, y0=20, x1=100, y1=30)],
        )
        citation = ChunkCitation(
            chunk_id="SEBI::t39::000",
            citation_text="Collect margins by T+1",
            page_range=(3, 3),
            page_regions=[region],
        )
        obl_source = ObligationSource(
            obligation_ref="CIRC-2025-CL-03",
            source_chunks=[citation],
            attribution_method="conservative",
        )
        fsm_prov = FSMProvenance(
            fsm_id="FSM-ABC123",
            locked_fsm_id="LOCKED-DEF456",
            obligation_source=obl_source,
        )
        evidence = EvidenceReference(
            verdict_id="VER-XYZ",
            circular_ref="SEBI/HO/MIRSD/P/CIR/2025/57",
            fsm_provenance=fsm_prov,
            pipeline_run_id="run-abc123",
        )

        assert evidence.verdict_id == "VER-XYZ"
        fsm = evidence.fsm_provenance
        assert fsm.fsm_id == "FSM-ABC123"
        assert fsm.locked_fsm_id == "LOCKED-DEF456"
        obl = fsm.obligation_source
        assert obl.obligation_ref == "CIRC-2025-CL-03"
        assert len(obl.source_chunks) == 1
        chunk = obl.source_chunks[0]
        assert chunk.page_range == (3, 3)
        assert len(chunk.page_regions) == 1
        assert chunk.page_regions[0].page_number == 3
        assert len(chunk.page_regions[0].rectangles) == 1

    def test_json_roundtrip(self) -> None:
        e = EvidenceReference(
            verdict_id="VER-01",
            circular_ref="SEBI/1",
            fsm_provenance=FSMProvenance(
                fsm_id="FSM-01",
                locked_fsm_id="LOCKED-01",
                obligation_source=ObligationSource(
                    obligation_ref="CL-01",
                    source_chunks=[
                        ChunkCitation(
                            chunk_id="C::1",
                            citation_text="text",
                            page_range=(2, 3),
                            page_regions=[
                                PageRegion(
                                    page_number=2,
                                    rectangles=[Rectangle(x0=1, y0=2, x1=3, y1=4)],
                                ),
                            ],
                        ),
                    ],
                ),
            ),
        )
        data = e.model_dump(mode="json")
        parsed = EvidenceReference.model_validate(data)
        assert parsed.evidence_id == e.evidence_id
        assert parsed.attribution_method == "conservative"
        # Traverse the chain to page regions
        chunk_cit = parsed.fsm_provenance.obligation_source.source_chunks[0]
        assert chunk_cit.page_regions[0].rectangles[0].x0 == 1


# =============================================================================
# ChunkMetadata — no PDF concepts
# =============================================================================


class TestChunkMetadataPageRange:
    def test_defaults_to_page_1(self) -> None:
        m = ChunkMetadata(circular_ref="TEST")
        assert m.start_page == 1
        assert m.end_page == 1

    def test_explicit_pages(self) -> None:
        m = ChunkMetadata(circular_ref="TEST", start_page=3, end_page=5)
        assert m.start_page == 3
        assert m.end_page == 5

    def test_start_page_must_be_positive(self) -> None:
        with pytest.raises(Exception):
            ChunkMetadata(circular_ref="TEST", start_page=0)

    def test_no_pdf_concepts_in_chunk_metadata(self) -> None:
        """ChunkMetadata must NOT carry bounding boxes or PDF-specific concepts."""
        field_names = set(ChunkMetadata.model_fields.keys())
        assert "page_boxes" not in field_names
        assert "page_regions" not in field_names
        assert "bbox" not in field_names
        assert "bounding_box" not in field_names
        assert "coordinates" not in field_names
        assert "x0" not in field_names
        assert "citation_text" not in field_names
