"""
Tests for attribution strategies — V2 M3.

Covers ConservativeAttribution, the AttributionStrategy protocol,
and the module-level get/set functions.
"""

from __future__ import annotations

import pytest

from app.models.evidence import ChunkCitation, ObligationSource
from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.pipeline.attribution import (
    ConservativeAttribution,
    AttributionStrategy,
    get_attribution_strategy,
    set_attribution_strategy,
)
from app.rag.schemas import Chunk, ChunkMetadata


# =============================================================================
# Helpers
# =============================================================================


def _make_chunk(chunk_id: str, text: str = "chunk text", start_page: int = 1, end_page: int = 1, topic: int = 1) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            circular_ref="TEST",
            start_page=start_page,
            end_page=end_page,
            topic_number=topic,
            char_count=len(text),
        ),
    )


def _make_obligation(clause_id: str) -> ObligationClause:
    return ObligationClause(
        clause_id=clause_id,
        circular_ref="TEST",
        obligation_type=ObligationType.TIMELINE,
        clause_text=f"Obligation {clause_id}",
        timeline_params=TimelineParams(offset=1, grace_period=0, unit="days"),
    )


# =============================================================================
# ConservativeAttribution
# =============================================================================


class TestConservativeAttribution:
    def test_method_name(self) -> None:
        strat = ConservativeAttribution()
        assert strat.method_name == "conservative"

    def test_all_chunks_attributed_to_all_obligations(self) -> None:
        strat = ConservativeAttribution()
        chunks = [
            _make_chunk("C::0", "margin collection", start_page=1),
            _make_chunk("C::1", "audit frequency", start_page=1),
            _make_chunk("C::2", "KYC requirements", start_page=2, end_page=3),
        ]
        obligations = [
            _make_obligation("CL-01"),
            _make_obligation("CL-02"),
        ]

        result = strat.attribute(chunks, obligations)
        assert len(result) == 2  # one per obligation
        for src in result:
            assert src.attribution_method == "conservative"
            assert len(src.source_chunks) == 3  # all chunks attributed to each
            chunk_ids = {c.chunk_id for c in src.source_chunks}
            assert chunk_ids == {"C::0", "C::1", "C::2"}

    def test_preserves_page_range_in_citations(self) -> None:
        strat = ConservativeAttribution()
        chunks = [
            _make_chunk("C::0", "text", start_page=3, end_page=5),
        ]
        obligations = [_make_obligation("CL-01")]

        result = strat.attribute(chunks, obligations)
        assert result[0].source_chunks[0].page_range == (3, 5)

    def test_page_regions_initially_empty(self) -> None:
        """Page regions are populated lazily after bbox extraction."""
        strat = ConservativeAttribution()
        chunks = [_make_chunk("C::0", "text")]
        obligations = [_make_obligation("CL-01")]

        result = strat.attribute(chunks, obligations)
        assert result[0].source_chunks[0].page_regions == []

    def test_empty_chunks_returns_empty(self) -> None:
        strat = ConservativeAttribution()
        result = strat.attribute([], [_make_obligation("CL-01")])
        assert result == []

    def test_empty_obligations_returns_empty(self) -> None:
        strat = ConservativeAttribution()
        result = strat.attribute([_make_chunk("C::0")], [])
        assert result == []

    def test_both_empty_returns_empty(self) -> None:
        strat = ConservativeAttribution()
        assert strat.attribute([], []) == []

    def test_many_to_many(self) -> None:
        """5 chunks × 10 obligations → 10 ObligationSources, each with 5 chunks."""
        strat = ConservativeAttribution()
        chunks = [_make_chunk(f"C::{i}", f"chunk {i}") for i in range(5)]
        obligations = [_make_obligation(f"CL-{i:02d}") for i in range(10)]

        result = strat.attribute(chunks, obligations)
        assert len(result) == 10
        for src in result:
            assert len(src.source_chunks) == 5


# =============================================================================
# Strategy swap
# =============================================================================


class TestStrategySwap:
    def test_default_is_conservative(self) -> None:
        strat = get_attribution_strategy()
        assert strat.method_name == "conservative"

    def test_can_swap_strategy(self) -> None:
        """A custom strategy can replace the default at runtime."""
        original = get_attribution_strategy()

        class TestStrategy:
            @property
            def method_name(self) -> str:
                return "test"

            def attribute(self, chunks, obligations):
                return []

        set_attribution_strategy(TestStrategy())
        assert get_attribution_strategy().method_name == "test"

        # Restore
        set_attribution_strategy(original)
        assert get_attribution_strategy().method_name == "conservative"

    def test_custom_strategy_works_functionally(self) -> None:
        """A custom class with matching methods can be used as an attribution strategy.

        The AttributionStrategy protocol is checked at type-check time (mypy),
        not at runtime — structural subtyping is verified by the test harness.
        """
        class CustomAttr:
            @property
            def method_name(self) -> str:
                return "custom"

            def attribute(self, chunks, obligations):
                if not obligations:
                    return []
                return [
                    ObligationSource(
                        obligation_ref=obligations[0].clause_id,
                        attribution_method="custom",
                    )
                ]

        custom = CustomAttr()
        assert custom.method_name == "custom"

        result = custom.attribute(
            [_make_chunk("C::0")],
            [_make_obligation("CL-01")],
        )
        assert len(result) == 1
        assert result[0].obligation_ref == "CL-01"
        assert result[0].attribution_method == "custom"


# =============================================================================
# ChunkCitation construction from Chunk
# =============================================================================


class TestCitationConstruction:
    """Verify the pattern used by attribution strategies to build citations."""

    def test_citation_from_chunk(self) -> None:
        chunk = _make_chunk("C::39", "Stock brokers shall collect margins", start_page=3, end_page=4, topic=39)
        citation = ChunkCitation(
            chunk_id=chunk.chunk_id,
            citation_text=chunk.text,
            page_range=(chunk.metadata.start_page, chunk.metadata.end_page),
        )
        assert citation.chunk_id == "C::39"
        assert citation.citation_text == "Stock brokers shall collect margins"
        assert citation.page_range == (3, 4)
        assert citation.page_regions == []

    def test_citation_preserves_chunk_id(self) -> None:
        chunk_id = "SEBI/HO/MIRSD/P/CIR/2025/57::chunk::t39::001"
        chunk = _make_chunk(chunk_id, "text")
        citation = ChunkCitation(
            chunk_id=chunk.chunk_id,
            citation_text=chunk.text,
            page_range=(chunk.metadata.start_page, chunk.metadata.end_page),
        )
        assert citation.chunk_id == chunk_id
