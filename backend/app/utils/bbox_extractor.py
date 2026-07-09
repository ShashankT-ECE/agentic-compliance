"""
Bounding-box extractor — V2 M3.

Extracts approximate page regions for chunk text within a source PDF
using pdfplumber's word-level position data.  Results are cached to disk
so extraction runs once per chunk during ingest.

Design:
  - pdfplumber (already a dependency) provides word-level bounding boxes.
  - Fuzzy text matching handles minor differences between the extracted
    chunk text and the PDF word stream (whitespace, ligatures).
  - Consecutive matched words are merged into a single ``Rectangle``.
  - Output is a list of ``PageRegion`` objects — one per page that
    contains matching text.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.models.evidence import PageRegion, Rectangle

logger = logging.getLogger(__name__)

# Default cache directory, relative to the backend root.
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "bbox"


# =============================================================================
# BoundingBoxExtractor
# =============================================================================


class BoundingBoxExtractor:
    """Extract page regions for chunk text within a PDF.

    Usage::

        extractor = BoundingBoxExtractor()
        regions = extractor.extract_for_chunk(
            pdf_path="data/circulars/circ.pdf",
            chunk_text="Stock brokers shall collect margins...",
            start_page=3,
            end_page=3,
        )
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_for_chunk(
        self,
        pdf_path: str | Path,
        chunk_text: str,
        start_page: int,
        end_page: int,
    ) -> list[PageRegion]:
        """Find the page regions containing *chunk_text* in the PDF.

        Args:
            pdf_path: Path to the source PDF.
            chunk_text: The chunk text to locate.
            start_page: First page to search (1-based, inclusive).
            end_page: Last page to search (1-based, inclusive).

        Returns:
            One ``PageRegion`` per page that contains matching text.
            Each region may have multiple rectangles if the text is
            split across non-contiguous blocks on the same page.
            Returns an empty list if the text cannot be located.
        """
        if not chunk_text.strip():
            return []

        import pdfplumber

        regions: list[PageRegion] = []

        try:
            with pdfplumber.open(Path(pdf_path)) as pdf:
                for page_num in range(start_page, end_page + 1):
                    if page_num < 1 or page_num > len(pdf.pages):
                        continue

                    page = pdf.pages[page_num - 1]  # pdfplumber is 0-indexed
                    words = page.extract_words(
                        keep_blank_chars=False,
                        use_text_flow=False,
                    )
                    if not words:
                        continue

                    rects = self._find_text_on_page(chunk_text, words)
                    if rects:
                        regions.append(PageRegion(
                            page_number=page_num,
                            rectangles=rects,
                        ))

        except Exception:
            logger.exception(
                "Bounding-box extraction failed for chunk on pages %d-%d of %s",
                start_page, end_page, pdf_path,
            )

        return regions

    def extract_batch(
        self,
        pdf_path: str | Path,
        chunks: list[tuple[str, int, int]],  # (text, start_page, end_page)
    ) -> list[list[PageRegion]]:
        """Extract regions for multiple chunks efficiently.

        Opens the PDF once and processes all chunks.

        Args:
            pdf_path: Path to the source PDF.
            chunks: List of (text, start_page, end_page) tuples.

        Returns:
            A list of region lists, parallel to *chunks*.
        """
        if not chunks:
            return []

        import pdfplumber

        # Pre-index all pages
        try:
            with pdfplumber.open(Path(pdf_path)) as pdf:
                total_pages = len(pdf.pages)
                page_words: dict[int, list[dict]] = {}

        except Exception:
            logger.exception("Failed to open PDF for batch extraction: %s", pdf_path)
            return [[] for _ in chunks]

        # Re-open for per-chunk processing (pdfplumber pages are not
        # reusable across context-manager boundaries).
        results: list[list[PageRegion]] = []
        try:
            with pdfplumber.open(Path(pdf_path)) as pdf:
                for text, sp, ep in chunks:
                    regions: list[PageRegion] = []
                    for pn in range(sp, ep + 1):
                        if pn < 1 or pn > total_pages:
                            continue
                        page = pdf.pages[pn - 1]
                        words = page.extract_words(
                            keep_blank_chars=False,
                            use_text_flow=False,
                        )
                        if not words:
                            continue
                        rects = self._find_text_on_page(text, words)
                        if rects:
                            regions.append(PageRegion(
                                page_number=pn,
                                rectangles=rects,
                            ))
                    results.append(regions)
        except Exception:
            logger.exception("Batch extraction failed for %s", pdf_path)
            results.extend([[] for _ in range(len(chunks) - len(results))])

        return results

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def load_or_extract(
        self,
        chunk_id: str,
        pdf_path: str | Path,
        chunk_text: str,
        start_page: int,
        end_page: int,
    ) -> list[PageRegion]:
        """Return cached regions for *chunk_id*, extracting if necessary.

        This is the primary entry point for the indexing pipeline: it
        checks the disk cache first and only extracts on a cache miss.
        """
        cache_path = self._cache_path(chunk_id)

        # Cache hit
        if cache_path.exists():
            try:
                return self._load_cache(cache_path)
            except Exception:
                logger.warning(
                    "Corrupt bbox cache for %s — re-extracting", chunk_id
                )

        # Cache miss — extract and store
        regions = self.extract_for_chunk(pdf_path, chunk_text, start_page, end_page)
        try:
            self._save_cache(cache_path, regions)
        except OSError:
            logger.warning("Failed to write bbox cache for %s", chunk_id)

        return regions

    # ------------------------------------------------------------------
    # Internal — text matching
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for fuzzy comparison.

        Lowercase, collapse whitespace, strip leading/trailing
        punctuation from each word.
        """
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        # Strip punctuation at word boundaries for comparison
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _find_text_on_page(
        self,
        chunk_text: str,
        words: list[dict],
    ) -> list[Rectangle]:
        """Find the positions of *chunk_text* within *words* on one page.

        Returns one or more rectangles covering the matched word sequences.
        """
        if not words:
            return []

        # Build a searchable word stream
        word_texts = [w.get("text", "") for w in words]

        # Split chunk_text into searchable phrases (by sentence/paragraph)
        phrases = self._split_into_phrases(chunk_text)

        rects: list[Rectangle] = []
        for phrase in phrases:
            phrase_rects = self._find_phrase(phrase, words, word_texts)
            rects.extend(phrase_rects)

        # Merge overlapping or adjacent rectangles
        return self._merge_rectangles(rects)

    def _split_into_phrases(self, text: str) -> list[str]:
        """Split chunk text into searchable phrases.

        Long chunks are split by paragraph or sentence boundaries.
        Short chunks are kept as one phrase.
        """
        text = text.strip()
        if not text:
            return []

        # Try paragraph splitting first
        paragraphs = re.split(r"\n\s*\n", text)
        if len(paragraphs) > 1:
            return [p.strip() for p in paragraphs if p.strip()]

        # If the chunk is short enough, keep as one phrase
        if len(text) < 2000:
            return [text]

        # For very long single-paragraph chunks, split by sentence
        sentences = re.split(r"(?<=[.!?])\s+", text)
        # Group sentences into ~500-char phrases
        result: list[str] = []
        current: list[str] = []
        current_len = 0
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if current and current_len + len(s) > 500:
                result.append(" ".join(current))
                current = [s]
                current_len = len(s)
            else:
                current.append(s)
                current_len += len(s)
        if current:
            result.append(" ".join(current))
        return result if result else [text]

    @staticmethod
    def _find_phrase(
        phrase: str,
        words: list[dict],
        word_texts: list[str],
    ) -> list[Rectangle]:
        """Find *phrase* within the word stream and return bounding rectangles.

        Uses a sliding window: find the longest consecutive word sequence
        whose normalized text starts with the normalized phrase.
        """
        norm_phrase = BoundingBoxExtractor._normalize(phrase)
        if not norm_phrase:
            return []

        # Build normalized word stream
        norm_words = [BoundingBoxExtractor._normalize(wt) for wt in word_texts]
        rects: list[Rectangle] = []

        # Sliding window: for each starting position, see how many
        # consecutive words match the phrase prefix.
        i = 0
        while i < len(words):
            best_len = 0
            best_end = i

            for end in range(i + 1, min(i + 50, len(words) + 1)):
                candidate = " ".join(norm_words[i:end])
                if norm_phrase.startswith(candidate):
                    best_len = end - i
                    best_end = end
                elif candidate and len(candidate) > len(norm_phrase):
                    break  # Past the phrase length — stop growing

            if best_len >= 2:  # Minimum 2 words to form a rectangle
                matched = words[i:best_end]
                x0 = min(w["x0"] for w in matched)
                y0 = min(w["top"] for w in matched)
                x1 = max(w["x1"] for w in matched)
                y1 = max(w["bottom"] for w in matched)
                rects.append(Rectangle(x0=x0, y0=y0, x1=x1, y1=y1))
                i = best_end
            else:
                i += 1

        return rects

    @staticmethod
    def _merge_rectangles(rects: list[Rectangle]) -> list[Rectangle]:
        """Merge overlapping or vertically adjacent rectangles.

        Two rectangles are merged if they overlap horizontally and are
        within a few lines of each other vertically (same paragraph).
        """
        if len(rects) <= 1:
            return rects

        # Sort by y0 (top to bottom)
        sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))
        merged: list[Rectangle] = []
        current = sorted_rects[0]

        for r in sorted_rects[1:]:
            # Check if r is close to current (within ~1.5 line heights)
            line_height = current.y1 - current.y0
            if line_height <= 0:
                line_height = 12  # default pt size

            # Horizontal overlap
            h_overlap = (
                min(current.x1, r.x1) - max(current.x0, r.x0) > 0
            )
            # Vertical proximity (within 1.5 lines)
            v_close = abs(r.y0 - current.y1) < line_height * 1.5

            if h_overlap and v_close:
                current = Rectangle(
                    x0=min(current.x0, r.x0),
                    y0=min(current.y0, r.y0),
                    x1=max(current.x1, r.x1),
                    y1=max(current.y1, r.y1),
                )
            else:
                merged.append(current)
                current = r

        merged.append(current)
        return merged

    # ------------------------------------------------------------------
    # Cache persistence
    # ------------------------------------------------------------------

    def _cache_path(self, chunk_id: str) -> Path:
        """Filesystem path for a chunk's cached bounding boxes."""
        # Sanitize chunk_id for use as a filename
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", chunk_id)
        return self._cache_dir / f"{safe}.json"

    @staticmethod
    def _load_cache(path: Path) -> list[PageRegion]:
        """Load cached PageRegions from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return [PageRegion.model_validate(r) for r in data]

    @staticmethod
    def _save_cache(path: Path, regions: list[PageRegion]) -> None:
        """Persist PageRegions to a JSON cache file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [r.model_dump(mode="json") for r in regions]
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
