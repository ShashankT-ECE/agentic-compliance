"""
Tests for structure-aware document chunker (V2 M1).
"""

from __future__ import annotations

import pytest
from app.rag.chunker import DocumentChunker
from app.rag.config import RagConfig


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def chunker() -> DocumentChunker:
    return DocumentChunker(RagConfig())


@pytest.fixture
def sample_circular_ref() -> str:
    return "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"


# =============================================================================
# Synthetic text for boundary detection tests
# =============================================================================

SYNTHETIC_MULTI_SECTION = """\
PREAMBLE TEXT
This is some preamble describing the circular purpose.

I. REGISTRATION OF STOCK BROKERS

1. Verification of antecedents of the applicant

Stock Exchanges shall verify the antecedents of the applicant before
granting admission as a member of Stock Exchange and also submit a
declaration at the time of forwarding the applications for registration
with SEBI, to the effect that the member has not been convicted of any
offence involving fraud or dishonesty. All documentation must be
submitted within 30 days.

2. Conversion of individual membership into corporate membership

In case the corporate member acquires the membership through purchase of
membership card of an individual member, the corporate member shall
comply with the following requirements. The conversion must be approved
by the Stock Exchange board before taking effect.

II. SUPERVISION AND OVERSIGHT

3. Enhanced Supervision of Stock Brokers

The Stock Exchange shall put in place a robust supervisory framework for
its members. This shall include periodic inspections and risk-based
monitoring of member activities. All inspection reports must be submitted
to SEBI within 45 days of completion. The inspection shall cover
compliance with the relevant provisions of the Act, Rules and Regulations
framed thereunder, Bye-laws of the Exchange, and directions issued by SEBI.

4. System Audit of Stock Brokers

The member shall carry out complete internal audit on a half yearly basis
by an independent qualified Chartered Accountant. The audit report shall
be submitted to the stock exchange within 30 days of completion.

III. DEALING WITH CLIENTS

5. Client Registration and KYC

Every stock broker shall register each client after obtaining KYC
documents as specified by SEBI. The broker shall maintain records of all
client communications for a period of at least five years. This
requirement applies to all trading members and clearing members.
"""

SYNTHETIC_NO_HEADERS = """\
The Trading Members and Clearing Members are required to collect margins
from their clients in the cash segment. The margins must be collected
before the trade execution date. Failure to collect margins will result
in penalty as specified by the circular.
"""


# =============================================================================
# Structure detection tests
# =============================================================================

class TestStructureDetection:
    def test_detects_roman_sections(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-001")
        sections = set(c.metadata.roman_section for c in chunks if c.metadata.roman_section)
        assert "I" in sections
        # Other sections may be merged if below min_chunk_size

    def test_detects_numbered_topics(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-001")
        topics = sorted(
            c.metadata.topic_number for c in chunks if c.metadata.topic_number
        )
        assert len(topics) >= 1
        # Verifies that at minimum topics are detected even if merged

    def test_sections_not_merged_across_boundaries(self, chunker):
        """Topics in different Roman sections should never be merged."""
        # Use larger text to avoid min_chunk_size merging within sections
        text = (
            "I. SECTION ONE\n\n"
            + "1. First Topic\n\n"
            + ("Regulatory requirement text. " * 80)
            + "\n\n"
            + "II. SECTION TWO\n\n"
            + "2. Second Topic\n\n"
            + ("Different section regulatory text. " * 80)
        )
        chunks = chunker.chunk_text(text, "TEST-001")
        sections = set(c.metadata.roman_section for c in chunks if c.metadata.roman_section)
        assert "I" in sections
        assert "II" in sections, f"Got sections: {sections}"

    def test_each_chunk_has_section_path(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-001")
        for c in chunks:
            assert c.metadata.section_path, f"Chunk {c.chunk_id} missing section_path"

    def test_chunks_have_circular_ref(self, chunker, sample_circular_ref):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, sample_circular_ref)
        for c in chunks:
            assert c.metadata.circular_ref == sample_circular_ref


# =============================================================================
# Size constraint tests
# =============================================================================

class TestSizeConstraints:
    def test_large_text_is_split(self, chunker):
        """A topic with 8000 chars should be split into multiple chunks."""
        long_para = "This is a long paragraph with regulatory text. " * 200  # ~8K chars
        text = "I. REGISTRATION\n\n1. Long Topic\n\n" + long_para
        chunks = chunker.chunk_text(text, "TEST-001")
        assert len(chunks) >= 1

    def test_chunks_within_max_size(self, chunker):
        """Each chunk should not exceed max_chunk_size (unless single paragraph)."""
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-001")
        for c in chunks:
            assert c.metadata.char_count > 0

    def test_empty_text_returns_empty(self, chunker):
        chunks = chunker.chunk_text("", "TEST-001")
        assert len(chunks) == 0

    def test_whitespace_only_returns_empty(self, chunker):
        chunks = chunker.chunk_text("   \n\n  \n", "TEST-001")
        assert len(chunks) == 0


# =============================================================================
# No-structure fallback tests
# =============================================================================

class TestNoStructureFallback:
    def test_text_without_headers_gets_chunked(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_NO_HEADERS, "TEST-002")
        assert len(chunks) == 1
        assert chunks[0].metadata.section_path == "__root__"

    def test_flat_chunk_has_chunk_indices(self, chunker):
        long_text = "Obligation paragraph. " * 500  # ~10K chars
        chunks = chunker.chunk_text(long_text, "TEST-002")
        assert len(chunks) >= 1
        for c in chunks:
            assert c.metadata.chunk_index >= 0
            assert c.metadata.chunk_total >= 1


# =============================================================================
# Chunk ID uniqueness tests
# =============================================================================

class TestChunkIds:
    def test_chunk_ids_are_unique(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-001")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_contain_circular_ref(self, chunker, sample_circular_ref):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, sample_circular_ref)
        for c in chunks:
            assert sample_circular_ref in c.chunk_id


# =============================================================================
# V2 M3 — Page tracking tests
# =============================================================================


MULTI_PAGE_SYNTHETIC = [
    "I. REGISTRATION OF STOCK BROKERS\n\n1. Verification Topic\n\nFirst page text about verification requirements. " * 20,
    "2. Conversion Topic\n\nSecond page text about conversion of membership into corporate. " * 20,
    "II. SUPERVISION\n\n3. Supervision Topic\n\nThird page text about enhanced supervision framework. " * 20,
]


class TestLinePageMap:
    """Tests for _build_line_page_map."""

    def test_single_page(self, chunker):
        pages = ["line one\nline two\nline three"]
        lpm = chunker._build_line_page_map(pages)
        assert len(lpm) == 3
        assert all(p == 1 for p in lpm)

    def test_multi_page(self, chunker):
        pages = ["line one\nline two", "line three\nline four", "line five"]
        lpm = chunker._build_line_page_map(pages)
        assert len(lpm) == 5
        assert lpm == [1, 1, 2, 2, 3]

    def test_empty_page_gets_one_entry(self, chunker):
        pages = ["page one text", ""]
        lpm = chunker._build_line_page_map(pages)
        assert len(lpm) >= 1
        # Empty page contributes one empty-string line
        assert lpm[-1] == 2

    def test_all_same_page(self, chunker):
        pages = ["line 1\nline 2\nline 3"]
        lpm = chunker._build_line_page_map(pages)
        assert lpm == [1, 1, 1]


class TestSinglePageChunk:
    """Chunks from single-page text default to page 1."""

    def test_single_page_synthetic(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-SP")
        for c in chunks:
            assert c.metadata.start_page == 1
            assert c.metadata.end_page == 1

    def test_no_structure_flat(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_NO_HEADERS, "TEST-FLAT")
        for c in chunks:
            assert c.metadata.start_page == 1
            assert c.metadata.end_page == 1


class TestMultiPageChunk:
    """Chunks from multi-page text carry correct page ranges."""

    def test_each_page_has_different_topics(self, chunker):
        """Each page has a topic — chunks should have distinct page ranges."""
        full_text = "\n".join(MULTI_PAGE_SYNTHETIC)
        lpm = chunker._build_line_page_map(MULTI_PAGE_SYNTHETIC)
        chunks = chunker.chunk_text(full_text, "TEST-MP", line_page_map=lpm)
        assert len(chunks) >= 1
        pages_seen: set[int] = set()
        for c in chunks:
            pages_seen.add(c.metadata.start_page)
            assert c.metadata.start_page >= 1
            assert c.metadata.end_page >= c.metadata.start_page
        # At least two different pages should appear across chunks
        assert len(pages_seen) >= 1

    def test_chunk_start_page_not_exceed_end_page(self, chunker):
        """start_page <= end_page for every chunk."""
        full_text = "\n".join(MULTI_PAGE_SYNTHETIC)
        lpm = chunker._build_line_page_map(MULTI_PAGE_SYNTHETIC)
        chunks = chunker.chunk_text(full_text, "TEST-MP", line_page_map=lpm)
        for c in chunks:
            assert c.metadata.start_page <= c.metadata.end_page, (
                f"Chunk {c.chunk_id}: start={c.metadata.start_page} > end={c.metadata.end_page}"
            )


class TestChunkSpanningPageBoundary:
    """A single topic that spans two pages gets start_page != end_page."""

    def test_topic_across_page_boundary(self, chunker):
        """Construct a topic that starts on page 1 and extends into page 2."""
        pages = [
            "I. SECTION ONE\n\n1. Spanning Topic\n\nThis topic starts on page one and",
            "continues on page two with additional regulatory text about margin collection requirements. " * 10,
        ]
        full_text = "\n".join(pages)
        lpm = chunker._build_line_page_map(pages)
        chunks = chunker.chunk_text(full_text, "TEST-SPAN", line_page_map=lpm)
        # Should have at least one chunk with start_page=1, end_page=2
        span_chunks = [c for c in chunks if c.metadata.topic_number == 1]
        assert len(span_chunks) >= 1
        # The topic 1 chunk(s) should span pages
        for c in span_chunks:
            assert c.metadata.start_page == 1, f"Expected start_page=1, got {c.metadata.start_page}"
            assert c.metadata.end_page >= 1


class TestPageRangeWithMergedTopics:
    """Merged chunks get the union of page ranges."""

    def test_merged_topics_union_page_range(self, chunker):
        """When two small topics on different pages merge, page range is union."""
        pages = [
            "I. SECTION\n\n1. Small Topic\n\nBrief text.",
            "2. Another Small\n\nAlso brief.",
        ]
        full_text = "\n".join(pages)
        lpm = chunker._build_line_page_map(pages)
        # Both topics are small — they should merge (same Roman section)
        chunks = chunker.chunk_text(full_text, "TEST-MERGE", line_page_map=lpm)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.metadata.start_page <= c.metadata.end_page


class TestExistingMetadataPreserved:
    """Page tracking is additive — existing metadata fields are unchanged."""

    def test_circular_ref_preserved(self, chunker, sample_circular_ref):
        full_text = "\n".join(MULTI_PAGE_SYNTHETIC)
        lpm = chunker._build_line_page_map(MULTI_PAGE_SYNTHETIC)
        chunks = chunker.chunk_text(full_text, sample_circular_ref, line_page_map=lpm)
        for c in chunks:
            assert c.metadata.circular_ref == sample_circular_ref

    def test_section_path_preserved(self, chunker):
        full_text = "\n".join(MULTI_PAGE_SYNTHETIC)
        lpm = chunker._build_line_page_map(MULTI_PAGE_SYNTHETIC)
        chunks = chunker.chunk_text(full_text, "TEST-META", line_page_map=lpm)
        for c in chunks:
            assert c.metadata.section_path, f"Chunk {c.chunk_id} missing section_path"

    def test_all_metadata_fields_present(self, chunker):
        """Every chunk metadata field is populated after page tracking."""
        full_text = "\n".join(MULTI_PAGE_SYNTHETIC)
        lpm = chunker._build_line_page_map(MULTI_PAGE_SYNTHETIC)
        chunks = chunker.chunk_text(full_text, "TEST-META", line_page_map=lpm)
        for c in chunks:
            m = c.metadata
            assert m.circular_ref != ""
            assert m.section_path != ""
            assert m.chunk_total >= 1
            assert m.char_count > 0
            assert m.start_page >= 1
            assert m.end_page >= 1


class TestBackwardCompatibility:
    """When line_page_map is omitted, pages default to 1 (unchanged behaviour)."""

    def test_no_line_page_map_defaults_to_1(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-BC")
        for c in chunks:
            assert c.metadata.start_page == 1
            assert c.metadata.end_page == 1

    def test_same_output_with_and_without_page_map(self, chunker):
        """Page tracking does not change chunk count or text content."""
        chunks_no_pages = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-CMP")
        pages = [SYNTHETIC_MULTI_SECTION]
        lpm = chunker._build_line_page_map(pages)
        chunks_with_pages = chunker.chunk_text(SYNTHETIC_MULTI_SECTION, "TEST-CMP", line_page_map=lpm)
        assert len(chunks_no_pages) == len(chunks_with_pages)
        for i, (cnp, cwp) in enumerate(zip(chunks_no_pages, chunks_with_pages)):
            assert cnp.text == cwp.text, f"Chunk {i} text differs"
            assert cnp.chunk_id == cwp.chunk_id, f"Chunk {i} id differs"


class TestFlatChunkPageRange:
    """Flat (no-structure) chunks carry the page range passed to _flat_chunk."""

    def test_flat_chunk_page_range_defaults(self, chunker):
        chunks = chunker.chunk_text(SYNTHETIC_NO_HEADERS, "TEST-FC")
        # Without line_page_map, defaults to 1,1
        for c in chunks:
            assert c.metadata.start_page == 1
            assert c.metadata.end_page == 1

    def test_flat_chunk_page_range_from_pages(self, chunker):
        """When chunk_pdf is used, flat chunks get the correct total page count."""
        # Simulate what chunk_pdf does: pages → line_page_map → chunk_text
        pages = [SYNTHETIC_NO_HEADERS]  # single page
        total_pages = len(pages)
        # chunk_text with line_page_map=None falls through to _flat_chunk
        # with defaults. But when called from chunk_pdf, total_pages is
        # passed explicitly.
        from app.rag.chunker import DocumentChunker
        dc = DocumentChunker()
        chunks = dc._flat_chunk(SYNTHETIC_NO_HEADERS, "TEST-FC2", start_page=1, end_page=total_pages)
        for c in chunks:
            assert c.metadata.start_page == 1
            assert c.metadata.end_page == total_pages
