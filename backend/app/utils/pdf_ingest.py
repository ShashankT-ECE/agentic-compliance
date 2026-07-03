"""
PDF ingestion utility — Node 1 extraction layer.

Handles reading SEBI circular PDFs: text extraction, multi-page aggregation,
and conversion to structured plain-text input for Node 2 (FSM Extractor).

This module is the ONLY place in the pipeline where PDF bytes are touched.
Every downstream node receives plain text — never a raw PDF handle.

Design:
  - pdfplumber for extraction (handles text layout better than PyPDF2
    for regulatory circulars with tables and multi-column text).
  - Page-order is preserved; section ordering across pages is retained
    by concatenating in page sequence with a single newline delimiter.
  - All errors surface as PdfIngestError (or FileNotFoundError for
    missing files) so callers only need to catch two exception types.
  - Empty PDFs (pages with no extractable text) return an empty string
    — this is not an error condition; a warning is logged.

LLM allowed: ✅ Yes (this is Node 1 — text extraction only, no compliance decision).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import pdfplumber

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAGE_DELIMITER: str = "\n"
"""Delimiter inserted between page texts during concatenation.

Kept minimal (single newline) so section continuity across page boundaries
is not disrupted by artificial separators.
"""

_MIN_FILE_SIZE_BYTES: int = 1
"""Minimum file size in bytes for a PDF to be considered non-empty.

A file smaller than this triggers a warning during extraction.
"""


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class PdfIngestError(Exception):
    """Raised when PDF ingestion fails due to a PDF-level error.

    This covers encrypted/protected PDFs, corrupted files, and any
    pdfplumber-level failure that is NOT a simple missing file (which
    raises the standard FileNotFoundError instead).

    Attributes:
        pdf_path: The absolute or relative path to the failing PDF.
        reason: A human-readable description of the failure.
    """

    def __init__(self, pdf_path: str, reason: str) -> None:
        self.pdf_path = pdf_path
        self.reason = reason
        super().__init__(f"Failed to ingest PDF '{pdf_path}': {reason}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_path(pdf_path: str) -> str:
    """Validate that the path exists and is a readable file.

    Returns the resolved absolute path on success.

    Args:
        pdf_path: Filesystem path to the PDF file.

    Returns:
        Resolved absolute path as a string.

    Raises:
        FileNotFoundError: If the path does not exist or is not a file.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF file not found or not a regular file: '{pdf_path}'")
    return os.path.abspath(pdf_path)


def _warn_if_empty(file_path: str) -> None:
    """Log a warning if the file appears suspiciously small.

    Args:
        file_path: Resolved absolute path to the PDF.
    """
    try:
        size = os.path.getsize(file_path)
        if size < _MIN_FILE_SIZE_BYTES:
            logger.warning(
                "PDF file '%s' is %d byte(s) — may be empty or truncated.",
                file_path,
                size,
            )
    except OSError:
        # Non-critical; size check is best-effort.
        logger.debug("Could not stat file '%s' for size check.", file_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_text_by_page(pdf_path: str) -> list[str]:
    """Extract text from every page of a PDF, returning one string per page.

    Pages are returned in document order (page 1 at index 0).  Pages that
    contain no extractable text yield an empty string at their index — this
    preserves the page-position mapping for the caller.

    Args:
        pdf_path: Filesystem path to the PDF file.

    Returns:
        A list of strings, one per page.  Length equals the total page
        count of the document.  An empty list means the PDF has zero pages.

    Raises:
        FileNotFoundError: If ``pdf_path`` does not exist.
        PdfIngestError: If the PDF is encrypted, corrupted, or otherwise
            unreadable by pdfplumber.
    """
    abs_path = _validate_path(pdf_path)
    _warn_if_empty(abs_path)

    logger.info("Opening PDF for per-page extraction: '%s'", abs_path)

    try:
        with pdfplumber.open(abs_path) as pdf:
            pages: list[str] = []
            total_pages: int = len(pdf.pages)

            logger.debug("PDF has %d page(s).", total_pages)

            for page_num, page in enumerate(pdf.pages, start=1):
                try:
                    text: str = page.extract_text() or ""
                    pages.append(text)
                    logger.debug(
                        "Page %d/%d: extracted %d character(s).",
                        page_num,
                        total_pages,
                        len(text),
                    )
                except Exception as exc:
                    raise PdfIngestError(
                        abs_path,
                        f"Error extracting text from page {page_num}: {exc}",
                    ) from exc

            # Check if every page returned empty text.
            non_empty_count = sum(1 for t in pages if t.strip())
            if non_empty_count == 0 and total_pages > 0:
                logger.warning(
                    "PDF '%s' has %d page(s) but zero extractable text — "
                    "the document may be image-based or use unsupported fonts.",
                    abs_path,
                    total_pages,
                )

            logger.info(
                "Per-page extraction complete: %d page(s), %d with text.",
                total_pages,
                non_empty_count,
            )

            return pages

    except PdfIngestError:
        # Re-raise PdfIngestError as-is — it is already well-formed.
        raise

    except Exception as exc:
        # Catch-all for pdfplumber-level failures: encrypted, corrupted, etc.
        error_msg = str(exc).lower()
        if "password" in error_msg or "encrypt" in error_msg:
            reason = "PDF is encrypted or password-protected"
        elif "corrupt" in error_msg or "invalid" in error_msg or "damaged" in error_msg:
            reason = "PDF appears to be corrupted or invalid"
        else:
            reason = f"PDF parsing failed: {exc}"

        logger.exception("PdfIngestError for '%s': %s", abs_path, reason)
        raise PdfIngestError(abs_path, reason) from exc


def extract_text(pdf_path: str) -> str:
    """Extract and concatenate all text from a multi-page PDF.

    Pages are concatenated in document order using a single newline
    delimiter, preserving section flow across page boundaries.  This
    is the primary entry point for Node 1 — the returned string is
    passed directly to Node 2 (FSM Extractor).

    Args:
        pdf_path: Filesystem path to the PDF file.

    Returns:
        Concatenated plain-text content of the entire PDF.  Returns an
        empty string if the PDF contains no extractable text (a warning
        is logged in that case).

    Raises:
        FileNotFoundError: If ``pdf_path`` does not exist.
        PdfIngestError: If the PDF is encrypted, corrupted, or otherwise
            unreadable.
    """
    abs_path = _validate_path(pdf_path)

    logger.info("Extracting full text from PDF: '%s'", abs_path)

    page_texts: list[str] = extract_text_by_page(abs_path)

    if not page_texts:
        logger.warning("PDF '%s' contains zero pages — returning empty string.", abs_path)
        return ""

    full_text: str = _PAGE_DELIMITER.join(page_texts)

    total_chars: int = len(full_text)
    non_blank_chars: int = sum(1 for c in full_text if not c.isspace())

    if non_blank_chars == 0:
        logger.warning(
            "PDF '%s' yielded %d character(s) (%d non-blank) — "
            "returning empty string.",
            abs_path,
            total_chars,
            non_blank_chars,
        )

    logger.info(
        "Full-text extraction complete: %d page(s), %d total character(s), "
        "%d non-blank character(s).",
        len(page_texts),
        total_chars,
        non_blank_chars,
    )

    return full_text
