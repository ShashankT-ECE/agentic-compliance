"""
Structure-aware chunker for SEBI regulatory PDFs — V2 M1.

Splits extracted PDF text into chunks at topic boundaries while preserving
document hierarchy metadata for citation and retrieval.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.rag.config import ChunkingConfig, RagConfig
from app.rag.schemas import Chunk, ChunkMetadata
from app.utils.pdf_ingest import extract_text_by_page

logger = logging.getLogger(__name__)

# =============================================================================
# Regex patterns
# =============================================================================

_RE_ROMAN = re.compile(r"^\s*([IVX]+)\.\s+([A-Z][A-Z\s/&,\\-]{5,})$")
_RE_TOPIC = re.compile(r"^\s*(\d{1,3})\.\s+([A-Z][A-Za-z\s/,()\-–\[\]\"\']{9,})$")
_RE_ANNEXURE = re.compile(r"^\s*(Annexure-\d+[A-Z]?)\s*[-–]?\s*(.*)$")
_RE_APPENDIX = re.compile(r"^\s*(Appendix-[A-Z])[-–]?\s*(.*)$")

_VALID_ROMAN = frozenset({"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"})


# =============================================================================
# Internal data structures
# =============================================================================

@dataclass
class _Topic:
    """A numbered topic detected in the document."""
    number: int
    title: str
    start_line: int
    end_line: int = 0
    roman_section: str = ""
    roman_title: str = ""


@dataclass
class _Section:
    """A Roman-numeral section containing topics."""
    number: str
    title: str
    start_line: int
    end_line: int = 0
    topics: list[_Topic] = field(default_factory=list)


# =============================================================================
# DocumentChunker
# =============================================================================

class DocumentChunker:
    """Split regulatory PDF text into semantically meaningful chunks.

    The chunking strategy:
      1. Detect Roman sections (I-X) and numbered topics (1-98).
      2. Each topic becomes one or more chunks (split by paragraph if too large).
      3. Topics smaller than min_chunk_size are merged with adjacent topics.
      4. Every chunk carries hierarchical metadata for citation.

    Usage::

        chunker = DocumentChunker(config)
        chunks = chunker.chunk_pdf("path/to/circular.pdf", "SEBI/HO/...")
    """

    def __init__(self, config: RagConfig | ChunkingConfig | None = None) -> None:
        if isinstance(config, RagConfig):
            self._cfg = config.chunking
        elif isinstance(config, ChunkingConfig):
            self._cfg = config
        else:
            self._cfg = ChunkingConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk_pdf(self, pdf_path: str, circular_ref: str) -> list[Chunk]:
        """Extract and chunk a PDF into structured Chunk objects."""
        pages = extract_text_by_page(pdf_path)
        return self.chunk_text("\n".join(pages), circular_ref)

    def chunk_text(self, text: str, circular_ref: str) -> list[Chunk]:
        """Chunk pre-extracted regulatory text."""
        if not text.strip():
            return []

        lines = text.split("\n")
        sections = self._detect_structure(lines)

        if not sections:
            # No structure detected — treat as one flat section
            return self._flat_chunk(text, circular_ref)

        return self._sections_to_chunks(sections, lines, circular_ref)

    # ------------------------------------------------------------------
    # Structure detection
    # ------------------------------------------------------------------

    def _detect_structure(self, lines: list[str]) -> list[_Section]:
        """Detect Roman sections and numbered topics from lines.

        Returns a list of _Section objects, each containing _Topic children.
        If no Roman sections are found, returns an empty list.
        """
        sections: list[_Section] = []
        current_section: _Section | None = None
        current_topic: _Topic | None = None
        roman_seen = False

        for i, raw_line in enumerate(lines):
            line = raw_line.strip()

            # Roman section detection
            rm = _RE_ROMAN.match(line)
            if rm and rm.group(1) in _VALID_ROMAN:
                num, title = rm.group(1), rm.group(2).strip()
                # Close previous section
                if current_section is not None:
                    if current_topic is not None:
                        current_topic.end_line = i
                        current_section.topics.append(current_topic)
                        current_topic = None
                    current_section.end_line = i

                current_section = _Section(number=num, title=title, start_line=i)
                sections.append(current_section)
                roman_seen = True
                current_topic = None
                continue

            if not roman_seen:
                continue

            # Topic detection
            tm = _RE_TOPIC.match(line)
            if tm:
                topic_num = int(tm.group(1))
                if 1 <= topic_num <= 200 and current_section is not None:
                    if current_topic is not None:
                        current_topic.end_line = i
                        current_section.topics.append(current_topic)
                    current_topic = _Topic(
                        number=topic_num,
                        title=tm.group(2).strip(),
                        start_line=i,
                        roman_section=current_section.number,
                        roman_title=current_section.title,
                    )
                continue

            # Annexure / Appendix as pseudo-topics
            am = _RE_ANNEXURE.match(line)
            if not am:
                am = _RE_APPENDIX.match(line)
            if am and current_section is not None:
                if current_topic is not None:
                    current_topic.end_line = i
                    current_section.topics.append(current_topic)
                # Use a high topic number for annexures
                current_topic = _Topic(
                    number=1000 + len(current_section.topics),
                    title=f"{am.group(1)} {am.group(2).strip()}",
                    start_line=i,
                    roman_section=current_section.number,
                    roman_title=current_section.title,
                )

        # Close final topic and section
        if current_section is not None:
            if current_topic is not None:
                current_topic.end_line = len(lines)
                current_section.topics.append(current_topic)
            current_section.end_line = len(lines)

        return sections

    # ------------------------------------------------------------------
    # Topic extraction
    # ------------------------------------------------------------------

    def _get_topic_text(self, topic: _Topic, lines: list[str]) -> str:
        """Extract the full text for a topic from the line array.

        Includes the topic header line and all text up to the next topic
        or section boundary.
        """
        end = topic.end_line if topic.end_line else len(lines)
        text_lines = lines[topic.start_line:end]
        return "\n".join(text_lines).strip()

    # ------------------------------------------------------------------
    # Chunk production
    # ------------------------------------------------------------------

    def _sections_to_chunks(
        self, sections: list[_Section], lines: list[str], circular_ref: str
    ) -> list[Chunk]:
        """Convert detected sections and topics into Chunk objects."""
        all_blocks: list[tuple[str, _Topic]] = []

        for section in sections:
            for topic in section.topics:
                text = self._get_topic_text(topic, lines)
                if text:
                    all_blocks.append((text, topic))

        if not all_blocks:
            return []

        # Split large blocks, merge small blocks
        chunks = self._apply_size_constraints(all_blocks, circular_ref)
        return chunks

    def _apply_size_constraints(
        self, blocks: list[tuple[str, _Topic]], circular_ref: str
    ) -> list[Chunk]:
        """Apply min/max chunk size constraints to topic text blocks."""
        # Step 1: Split oversized blocks at paragraph boundaries
        expanded: list[tuple[str, _Topic]] = []
        for text, topic in blocks:
            parts = self._size_split(text)
            for part in parts:
                expanded.append((part, topic))

        # Step 2: Merge undersized blocks with neighbors in the same section.
        # Never merge across Roman section boundaries — that would lose
        # section metadata and produce misleading citation paths.
        merged: list[tuple[str, _Topic]] = []
        for text, topic in expanded:
            can_merge = (
                merged
                and len(text) < self._cfg.min_chunk_size
                and merged[-1][1].roman_section == topic.roman_section
                and len(merged[-1][0]) + len(text) <= self._cfg.max_chunk_size
            )
            if can_merge:
                prev_text, prev_topic = merged[-1]
                merged[-1] = (prev_text + "\n\n" + text, prev_topic)
            else:
                merged.append((text, topic))

        # Step 3: Convert to Chunk objects with metadata
        chunks: list[Chunk] = []
        # Count chunks per topic for indexing
        topic_counts: dict[int, int] = {}
        topic_indices: dict[int, int] = {}
        for _, topic in merged:
            topic_counts[topic.number] = topic_counts.get(topic.number, 0) + 1

        for text, topic in merged:
            idx = topic_indices.get(topic.number, 0)
            total = topic_counts[topic.number]
            meta = ChunkMetadata(
                circular_ref=circular_ref,
                section_path=self._build_section_path(topic),
                roman_section=topic.roman_section or None,
                roman_title=topic.roman_title or None,
                topic_number=topic.number,
                topic_title=topic.title or None,
                chunk_index=idx,
                chunk_total=total,
                char_count=len(text),
            )
            chunk_id = (
                f"{circular_ref}::chunk::t{topic.number}::{idx:03d}"
            )
            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=text,
                metadata=meta,
            ))
            topic_indices[topic.number] = idx + 1

        logger.info(
            "Chunked '%s': %d chunks from %d topics",
            circular_ref,
            len(chunks),
            len(topic_counts),
        )
        return chunks

    def _build_section_path(self, topic: _Topic) -> str:
        """Build a hierarchical section path like 'III.39'."""
        if topic.roman_section:
            return f"{topic.roman_section}.{topic.number}"
        return str(topic.number)

    def _size_split(self, text: str) -> list[str]:
        """Split text into chunks respecting size constraints."""
        if len(text) <= self._cfg.max_chunk_size:
            return [text]

        paragraphs = re.split(r"\n\s*\n", text)
        result: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            pl = len(para)
            if current and (current_len + pl > self._cfg.max_chunk_size):
                result.append("\n\n".join(current))
                current = [para]
                current_len = pl
            else:
                current.append(para)
                current_len += pl

        if current:
            result.append("\n\n".join(current))

        return result if result else [text]

    def _flat_chunk(self, text: str, circular_ref: str) -> list[Chunk]:
        """Create chunks from unstructured text (no section/topic headers detected)."""
        result = self._size_split(text)
        chunks: list[Chunk] = []
        for i, t in enumerate(result):
            meta = ChunkMetadata(
                circular_ref=circular_ref,
                section_path="__root__",
                chunk_index=i,
                chunk_total=len(result),
                char_count=len(t),
            )
            chunk_id = f"{circular_ref}::chunk::flat::{i:05d}"
            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=t,
                metadata=meta,
            ))
        return chunks
