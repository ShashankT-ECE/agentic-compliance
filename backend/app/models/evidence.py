"""
Evidence models — V2 M3.

Defines the provenance chain linking compliance verdicts back to the
exact regulatory text that produced them.

Presentation geometry (``Rectangle``, ``PageRegion``) lives here, not
in the retrieval model (``ChunkMetadata``).  This keeps the evidence
layer independent of PDF rendering details.

Provenance chain:
  Circular → Page → Section → Chunk → Parser → Obligation → FSM → Verdict
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


# =============================================================================
# Presentation geometry (PDF-page-level)
# =============================================================================


class Rectangle(BaseModel):
    """A single rectangular region on a PDF page.

    Coordinates use pdfplumberʼs native system: origin at top-left,
    *y* increases downward.  All values are in PDF points (1 pt = 1/72 inch).
    """

    x0: float = Field(..., ge=0.0, description="Left edge (points)")
    y0: float = Field(..., ge=0.0, description="Top edge (points)")
    x1: float = Field(..., ge=0.0, description="Right edge (points)")
    y1: float = Field(..., ge=0.0, description="Bottom edge (points)")


class PageRegion(BaseModel):
    """The location of a passage on a single PDF page.

    A passage may be split across multiple non-contiguous rectangles on
    the same page (e.g., text wrapping around a table or image).  Each
    entry in ``rectangles`` is one contiguous block.

    This is the *presentation* abstraction — it carries page and region
    data without exposing raw PDF coordinate semantics.
    """

    page_number: int = Field(..., ge=1, description="1-based page number")
    rectangles: list[Rectangle] = Field(
        default_factory=list,
        description="One or more rectangles on this page containing the cited text",
    )


# =============================================================================
# Chunk citation (links a chunk to its PDF position)
# =============================================================================


class ChunkCitation(BaseModel):
    """Citation linking a chunk to the PDF with page positions.

    Designed for the evidence layer — does NOT pollute ChunkMetadata
    with PDF-specific concepts.
    """

    chunk_id: str = Field(..., description="Unique chunk identifier")
    citation_text: str = Field(
        default="",
        description="The chunk text cited as evidence (may be truncated for display)",
    )
    page_range: tuple[int, int] = Field(
        default=(1, 1),
        description="(start_page, end_page) 1-based, inclusive",
    )
    page_regions: list[PageRegion] = Field(
        default_factory=list,
        description="Page-level regions for this chunk; populated lazily "
                    "by the bounding-box extractor after ingest",
    )


# =============================================================================
# Obligation source (chunks → obligation)
# =============================================================================


class ObligationSource(BaseModel):
    """Provenance: which chunks contributed to parsing an obligation.

    In the initial conservative attribution model, all chunks fed to the
    parser are attributed to all obligations it produces.  Future
    attribution strategies may provide finer-grained linkages.
    """

    obligation_ref: str = Field(
        default="",
        description="ObligationClause.clause_id (empty when not yet assigned)",
    )
    source_chunks: list[ChunkCitation] = Field(
        default_factory=list,
        description="Chunks that were provided to the parser for this obligation",
    )
    attribution_method: str = Field(
        default="conservative",
        description="Which AttributionStrategy produced this mapping",
    )


# =============================================================================
# FSM provenance (obligation → FSM)
# =============================================================================


class FSMProvenance(BaseModel):
    """Provenance: which obligation produced which FSM."""

    fsm_id: str = Field(
        default="",
        description="HybridFSM.fsm_id (empty when not yet assigned)",
    )
    locked_fsm_id: str | None = Field(
        default=None,
        description="If the FSM passed through the HITL gate",
    )
    obligation_source: ObligationSource = Field(
        default_factory=ObligationSource,
    )


# =============================================================================
# Evidence reference (top-level — verdict → source chunks)
# =============================================================================


class EvidenceReference(BaseModel):
    """Complete evidence chain from circular PDF to compliance verdict.

    This is the top-level schema returned by the evidence API.  It links
    a single verdict through its FSM and obligation back to the exact
    chunks (and pages) of the regulatory PDF that the parser used.

    Provenance chain:
      Circular → Page → Section → Chunk → Parser → Obligation → FSM → Verdict
    """

    evidence_id: str = Field(
        default_factory=lambda: f"EV-{uuid4().hex[:12].upper()}",
        description="Unique evidence record identifier",
    )
    verdict_id: str = Field(..., description="ComplianceVerdict.verdict_id")
    circular_ref: str = Field(..., description="Source SEBI circular reference")
    fsm_provenance: FSMProvenance = Field(
        default_factory=FSMProvenance,
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when evidence was assembled",
    )
    pipeline_run_id: str | None = Field(
        default=None,
        description="Pipeline run that produced this verdict",
    )
    attribution_method: str = Field(
        default="conservative",
        description="Which AttributionStrategy produced this evidence",
    )
