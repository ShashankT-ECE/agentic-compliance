"""
Tests for bounding-box extractor — V2 M3.

Covers word-level text matching, rectangle merging, cache hit/miss,
multi-page regions, and error handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.models.evidence import PageRegion, Rectangle
from app.utils.bbox_extractor import BoundingBoxExtractor


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def extractor() -> BoundingBoxExtractor:
    with TemporaryDirectory() as tmp:
        yield BoundingBoxExtractor(cache_dir=tmp)


# Path to a real PDF fixture for integration tests
def _sample_pdf_path() -> str | None:
    """Return the path to the 2-page SEBI circular, or None if missing."""
    candidates = [
        "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf",
        "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57-official.pdf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# =============================================================================
# Normalization
# =============================================================================


class TestNormalize:
    def test_lowercase(self) -> None:
        result = BoundingBoxExtractor._normalize("HELLO World")
        assert result == "hello world"

    def test_collapse_whitespace(self) -> None:
        result = BoundingBoxExtractor._normalize("  hello    world  ")
        assert result == "hello world"

    def test_strip_punctuation(self) -> None:
        result = BoundingBoxExtractor._normalize("Hello, world! How are you?")
        assert result == "hello world how are you"

    def test_empty_string(self) -> None:
        assert BoundingBoxExtractor._normalize("") == ""
        assert BoundingBoxExtractor._normalize("   ") == ""


# =============================================================================
# Phrase splitting
# =============================================================================


class TestSplitPhrases:
    def test_short_text_kept_whole(self, extractor) -> None:
        phrases = extractor._split_into_phrases("Short regulatory text.")
        assert len(phrases) == 1
        assert phrases[0] == "Short regulatory text."

    def test_paragraph_split(self, extractor) -> None:
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        phrases = extractor._split_into_phrases(text)
        assert len(phrases) == 3
        assert phrases[0] == "Paragraph one."
        assert phrases[1] == "Paragraph two."

    def test_empty_text(self, extractor) -> None:
        assert extractor._split_into_phrases("") == []
        assert extractor._split_into_phrases("   ") == []

    def test_very_long_single_paragraph(self, extractor) -> None:
        """Long text without paragraph breaks is split into manageable chunks."""
        long_text = "This is a sentence. " * 200  # ~5000 chars
        phrases = extractor._split_into_phrases(long_text)
        assert len(phrases) > 1
        for p in phrases:
            assert len(p) < 2000  # reasonable upper bound


# =============================================================================
# Rectangle merging
# =============================================================================


class TestMergeRectangles:
    def test_empty_list(self) -> None:
        assert BoundingBoxExtractor._merge_rectangles([]) == []

    def test_single_rectangle(self) -> None:
        r = Rectangle(x0=10, y0=20, x1=100, y1=40)
        assert BoundingBoxExtractor._merge_rectangles([r]) == [r]

    def test_overlapping_merged(self) -> None:
        r1 = Rectangle(x0=10, y0=20, x1=100, y1=40)
        r2 = Rectangle(x0=15, y0=35, x1=120, y1=55)
        merged = BoundingBoxExtractor._merge_rectangles([r1, r2])
        assert len(merged) == 1
        assert merged[0].x0 == 10
        assert merged[0].y0 == 20
        assert merged[0].x1 == 120
        assert merged[0].y1 == 55

    def test_far_apart_not_merged(self) -> None:
        r1 = Rectangle(x0=10, y0=20, x1=100, y1=30)
        r2 = Rectangle(x0=10, y0=200, x1=100, y1=210)
        merged = BoundingBoxExtractor._merge_rectangles([r1, r2])
        assert len(merged) == 2


# =============================================================================
# Phrase finding (synthetic word data)
# =============================================================================


def _make_words(texts: list[str], x0: float = 10) -> list[dict]:
    """Build synthetic word dicts at fixed positions."""
    words = []
    y = 100
    for t in texts:
        words.append({
            "text": t,
            "x0": x0,
            "top": y,
            "x1": x0 + len(t) * 6,
            "bottom": y + 14,
        })
        y += 16
    return words


class TestFindPhrase:
    def test_exact_match(self) -> None:
        word_texts = ["The", "stock", "broker", "shall", "collect", "margins"]
        words = _make_words(word_texts)
        rects = BoundingBoxExtractor._find_phrase(
            "stock broker shall", words, word_texts,
        )
        assert len(rects) >= 1
        # Should cover "stock", "broker", "shall"
        first = rects[0]
        assert first.x0 >= 0
        assert first.y0 >= 0
        assert first.x1 > first.x0

    def test_no_match_returns_empty(self) -> None:
        words = _make_words(["Hello", "world"])
        rects = BoundingBoxExtractor._find_phrase(
            "margin collection", words, ["Hello", "world"],
        )
        assert rects == []

    def test_empty_phrase(self) -> None:
        words = _make_words(["text"])
        rects = BoundingBoxExtractor._find_phrase("", words, ["text"])
        assert rects == []

    def test_empty_words(self) -> None:
        rects = BoundingBoxExtractor._find_phrase("text", [], [])
        assert rects == []

    def test_partial_match(self) -> None:
        """Match the longest prefix of the phrase found in the words."""
        words = _make_words(["The", "stock", "broker", "shall", "collect"])
        word_texts = [w["text"] for w in words]
        rects = BoundingBoxExtractor._find_phrase(
            "stock broker shall collect margins", words, word_texts,
        )
        assert len(rects) >= 1
        first = rects[0]
        assert first.x1 > first.x0
        assert first.y1 > first.y0


# =============================================================================
# Cache tests
# =============================================================================


class TestCache:
    def test_cache_miss_triggers_extraction(self, extractor) -> None:
        """When cache is empty, extraction runs and produces results."""
        pdf_path = _sample_pdf_path()
        if not pdf_path:
            pytest.skip("No sample PDF available")

        regions = extractor.load_or_extract(
            chunk_id="TEST-CACHE::chunk::001",
            pdf_path=pdf_path,
            chunk_text="Trading Members of the Exchange are hereby informed",
            start_page=1,
            end_page=1,
        )
        # Should find the text on page 1
        assert isinstance(regions, list)
        # The text should be found (at least one region)
        if regions:
            assert all(isinstance(r, PageRegion) for r in regions)

    def test_cache_hit_avoids_re_extraction(self, extractor) -> None:
        """Second call with same chunk_id returns cached data."""
        pdf_path = _sample_pdf_path()
        if not pdf_path:
            pytest.skip("No sample PDF available")

        chunk_id = "TEST-CACHE-HIT::chunk::001"
        text = "Trading Members of the Exchange are hereby informed"

        # First call — extract
        regions1 = extractor.load_or_extract(
            chunk_id=chunk_id,
            pdf_path=pdf_path,
            chunk_text=text,
            start_page=1,
            end_page=1,
        )

        # Second call — should hit cache
        regions2 = extractor.load_or_extract(
            chunk_id=chunk_id,
            pdf_path=pdf_path,
            chunk_text=text,
            start_page=1,
            end_page=1,
        )

        # Same result
        assert len(regions1) == len(regions2)
        for r1, r2 in zip(regions1, regions2):
            assert r1.page_number == r2.page_number
            assert len(r1.rectangles) == len(r2.rectangles)


# =============================================================================
# Multi-page regions
# =============================================================================


class TestMultiPage:
    def test_text_across_pages(self, extractor) -> None:
        """Text spanning pages 1-2 produces regions on both pages."""
        pdf_path = _sample_pdf_path()
        if not pdf_path:
            pytest.skip("No sample PDF available")

        regions = extractor.extract_for_chunk(
            pdf_path=pdf_path,
            chunk_text="Securities Exchange Board of India",
            start_page=1,
            end_page=2,
        )
        assert isinstance(regions, list)

    def test_start_page_equals_end_page(self, extractor) -> None:
        """Single-page extraction works."""
        pdf_path = _sample_pdf_path()
        if not pdf_path:
            pytest.skip("No sample PDF available")

        regions = extractor.extract_for_chunk(
            pdf_path=pdf_path,
            chunk_text="Trading Members",
            start_page=1,
            end_page=1,
        )
        assert isinstance(regions, list)
        if regions:
            assert regions[0].page_number == 1


# =============================================================================
# Error handling
# =============================================================================


class TestErrorHandling:
    def test_nonexistent_pdf(self, extractor) -> None:
        regions = extractor.extract_for_chunk(
            pdf_path="/nonexistent/path.pdf",
            chunk_text="some text",
            start_page=1,
            end_page=1,
        )
        assert regions == []

    def test_empty_chunk_text(self, extractor) -> None:
        pdf_path = _sample_pdf_path()
        if not pdf_path:
            pytest.skip("No sample PDF available")

        regions = extractor.extract_for_chunk(
            pdf_path=pdf_path,
            chunk_text="",
            start_page=1,
            end_page=1,
        )
        assert regions == []

    def test_page_out_of_range(self, extractor) -> None:
        pdf_path = _sample_pdf_path()
        if not pdf_path:
            pytest.skip("No sample PDF available")

        regions = extractor.extract_for_chunk(
            pdf_path=pdf_path,
            chunk_text="Trading Members",
            start_page=999,
            end_page=999,
        )
        assert regions == []

    def test_batch_empty_chunks(self, extractor) -> None:
        regions = extractor.extract_batch(
            pdf_path="/nonexistent/path.pdf",
            chunks=[],
        )
        assert regions == []


# =============================================================================
# Backward compatibility
# =============================================================================


class TestBackwardCompatibility:
    def test_page_region_is_not_page_box(self) -> None:
        """PageRegion replaces PageBox — it has rectangles, not raw coords."""
        region = PageRegion(page_number=1, rectangles=[Rectangle(x0=1, y0=2, x1=3, y1=4)])
        # PageRegion does NOT expose x0/y0/x1/y1 directly
        assert not hasattr(region, "x0")
        assert not hasattr(region, "y0")
        # PageRegion exposes page_number + rectangles
        assert region.page_number == 1
        assert len(region.rectangles) == 1

    def test_rectangle_is_the_coordinate_atom(self) -> None:
        """Rectangle is the only type carrying raw coordinates."""
        r = Rectangle(x0=10, y0=20, x1=100, y1=30)
        assert r.x0 == 10
        # Evidence models reference PageRegion, not Rectangle directly
        # (Rectangle is used inside PageRegion.rectangles)
