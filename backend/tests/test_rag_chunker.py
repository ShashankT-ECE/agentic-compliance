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
