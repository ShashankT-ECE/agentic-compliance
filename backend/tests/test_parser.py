"""
Tests for Node 1 — Circular Parser (PDF extraction + obligation parsing).

Covers:
  - PDF text extraction (pdf_ingest): valid PDFs, multi-page, errors
  - Prompt template loading
  - LLM response JSON extraction
  - Clause dict parsing and Pydantic validation
  - parse_circular() with MockLLMClient
  - Edge cases: empty text, malformed LLM output, validation failures
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.pipeline.nodes.parser import (
    _extract_json_from_response,
    _parse_clause_dict,
    load_prompt_template,
    parse_circular,
)
from app.utils.llm_client import LLMClientError, MockLLMClient
from app.utils.pdf_ingest import PdfIngestError, extract_text, extract_text_by_page


# ====================================================================
# Helpers — Minimal valid PDF generation
# ====================================================================


def _make_minimal_pdf(text: str = "Test Circular Text") -> bytes:
    """Create a minimal valid one-page PDF containing the given text.

    Constructs a syntactically valid PDF 1.4 document with a single page
    containing the provided text in Helvetica at 18pt.  The cross-reference
    table is built with exact byte offsets so strict parsers can read it.

    Args:
        text: The text string to embed in the PDF page content stream.

    Returns:
        Raw PDF bytes suitable for writing to a ``.pdf`` file.
    """
    # Escape parentheses and backslashes in the text for PDF literal strings
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Build objects
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"

    font_res = b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"

    stream_content = (
        f"BT /F1 18 Tf 72 720 Td ({safe_text}) Tj ET"
    ).encode("latin-1", errors="replace")
    stream_obj_body = (
        b"<< /Length %d >>\nstream\n" % len(stream_content)
        + stream_content
        + b"\nendstream\nendobj\n"
    )

    page_obj = (
        b"4 0 obj\n<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R "
        b"/Resources << /Font << /F1 3 0 R >> >> >>\nendobj\n"
    )
    stream_obj = b"5 0 obj\n" + stream_obj_body

    # Assemble objects and track offsets
    objects = [obj1, obj2, font_res, page_obj, stream_obj]
    body_parts: list[bytes] = []
    offsets: dict[int, int] = {}

    for i, obj in enumerate(objects, start=1):
        offsets[i] = len(b"".join(body_parts))
        body_parts.append(obj)

    body = b"".join(body_parts)

    # Cross-reference table
    xref_lines: list[bytes] = [
        b"xref",
        f"0 {len(objects) + 1}".encode(),
        b"0000000000 65535 f ",
    ]
    for i in range(1, len(objects) + 1):
        xref_lines.append(f"{offsets[i]:010d} 00000 n ".encode())

    xref = b"\n".join(xref_lines) + b"\n"

    trailer = (
        b"trailer\n"
        + f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
        + b"startxref\n"
        + f"{len(body)}".encode()
        + b"\n%%EOF\n"
    )

    return b"%PDF-1.4\n" + body + xref + trailer


def _make_temp_pdf(text: str = "Test Circular Text") -> str:
    """Write a minimal PDF to a temporary file and return its path.

    The caller is responsible for deleting the file after use.
    """
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="test_circular_")
    os.close(fd)
    Path(path).write_bytes(_make_minimal_pdf(text))
    return path


# ====================================================================
# PDF Extraction tests
# ====================================================================


class TestPdfExtraction:
    """Tests for pdf_ingest: extract_text and extract_text_by_page."""

    def test_extract_text_single_page(self):
        path = _make_temp_pdf("SEBI Circular: Margin Requirements")
        try:
            result = extract_text(path)
            assert "Margin Requirements" in result
        finally:
            os.unlink(path)

    def test_extract_text_multi_page(self):
        """Multi-page PDF concatenates text from all pages."""
        # Build a 2-page PDF
        page1 = (
            b"4 0 obj\n<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] /Contents 6 0 R "
            b"/Resources << /Font << /F1 3 0 R >> >> >>\nendobj\n"
        )
        page2 = (
            b"5 0 obj\n<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] /Contents 7 0 R "
            b"/Resources << /Font << /F1 3 0 R >> >> >>\nendobj\n"
        )

        def _stream_obj(obj_num: int, text: str) -> bytes:
            safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content = f"BT /F1 18 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1", errors="replace")
            return (
                f"{obj_num} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode()
                + content
                + b"\nendstream\nendobj\n"
            )

        catalog = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        pages = b"2 0 obj\n<< /Type /Pages /Kids [4 0 R 5 0 R] /Count 2 >>\nendobj\n"
        font = b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"

        objects = [catalog, pages, font, page1, page2,
                   _stream_obj(6, "First Page Obligation"),
                   _stream_obj(7, "Second Page Obligation")]

        offsets: dict[int, int] = {}
        body_parts: list[bytes] = []
        for i, obj in enumerate(objects, start=1):
            offsets[i] = len(b"".join(body_parts))
            body_parts.append(obj)
        body = b"".join(body_parts)

        xref_lines = [b"xref", f"0 {len(objects) + 1}".encode(),
                      b"0000000000 65535 f "]
        for i in range(1, len(objects) + 1):
            xref_lines.append(f"{offsets[i]:010d} 00000 n ".encode())
        xref = b"\n".join(xref_lines) + b"\n"

        trailer = (
            b"trailer\n"
            + f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
            + b"startxref\n"
            + f"{len(body)}".encode()
            + b"\n%%EOF\n"
        )

        pdf_bytes = b"%PDF-1.4\n" + body + xref + trailer

        fd, path = tempfile.mkstemp(suffix=".pdf", prefix="test_multi_")
        os.close(fd)
        try:
            Path(path).write_bytes(pdf_bytes)
            result = extract_text(path)
            assert "First Page Obligation" in result
            assert "Second Page Obligation" in result
        finally:
            os.unlink(path)

    def test_extract_text_by_page(self):
        path = _make_temp_pdf("Page One")
        try:
            pages = extract_text_by_page(path)
            assert isinstance(pages, list)
            assert len(pages) >= 1
            assert any("Page One" in p for p in pages)
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_text("/nonexistent/path/circular.pdf")

    def test_file_not_found_by_page(self):
        with pytest.raises(FileNotFoundError):
            extract_text_by_page("/nonexistent/path/circular.pdf")

    def test_non_pdf_file(self):
        """A non-PDF file should raise PdfIngestError."""
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="not_a_pdf_")
        os.close(fd)
        try:
            Path(path).write_text("This is not a PDF file.")
            with pytest.raises(PdfIngestError):
                extract_text(path)
        finally:
            os.unlink(path)


# ====================================================================
# Prompt template tests
# ====================================================================


class TestPromptLoading:
    """Tests for load_prompt_template."""

    def test_load_default_prompt(self):
        template = load_prompt_template()
        assert len(template) > 100
        assert "regulatory compliance parser" in template.lower()
        assert "JSON" in template

    def test_load_nonexistent_prompt(self):
        with pytest.raises(FileNotFoundError, match="Parser prompt template not found"):
            load_prompt_template("/nonexistent/path/prompt.md")


# ====================================================================
# JSON extraction tests
# ====================================================================


class TestJsonExtraction:
    """Tests for _extract_json_from_response — LLM output parsing."""

    def test_pure_json_array(self):
        response = '[{"clause_id": "C-01", "clause_text": "Test obligation text here."}]'
        result = _extract_json_from_response(response)
        assert len(result) == 1
        assert result[0]["clause_id"] == "C-01"

    def test_markdown_fenced_json(self):
        response = """Here are the extracted obligations:

```json
[
  {"clause_id": "C-01", "clause_text": "Test obligation text here."},
  {"clause_id": "C-02", "clause_text": "Another obligation text here."}
]
```

These were extracted from the circular."""
        result = _extract_json_from_response(response)
        assert len(result) == 2
        assert result[0]["clause_id"] == "C-01"
        assert result[1]["clause_id"] == "C-02"

    def test_markdown_fence_without_json_tag(self):
        response = """```
[
  {"clause_id": "C-01", "clause_text": "Test obligation text here."}
]
```"""
        result = _extract_json_from_response(response)
        assert len(result) == 1

    def test_json_buried_in_text(self):
        response = """I found the following obligations:
[{"clause_id": "C-01", "clause_text": "Test obligation text here."}]
This completes the extraction."""
        result = _extract_json_from_response(response)
        assert len(result) == 1

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Could not extract a valid JSON array"):
            _extract_json_from_response("This is not JSON at all. No array here.")

    def test_empty_json_response(self):
        with pytest.raises(ValueError, match="Could not extract a valid JSON array"):
            _extract_json_from_response("")

    def test_single_json_object_wrapped_in_list(self):
        """A single JSON object (not array) should be wrapped in a list."""
        result = _extract_json_from_response('{"clause_id": "C-01", "clause_text": "Test obligation text here."}')
        assert len(result) == 1
        assert result[0]["clause_id"] == "C-01"


# ====================================================================
# Clause parsing tests
# ====================================================================


class TestClauseDictParsing:
    """Tests for _parse_clause_dict — dict-to-ObligationClause validation."""

    CIRCULAR_REF = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"

    def test_valid_timeline_clause(self):
        """Clause text from circular para 3: collect margins by settlement day."""
        data = {
            "clause_id": "CIRC-2025-057-CL-01",
            "circular_ref": self.CIRCULAR_REF,
            "clause_text": "The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
            "obligation_type": "timeline",
            "timeline_params": {"offset": 1, "grace_period": 0, "unit": "days"},
            "effective_date": None,
            "applicable_entities": ["trading_member", "clearing_member"],
        }
        clause = _parse_clause_dict(data, self.CIRCULAR_REF)
        assert isinstance(clause, ObligationClause)
        assert clause.obligation_type == ObligationType.TIMELINE
        assert clause.timeline_params is not None
        assert clause.timeline_params.offset == 1

    def test_valid_threshold_clause(self):
        """Threshold-type parsing: structurally valid data — the parser must handle threshold types."""
        data = {
            "clause_id": "CIRC-2025-057-CL-05",
            "clause_text": "Trading Members shall maintain adequate net worth as prescribed under SEBI regulations.",
            "obligation_type": "threshold",
            "timeline_params": None,
            "effective_date": None,
            "applicable_entities": ["trading_member"],
        }
        clause = _parse_clause_dict(data, self.CIRCULAR_REF)
        assert clause.obligation_type == ObligationType.THRESHOLD
        assert clause.timeline_params is None
        assert clause.circular_ref == self.CIRCULAR_REF

    def test_missing_circular_ref_filled_from_param(self):
        """Clause text from circular para 6.1: amend bye-laws."""
        data = {
            "clause_id": "CIRC-2025-057-CL-03",
            "clause_text": "The recognized Stock Exchanges and Clearing Corporations shall make necessary amendments to the relevant bye-laws, rules and regulations for the implementation of the above decision.",
            "obligation_type": "procedure",
            "timeline_params": None,
            "effective_date": None,
            "applicable_entities": ["recognized_stock_exchange", "clearing_corporation"],
        }
        clause = _parse_clause_dict(data, self.CIRCULAR_REF)
        assert clause.circular_ref == self.CIRCULAR_REF

    def test_obligation_type_normalisation(self):
        """Type strings should be normalised to enum values."""
        data = {
            "clause_id": "CIRC-2025-057-CL-02",
            "clause_text": "The TMs/CMs in cash segment are required to mandatorily collect upfront VaR margins and ELM from their clients in advance of trade.",
            "obligation_type": "TIMELINE",  # uppercase
            "timeline_params": {"offset": 0, "grace_period": 0, "unit": "days"},
            "effective_date": None,
            "applicable_entities": ["trading_member", "clearing_member"],
        }
        clause = _parse_clause_dict(data, self.CIRCULAR_REF)
        assert clause.obligation_type == ObligationType.TIMELINE

    def test_timeline_without_params_raises(self):
        """Timeline obligation must have timeline_params."""
        data = {
            "clause_id": "CIRC-2025-057-CL-06",
            "clause_text": "The TMs/CMs shall collect margins from their clients by the settlement day.",
            "obligation_type": "timeline",
            "timeline_params": None,
            "effective_date": None,
            "applicable_entities": ["trading_member"],
        }
        with pytest.raises(ValueError):
            _parse_clause_dict(data, self.CIRCULAR_REF)

    def test_invalid_clause_id_pattern(self):
        """Clause IDs must match the required pattern."""
        data = {
            "clause_id": "clause with spaces",
            "clause_text": "The TMs/CMs shall collect margins from their clients by the settlement day.",
            "obligation_type": "threshold",
            "timeline_params": None,
            "effective_date": None,
            "applicable_entities": ["trading_member"],
        }
        with pytest.raises(ValueError):
            _parse_clause_dict(data, self.CIRCULAR_REF)

    def test_effective_date_parsed(self):
        """Effective date from the circular: April 28, 2025 (date of issuance)."""
        data = {
            "clause_id": "CIRC-2025-057-CL-04",
            "clause_text": "The recognized Stock Exchanges and Clearing Corporations shall bring the provisions of this circular to the notice of the market participants and disseminate the same on their website.",
            "obligation_type": "procedure",
            "timeline_params": None,
            "effective_date": "2025-04-28",
            "applicable_entities": ["recognized_stock_exchange", "clearing_corporation"],
        }
        clause = _parse_clause_dict(data, self.CIRCULAR_REF)
        assert clause.effective_date == date(2025, 4, 28)


# ====================================================================
# parse_circular integration tests (with MockLLMClient)
# ====================================================================


# Sample LLM response matching the real SEBI circular in the fixture.
# Circular: SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57 dated April 28, 2025
# Subject: Timelines for collection of Margins other than Upfront Margins
# Each obligation is directly traceable to a specific sentence in the source text.
SAMPLE_LLM_RESPONSE = json.dumps([
    {
        "clause_id": "CIRC-2025-057-CL-01",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        "clause_text": "The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
        "obligation_type": "timeline",
        "timeline_params": {"offset": 1, "grace_period": 0, "unit": "days"},
        "effective_date": "2025-04-28",
        "applicable_entities": ["trading_member", "clearing_member"],
    },
    {
        "clause_id": "CIRC-2025-057-CL-02",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        "clause_text": "The TMs/CMs in cash segment are required to mandatorily collect upfront VaR margins and ELM from their clients in advance of trade.",
        "obligation_type": "timeline",
        "timeline_params": {"offset": 0, "grace_period": 0, "unit": "days"},
        "effective_date": "2025-04-28",
        "applicable_entities": ["trading_member", "clearing_member"],
    },
    {
        "clause_id": "CIRC-2025-057-CL-03",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        "clause_text": "The recognized Stock Exchanges and Clearing Corporations shall make necessary amendments to the relevant bye-laws, rules and regulations for the implementation of the above decision.",
        "obligation_type": "procedure",
        "timeline_params": None,
        "effective_date": "2025-04-28",
        "applicable_entities": ["recognized_stock_exchange", "clearing_corporation"],
    },
    {
        "clause_id": "CIRC-2025-057-CL-04",
        "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
        "clause_text": "The recognized Stock Exchanges and Clearing Corporations shall bring the provisions of this circular to the notice of the market participants and disseminate the same on their website.",
        "obligation_type": "procedure",
        "timeline_params": None,
        "effective_date": "2025-04-28",
        "applicable_entities": ["recognized_stock_exchange", "clearing_corporation"],
    },
])


class TestParseCircular:
    """Integration tests for parse_circular with MockLLMClient."""

    CIRCULAR_REF = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"

    @pytest.fixture
    def circular_text(self) -> str:
        """Load the test fixture text."""
        fixture_path = Path(__file__).parent / "fixtures" / "circular_slice.txt"
        return fixture_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_successful_parsing(self, circular_text):
        """Full parse with a realistic LLM response matching the real SEBI circular."""
        client = MockLLMClient(response=SAMPLE_LLM_RESPONSE)
        clauses = await parse_circular(circular_text, self.CIRCULAR_REF, client)

        assert len(clauses) == 4

        # Clause 1: timeline — collect margins by settlement day (T+1)
        assert clauses[0].obligation_type == ObligationType.TIMELINE
        assert clauses[0].timeline_params.offset == 1
        assert clauses[0].clause_id == "CIRC-2025-057-CL-01"
        assert "settlement day" in clauses[0].clause_text

        # Clause 2: timeline — collect VaR margins and ELM in advance of trade
        assert clauses[1].obligation_type == ObligationType.TIMELINE
        assert clauses[1].timeline_params.offset == 0
        assert clauses[1].clause_id == "CIRC-2025-057-CL-02"
        assert "advance of trade" in clauses[1].clause_text

        # Clause 3: procedure — amend bye-laws
        assert clauses[2].obligation_type == ObligationType.PROCEDURE
        assert clauses[2].timeline_params is None
        assert clauses[2].clause_id == "CIRC-2025-057-CL-03"
        assert "bye-laws" in clauses[2].clause_text

        # Clause 4: procedure — disseminate to market participants
        assert clauses[3].obligation_type == ObligationType.PROCEDURE
        assert clauses[3].timeline_params is None
        assert clauses[3].clause_id == "CIRC-2025-057-CL-04"

        # All clauses should have valid IDs, circular_ref, and effective_date
        for c in clauses:
            assert c.circular_ref == self.CIRCULAR_REF
            assert c.clause_id.startswith("CIRC-")
            assert len(c.clause_text) >= 10
            assert c.effective_date == date(2025, 4, 28)

    @pytest.mark.asyncio
    async def test_empty_text_raises(self):
        client = MockLLMClient()
        with pytest.raises(ValueError, match="raw_text is empty"):
            await parse_circular("", self.CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_whitespace_only_text_raises(self):
        client = MockLLMClient()
        with pytest.raises(ValueError, match="raw_text is empty"):
            await parse_circular("   \n  \t  ", self.CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_llm_returns_empty_array(self):
        client = MockLLMClient(response="[]")
        with pytest.raises(ValueError, match="No obligation clauses extracted"):
            await parse_circular(
                "Some text that should produce obligations but LLM returned empty.",
                self.CIRCULAR_REF,
                client,
            )

    @pytest.mark.asyncio
    async def test_llm_returns_invalid_json(self):
        client = MockLLMClient(response="this is not json")
        with pytest.raises(ValueError, match="Could not extract a valid JSON array"):
            await parse_circular("Valid circular text here, at least ten characters long.", self.CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_llm_returns_partial_valid_clauses(self):
        """Some clauses valid, some invalid — valid ones survive."""
        mixed_response = json.dumps([
            {
                "clause_id": "CIRC-2025-057-CL-01",
                "clause_text": "The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
                "obligation_type": "timeline",
                "timeline_params": {"offset": 1, "grace_period": 0, "unit": "days"},
                "effective_date": "2025-04-28",
                "applicable_entities": ["trading_member", "clearing_member"],
            },
            {
                "clause_id": "bad id with spaces",
                "clause_text": "Short",
                "obligation_type": "timeline",
                "timeline_params": None,
                "effective_date": None,
                "applicable_entities": [],
            },
            {
                "clause_id": "CIRC-2025-057-CL-03",
                "clause_text": "The recognized Stock Exchanges shall make necessary amendments to the relevant bye-laws for implementation.",
                "obligation_type": "procedure",
                "timeline_params": None,
                "effective_date": "2025-04-28",
                "applicable_entities": ["recognized_stock_exchange"],
            },
        ])
        client = MockLLMClient(response=mixed_response)
        clauses = await parse_circular(
            "Test circular text with multiple obligations, at least ten chars per.",
            self.CIRCULAR_REF,
            client,
        )
        # 2 valid, 1 rejected (bad clause_id + short text)
        assert len(clauses) == 2
        assert clauses[0].clause_id == "CIRC-2025-057-CL-01"
        assert clauses[1].clause_id == "CIRC-2025-057-CL-03"

    @pytest.mark.asyncio
    async def test_all_clauses_invalid_raises(self):
        """When every clause fails validation, raise ValueError."""
        bad_response = json.dumps([
            {
                "clause_id": "bad id",
                "clause_text": "Short",
                "obligation_type": "timeline",
                "timeline_params": None,
                "effective_date": None,
                "applicable_entities": [],
            },
        ])
        client = MockLLMClient(response=bad_response)
        with pytest.raises(ValueError, match="All .* extracted clauses failed"):
            await parse_circular("Valid circular text at least ten chars here.", self.CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_llm_client_error_propagates(self):
        """LLMClientError from the backend should propagate."""
        client = MockLLMClient(response="[]")

        # Patch the mock to raise
        async def _failing_generate(*args, **kwargs):
            raise LLMClientError("API unavailable", status_code=503)
        client.generate = _failing_generate  # type: ignore[method-assign]

        with pytest.raises(LLMClientError, match="API unavailable"):
            await parse_circular("Valid circular text at least ten chars here.", self.CIRCULAR_REF, client)

    @pytest.mark.asyncio
    async def test_markdown_fenced_llm_response(self, circular_text):
        """Some LLMs wrap JSON in markdown fences despite instructions."""
        fenced = f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        client = MockLLMClient(response=fenced)
        clauses = await parse_circular(circular_text, self.CIRCULAR_REF, client)
        assert len(clauses) == 4

    @pytest.mark.asyncio
    async def test_llm_includes_surrounding_text(self, circular_text):
        """LLM includes explanatory text around the JSON array."""
        verbose = f"Here are the extracted obligations:\n\n{SAMPLE_LLM_RESPONSE}\n\nExtraction complete."
        client = MockLLMClient(response=verbose)
        clauses = await parse_circular(circular_text, self.CIRCULAR_REF, client)
        assert len(clauses) == 4

    @pytest.mark.asyncio
    async def test_clause_with_effective_date_parsed(self):
        """Effective date from real circular: April 28, 2025."""
        client = MockLLMClient(response=json.dumps([
            {
                "clause_id": "CIRC-2025-057-CL-01",
                "clause_text": "The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
                "obligation_type": "timeline",
                "timeline_params": {"offset": 1, "grace_period": 0, "unit": "days"},
                "effective_date": "2025-04-28",
                "applicable_entities": ["trading_member", "clearing_member"],
            },
        ]))
        clauses = await parse_circular(
            "Test text that is sufficiently long to pass minimum validation checks.",
            self.CIRCULAR_REF,
            client,
        )
        assert clauses[0].effective_date == date(2025, 4, 28)


# ====================================================================
# LLM client tests
# ====================================================================


class TestDeepSeekTruncationRecovery:
    """Regression tests for truncated JSON recovery from real LLM responses.

    When max_tokens is insufficient or the model output is cut off,
    the parser must salvage as many complete clause objects as possible
    rather than failing entirely.
    """

    def test_recovers_complete_objects_from_truncated_array(self):
        """Realistic DeepSeek v4 Pro truncated response — recover 2 of 3 clauses."""
        truncated = (
            '[\n'
            '  {\n'
            '    "clause_id": "C-1",\n'
            '    "circular_ref": "SEBI/2025/57",\n'
            '    "clause_text": "The TMs/CMs shall collect margins by settlement day.",\n'
            '    "obligation_type": "timeline",\n'
            '    "timeline_params": {"offset": 1, "grace_period": 0, "unit": "days"},\n'
            '    "effective_date": "2025-04-28",\n'
            '    "applicable_entities": ["trading_member"]\n'
            '  },\n'
            '  {\n'
            '    "clause_id": "C-2",\n'
            '    "circular_ref": "SEBI/2025/57",\n'
            '    "clause_text": "The VaR margins shall be collected in advance of trade.",\n'
            '    "obligation_type": "procedure",\n'
            '    "timeline_params": null,\n'
            '    "effective_date": "2025-04-28",\n'
            '    "applicable_entities": ["trading_member"]\n'
            '  },\n'
            '  {\n'
            '    "clause_id": "C-3",\n'
            '    "circular_ref": "SEBI/2025/57",\n'
            '    "clause_text": "Make necessary amendments to the relevant'  # truncated!
        )
        from app.pipeline.nodes.parser import _extract_json_from_response

        result = _extract_json_from_response(truncated)
        assert len(result) == 2, f"Expected 2 recovered clauses, got {len(result)}"
        assert result[0]["clause_id"] == "C-1"
        assert result[1]["clause_id"] == "C-2"

    def test_truncated_mid_key_returns_nothing(self):
        """If no complete top-level object exists, the parser must still raise."""
        from app.pipeline.nodes.parser import _extract_json_from_response

        with pytest.raises(ValueError, match="valid JSON array"):
            _extract_json_from_response('[{"clause_id": "C-1", "clau')

    def test_truncated_array_recovery_returns_list(self):
        """Recovered data must be a list, not a dict or other type."""
        truncated = (
            '[\n'
            '  {"clause_id": "C-1", "clause_text": "test obligation text", '
            '"obligation_type": "timeline"}\n'
        )
        from app.pipeline.nodes.parser import _extract_json_from_response

        result = _extract_json_from_response(truncated)
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}"
        assert len(result) == 1
        assert result[0]["clause_id"] == "C-1"

    def test_complete_response_still_works(self):
        """A complete JSON array must still parse normally (no regression)."""
        complete = (
            '[{"clause_id": "C-1", "clause_text": "test obligation text here", '
            '"obligation_type": "timeline", "applicable_entities": ["trading_member"]}]'
        )
        from app.pipeline.nodes.parser import _extract_json_from_response

        result = _extract_json_from_response(complete)
        assert len(result) == 1
        assert result[0]["clause_id"] == "C-1"


class TestMockLLMClient:
    """Tests for MockLLMClient used in parser tests."""

    @pytest.mark.asyncio
    async def test_returns_configured_response(self):
        client = MockLLMClient(response="test output")
        result = await client.generate("system", "user")
        assert result == "test output"

    @pytest.mark.asyncio
    async def test_records_calls(self):
        client = MockLLMClient(response="output")
        await client.generate("sys1", "user1", temperature=0.2)
        await client.generate("sys2", "user2", temperature=0.5)
        assert len(client.calls) == 2
        assert client.calls[0]["system_prompt"] == "sys1"
        assert client.calls[1]["temperature"] == 0.5
