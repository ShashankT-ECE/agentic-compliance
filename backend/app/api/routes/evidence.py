"""
Evidence API routes — V2 M3.

Exposes evidence references, chunk positions, and PDF serving so the
frontend evidence viewer can render the provenance chain and highlight
passages in the source circular PDF.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.models.evidence import PageRegion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["evidence"])


# =============================================================================
# Request / response models
# =============================================================================


class EvidenceResponse(BaseModel):
    """Full evidence chain for a verdict."""
    evidence_id: str
    verdict_id: str
    circular_ref: str
    fsm_provenance: dict
    evaluated_at: str
    pipeline_run_id: str | None
    attribution_method: str


class FsmEvidenceResponse(BaseModel):
    """Evidence for a specific locked FSM."""
    locked_fsm_id: str | None
    fsm_id: str
    circular_ref: str
    obligation_ref: str
    source_chunks: list[dict]
    review_status: str | None


class ChunkPositionsResponse(BaseModel):
    """Bounding-box positions for a chunk."""
    chunk_id: str
    circular_ref: str
    page_range: tuple[int, int]
    page_height: float | None
    page_width: float | None
    regions: list[dict]
    status: str  # "complete" | "extracting" | "unavailable"


class EvidenceListResponse(BaseModel):
    """List of evidence references for a pipeline run."""
    run_id: str
    evidence_ids: list[str]
    total: int


# =============================================================================
# Helpers
# =============================================================================


def _resolve_pdf_path(circular_ref: str) -> Path | None:
    """Look up the PDF path for a circular from the registry.

    Returns None if not registered.
    """
    try:
        from app.rag.circular_registry import get_registry
        registry = get_registry()
        rec = registry.get(circular_ref)
        if rec and rec.pdf_path:
            pdf_path = Path(rec.pdf_path)
            if pdf_path.exists():
                return pdf_path
            # Try relative to backend root
            alt = Path(__file__).resolve().parent.parent.parent.parent / rec.pdf_path
            if alt.exists():
                return alt
    except Exception:
        logger.warning("Failed to resolve PDF path for '%s'", circular_ref)
    return None


def _evidence_to_dict(evidence) -> dict:
    """Serialize an EvidenceReference to a JSON-safe dict."""
    return evidence.model_dump(mode="json", exclude_none=True)


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/evidence/{verdict_id}", response_model=EvidenceResponse)
def get_evidence_for_verdict(verdict_id: str) -> dict:
    """Return the complete evidence chain for a compliance verdict.

    Searches the in-memory pipeline run store for the verdict and returns
    its assembled EvidenceReference.  Evidence is automatically generated
    during pipeline execution (after evaluator → scoreboard).
    """
    from app.pipeline.runner import get_run_state

    # Scan all runs for the verdict
    from app.pipeline.runner import _get_store
    store = _get_store()

    for run_id, record in store.items():
        state = record.state
        evidence_data = state.evidence_map.get(verdict_id)
        if evidence_data:
            return evidence_data

        # Also check verdicts directly (fallback if evidence assembly was skipped)
        for v in state.compliance_verdicts:
            if v.verdict_id == verdict_id:
                # Verdict exists but no evidence assembled yet
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Evidence not yet assembled for verdict '{verdict_id}'. "
                        f"The pipeline run '{run_id}' may still be in progress, "
                        "or evidence assembly was skipped (no RAG chunks available)."
                    ),
                )

    raise HTTPException(
        status_code=404,
        detail=f"Verdict '{verdict_id}' not found in any pipeline run.",
    )


@router.get("/evidence/fsm/{locked_fsm_id}", response_model=FsmEvidenceResponse)
def get_evidence_for_fsm(locked_fsm_id: str) -> dict:
    """Return source chunks and obligation for a locked FSM.

    Loads the LockedFSM from disk, resolves its obligation, and returns
    the available provenance data.
    """
    try:
        from app.pipeline.nodes.hitl_gate import load_locked_fsms

        # Find which run this FSM belongs to by scanning disk
        import app.api.routes.pipeline as pipeline_mod
        data_dir = pipeline_mod._get_data_dir()

        # Scan runs for this locked_fsm_id
        found_fsm = None
        found_run_id = None
        if data_dir.exists():
            for run_dir in sorted(data_dir.iterdir(), reverse=True):
                if not run_dir.is_dir():
                    continue
                try:
                    fsms = load_locked_fsms(run_dir.name, data_dir=data_dir)
                    for fsm in fsms:
                        if fsm.locked_fsm_id == locked_fsm_id:
                            found_fsm = fsm
                            found_run_id = run_dir.name
                            break
                except Exception:
                    continue
                if found_fsm:
                    break

        if found_fsm is None:
            raise HTTPException(
                status_code=404,
                detail=f"LockedFSM '{locked_fsm_id}' not found in any pipeline run",
            )

        # Get chunks from PostgreSQL (authoritative), Chroma fallback
        circular_ref = found_fsm.circular_ref
        indexed_chunks = _get_chunks_for_circular(circular_ref)

        source_chunks: list[dict] = []
        if indexed_chunks:
            for c in indexed_chunks:
                source_chunks.append({
                    "chunk_id": c.chunk_id,
                    "text": c.text[:500],  # truncated for display
                    "page_range": [c.metadata.start_page, c.metadata.end_page],
                    "section_path": c.metadata.section_path,
                })

        return {
            "locked_fsm_id": found_fsm.locked_fsm_id,
            "fsm_id": found_fsm.fsm_id,
            "circular_ref": circular_ref,
            "obligation_ref": found_fsm.obligation_ref,
            "source_chunks": source_chunks,
            "review_status": found_fsm.status.value if hasattr(found_fsm.status, 'value') else str(found_fsm.status),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get evidence for FSM '%s'", locked_fsm_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve FSM evidence: {exc}",
        )


@router.get("/chunks/{chunk_id:path}/positions", response_model=ChunkPositionsResponse)
def get_chunk_positions(
    chunk_id: str,
    circular_ref: str = Query(..., description="SEBI circular reference"),
) -> dict:
    """Return pre-computed page regions for a specific chunk.

    Returns ``status: "complete"`` with bounding boxes, ``"unavailable"``
    if the chunk or PDF is not found, or ``"extracting"`` if extraction
    is in progress (future: background task support).
    """
    from app.utils.bbox_extractor import BoundingBoxExtractor

    # Look up the chunk in PostgreSQL (authoritative), Chroma fallback
    chunks = _get_chunks_for_circular(circular_ref)
    chunk = next((c for c in chunks if c.chunk_id == chunk_id), None)

    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chunk '{chunk_id}' not found for circular '{circular_ref}'",
        )

    # Resolve PDF path
    pdf_path = _resolve_pdf_path(circular_ref)
    if pdf_path is None:
        return {
            "chunk_id": chunk_id,
            "circular_ref": circular_ref,
            "page_range": (chunk.metadata.start_page, chunk.metadata.end_page),
            "page_height": None,
            "page_width": None,
            "regions": [],
            "status": "unavailable",
        }

    # Extract (or load from cache)
    extractor = BoundingBoxExtractor()
    regions = extractor.load_or_extract(
        chunk_id=chunk_id,
        pdf_path=pdf_path,
        chunk_text=chunk.text,
        start_page=chunk.metadata.start_page,
        end_page=chunk.metadata.end_page,
    )

    # Get page dimensions from the first page of the region
    page_height = None
    page_width = None
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if regions and regions[0].page_number <= len(pdf.pages):
                page = pdf.pages[regions[0].page_number - 1]
                page_height = float(page.height)
                page_width = float(page.width)
    except Exception:
        pass

    return {
        "chunk_id": chunk_id,
        "circular_ref": circular_ref,
        "page_range": (chunk.metadata.start_page, chunk.metadata.end_page),
        "page_height": page_height,
        "page_width": page_width,
        "regions": [r.model_dump(mode="json") for r in regions],
        "status": "complete" if regions else "unavailable",
    }


@router.get("/circulars/{circular_ref:path}/pdf")
def serve_circular_pdf(circular_ref: str) -> FileResponse:
    """Serve the source PDF for a circular (for the PDF.js viewer).

    Returns the PDF file with ``Content-Type: application/pdf`` so the
    browser's built-in PDF viewer or PDF.js can render it.
    """
    pdf_path = _resolve_pdf_path(circular_ref)
    if pdf_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"PDF not found for circular '{circular_ref}'. "
                   "Ensure the circular is registered and the PDF file exists.",
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{circular_ref.replace('/', '_')}.pdf",
    )


# =============================================================================
# Chunk helpers (V2 M4 — PG with Chroma fallback)
# =============================================================================


def _get_chunks_for_circular(circular_ref: str) -> list:
    """Get chunks from PostgreSQL (authoritative), Chroma fallback."""
    # Try PG first
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.rag_chunk_repo import RagChunkRepo

        async def _fetch():
            async with AsyncSessionLocal() as session:
                repo = RagChunkRepo(session)
                return await repo.get_by_circular_ref(circular_ref)

        chunks = asyncio.run(_fetch())
        if chunks:
            return chunks
    except Exception:
        pass

    # Chroma fallback
    try:
        from app.rag.vector_store import ChromaVectorStore
        from app.rag.config import load_rag_config
        store = ChromaVectorStore(load_rag_config())
        return store.get_by_circular_ref(circular_ref)
    except Exception:
        return []
