"""
RAG API endpoints — V2 M1.

Provides endpoints for indexing circulars, semantic search, and
checking index status.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["rag"])


# =============================================================================
# Request / response models
# =============================================================================


class IndexRequest(BaseModel):
    """Request body for POST /rag/index."""
    circular_path: str = Field(..., min_length=1, description="Path to circular PDF")
    circular_ref: str = Field(..., min_length=1, description="SEBI circular reference")


class IndexResponse(BaseModel):
    """Response for POST /rag/index."""
    circular_ref: str
    chunks_created: int
    chunks_indexed: int
    message: str


class QueryRequest(BaseModel):
    """Request body for POST /rag/query."""
    query: str = Field(..., min_length=3, description="Natural language query")
    top_k: int = Field(default=10, ge=1, le=50, description="Max results")
    circular_ref: str | None = Field(default=None, description="Filter to circular")


class QueryResultItem(BaseModel):
    """A single search result."""
    chunk_id: str
    text: str
    score: float
    metadata: dict


class QueryResponse(BaseModel):
    """Response for POST /rag/query."""
    query: str
    results: list[QueryResultItem]
    total_chunks_searched: int


class StatusResponse(BaseModel):
    """Response for GET /rag/status/{circular_ref}."""
    circular_ref: str
    indexed: bool
    chunk_count: int


class CircularListItem(BaseModel):
    """A single circular in the list response."""
    circular_ref: str
    pdf_path: str
    title: str
    document_hash: str
    index_version: str
    indexed_at: str
    chunk_count: int
    char_count: int
    indexed: bool  # True if chunks exist in Chroma


class CircularListResponse(BaseModel):
    """Response for GET /rag/circulars."""
    circulars: list[CircularListItem]
    total: int


class IndexAllRequest(BaseModel):
    """Optional body for POST /rag/index-all."""
    entries: list[IndexRequest] = Field(
        default_factory=list,
        description="List of circulars to index. If empty, indexes all PDFs "
                    "referenced in the registry that are not yet indexed.",
    )
    directory: str = Field(
        default="data/circulars",
        description="Directory to scan for PDFs when entries is empty",
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/index", response_model=IndexResponse, status_code=201)
def index_circular(request: IndexRequest) -> dict:
    """Index a circular PDF into the RAG vector store.

    Chunks the PDF, generates embeddings, stores them in Chroma, and
    registers the circular in the circular registry for
    multi-circular discovery.
    """
    from app.rag.chunker import DocumentChunker
    from app.rag.config import load_rag_config
    from app.rag.embedder import LocalEmbedder
    from app.rag.vector_store import ChromaVectorStore

    config = load_rag_config()

    # 1. Chunk the PDF
    try:
        chunker = DocumentChunker(config)
        chunks = chunker.chunk_pdf(request.circular_path, request.circular_ref)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Chunking failed")
        raise HTTPException(status_code=500, detail=f"Chunking failed: {e}")

    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks produced — PDF may be empty")

    # 2. Generate embeddings
    try:
        embedder = LocalEmbedder(config)
        texts = [c.text for c in chunks]
        embeddings = embedder._encode_sync(texts)
    except Exception as e:
        logger.exception("Embedding generation failed")
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    # 3. Store embeddings in Chroma (ANN search)
    try:
        store = ChromaVectorStore(config)
        store.add_chunks(chunks, embeddings)
    except Exception as e:
        logger.exception("Vector store write failed")
        raise HTTPException(status_code=500, detail=f"Vector store write failed: {e}")

    # 4. Store chunk text + metadata in PostgreSQL (authoritative)
    _save_chunks_to_pg(chunks)

    # 5. Register in circular registry
    try:
        from app.rag.circular_registry import build_record, get_registry
        registry = get_registry()
        total_chars = sum(c.metadata.char_count for c in chunks)
        record = build_record(
            circular_ref=request.circular_ref,
            pdf_path=request.circular_path,
            chunk_count=len(chunks),
            char_count=total_chars,
        )
        registry.register(record)
    except Exception as e:
        logger.exception("Registry update failed")
        raise HTTPException(status_code=500, detail=f"Registry update failed: {e}")

    return {
        "circular_ref": request.circular_ref,
        "chunks_created": len(chunks),
        "chunks_indexed": store.count_by_circular(request.circular_ref),
        "message": f"Indexed {len(chunks)} chunks for '{request.circular_ref}'",
    }


@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest) -> dict:
    """Search indexed circulars with a natural language query.

    Uses Chroma for ANN vector search; hydrates chunk text and metadata
    from PostgreSQL when available.
    """
    from app.rag.config import load_rag_config
    from app.rag.retrieval import RetrievalPipeline
    from app.database import AsyncSessionLocal

    config = load_rag_config()
    pipeline = RetrievalPipeline(config)

    # Try PG hydration via an async session
    db_session = None
    try:
        db_session = AsyncSessionLocal()
    except Exception:
        logger.debug("PG not available for query hydration")

    try:
        results = await pipeline.search(
            query=request.query,
            top_k=request.top_k,
            circular_ref=request.circular_ref,
            db_session=db_session,
        )
    except Exception as e:
        logger.exception("RAG query failed")
        if db_session:
            await db_session.close()
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    total = pipeline.get_chunk_count(request.circular_ref) if request.circular_ref else 0

    if db_session:
        await db_session.close()

    return {
        "query": request.query,
        "results": [
            {
                "chunk_id": r.chunk_id,
                "text": r.text,
                "score": r.score,
                "metadata": r.metadata,
            }
            for r in results
        ],
        "total_chunks_searched": total,
    }


@router.get("/status/{circular_ref:path}", response_model=StatusResponse)
def rag_status(circular_ref: str) -> dict:
    """Check whether a circular has been indexed.

    Checks PostgreSQL first; falls back to Chroma if PG is unavailable.
    """
    count = _count_chunks_for_circular(circular_ref)
    return {
        "circular_ref": circular_ref,
        "indexed": count > 0,
        "chunk_count": count,
    }


# =============================================================================
# V2 M2 — Multi-circular endpoints
# =============================================================================


@router.get("/circulars", response_model=CircularListResponse)
def list_circulars() -> dict:
    """List all indexed circulars with metadata.

    Prefers PostgreSQL for chunk counts; falls back to Chroma.
    """
    from app.rag.circular_registry import get_registry

    registry = get_registry()

    # Collect refs from both registry and chunk store
    all_refs: set[str] = set()
    registry_records = {r.circular_ref: r for r in registry.list_all()}
    all_refs.update(registry_records.keys())

    # Add refs from chunk store (PG first, Chroma fallback)
    pg_refs = _list_circulars_from_pg()
    if pg_refs:
        all_refs.update(pg_refs)
    else:
        all_refs.update(_list_circulars_from_chroma())

    items: list[dict] = []
    for ref in sorted(all_refs):
        rec = registry_records.get(ref)
        chunk_count = _count_chunks_for_circular(ref)

        items.append({
            "circular_ref": ref,
            "pdf_path": rec.pdf_path if rec else "",
            "title": rec.title if rec else "",
            "document_hash": rec.document_hash if rec else "",
            "index_version": rec.index_version if rec else "",
            "indexed_at": rec.indexed_at if rec else "",
            "chunk_count": rec.chunk_count if rec else chunk_count,
            "char_count": rec.char_count if rec else 0,
            "indexed": chunk_count > 0,
        })

    return {"circulars": items, "total": len(items)}


@router.post("/index-all", response_model=list[IndexResponse], status_code=201)
def index_all(request: IndexAllRequest | None = None) -> list[dict]:
    """Index multiple circulars in one call.

    If *entries* is provided, each entry is indexed (same as calling
    ``POST /index`` for each).  If *entries* is empty, scans *directory*
    for PDFs listed in the registry that have not yet been indexed.
    """
    from pathlib import Path

    from app.rag.circular_registry import get_registry

    entries: list[IndexRequest] = []

    if request is not None and request.entries:
        entries = request.entries
    else:
        # Scan registry for un-indexed circulars whose PDFs are on disk.
        registry = get_registry()
        scan_dir = Path(request.directory) if request and request.directory else Path("data/circulars")

        for rec in registry.list_all():
            pdf_path = Path(rec.pdf_path)
            # Resolve relative paths against the scan directory
            if not pdf_path.is_absolute() and not pdf_path.exists():
                pdf_path = scan_dir / pdf_path.name
            if not pdf_path.exists():
                logger.warning("Skipping '%s' — PDF not found at %s", rec.circular_ref, pdf_path)
                continue

            entries.append(IndexRequest(
                circular_path=str(pdf_path),
                circular_ref=rec.circular_ref,
            ))

        if not entries:
            # Fallback: scan directory for PDFs and use filename as ref
            if scan_dir.exists():
                for pdf_path in sorted(scan_dir.glob("*.pdf")):
                    ref = _derive_circular_ref(pdf_path)
                    entries.append(IndexRequest(
                        circular_path=str(pdf_path),
                        circular_ref=ref,
                    ))

    if not entries:
        raise HTTPException(status_code=400, detail="No circulars found to index")

    results: list[dict] = []
    errors: list[str] = []

    for entry in entries:
        try:
            result = index_circular(entry)
            results.append(result)
        except HTTPException as exc:
            errors.append(f"{entry.circular_ref}: {exc.detail}")
        except Exception as exc:
            errors.append(f"{entry.circular_ref}: {exc}")

    if errors:
        raise HTTPException(
            status_code=500,
            detail=f"Indexing completed with {len(errors)} error(s): {'; '.join(errors[:5])}",
        )

    return results


@router.delete("/circular/{circular_ref:path}")
def delete_circular(circular_ref: str) -> dict:
    """Remove a circular from the index and registry.

    Deletes from PostgreSQL (authoritative), Chroma (embeddings), and the
    circular registry.  The original PDF is NOT deleted from disk.
    """
    from app.rag.circular_registry import get_registry

    registry = get_registry()
    reg_record = registry.get(circular_ref)
    store_count = _count_chunks_for_circular(circular_ref)

    if store_count == 0 and reg_record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Circular '{circular_ref}' not found in index or registry",
        )

    # Delete from PostgreSQL (authoritative)
    pg_deleted = _delete_chunks_from_pg(circular_ref)

    # Delete from Chroma (embeddings)
    chroma_deleted = 0
    try:
        from app.rag.vector_store import ChromaVectorStore
        from app.rag.config import load_rag_config
        config = load_rag_config()
        store = ChromaVectorStore(config)
        chroma_deleted = store.delete_circular(circular_ref)
    except Exception as e:
        logger.warning("Chroma deletion failed for '%s': %s", circular_ref, e)

    # Deregister
    registry.deregister(circular_ref)

    total_deleted = max(pg_deleted, chroma_deleted, store_count)
    return {
        "circular_ref": circular_ref,
        "deleted_chunks": total_deleted,
        "deregistered": reg_record is not None,
        "message": f"Removed '{circular_ref}' ({total_deleted} chunks deleted)",
    }


# =============================================================================
# Helpers
# =============================================================================


def _derive_circular_ref(pdf_path: Path) -> str:
    """Derive a circular reference from a PDF filename.

    Falls back to the stem if the filename doesn't match SEBI patterns.
    """
    stem = pdf_path.stem
    # Common pattern: SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57 → SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57
    if stem.upper().startswith("SEBI"):
        # Replace hyphens between segments with slashes where appropriate
        parts = stem.replace("-official", "").replace("-signed", "").split("-")
        # Heuristic: after "SEBI", join with slashes
        if len(parts) >= 2:
            # Find where the reference pattern changes from department codes to CIR/year/number
            ref_parts: list[str] = []
            for p in parts:
                ref_parts.append(p)
            return "/".join(ref_parts)
    return stem


# =============================================================================
# PG helpers (V2 M4 — Chroma fallback)
# =============================================================================


def _save_chunks_to_pg(chunks) -> None:
    """Dual-write: store chunk text and metadata in PostgreSQL.

    If PG is unavailable, logs a warning and continues — Chroma embedding
    storage is the critical path; PG is the authoritative metadata store
    but the system degrades gracefully without it.
    """
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.rag_chunk_repo import RagChunkRepo

        async def _save():
            async with AsyncSessionLocal() as session:
                repo = RagChunkRepo(session)
                await repo.save_batch(list(chunks))
                await session.commit()

        asyncio.run(_save())
        logger.info("Saved %d chunk(s) to PostgreSQL", len(chunks))
    except Exception:
        logger.warning(
            "Failed to save chunks to PostgreSQL (%d chunks) — "
            "chunks are in Chroma only. Start PostgreSQL via "
            "'docker-compose up -d db'.",
            len(chunks),
        )


def _count_chunks_for_circular(circular_ref: str) -> int:
    """Count chunks from PG, falling back to Chroma."""
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.rag_chunk_repo import RagChunkRepo

        async def _count():
            async with AsyncSessionLocal() as session:
                repo = RagChunkRepo(session)
                return await repo.count_by_circular_ref(circular_ref)

        return asyncio.run(_count())
    except Exception:
        pass

    # Chroma fallback
    try:
        from app.rag.vector_store import ChromaVectorStore
        from app.rag.config import load_rag_config
        store = ChromaVectorStore(load_rag_config())
        return store.count_by_circular(circular_ref)
    except Exception:
        return 0


def _list_circulars_from_pg() -> list[str] | None:
    """Return unique circular refs from PG, or None if unavailable."""
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.rag_chunk_repo import RagChunkRepo

        async def _list():
            async with AsyncSessionLocal() as session:
                repo = RagChunkRepo(session)
                return await repo.list_circulars()

        return asyncio.run(_list())
    except Exception:
        return None


def _list_circulars_from_chroma() -> list[str]:
    """Return unique circular refs from Chroma (fallback)."""
    try:
        from app.rag.vector_store import ChromaVectorStore
        from app.rag.config import load_rag_config
        store = ChromaVectorStore(load_rag_config())
        return store.list_circulars()
    except Exception:
        return []


def _delete_chunks_from_pg(circular_ref: str) -> int:
    """Delete chunks from PG.  Returns count deleted.  Graceful on failure."""
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.rag_chunk_repo import RagChunkRepo

        async def _delete():
            async with AsyncSessionLocal() as session:
                repo = RagChunkRepo(session)
                count = await repo.delete_by_circular_ref(circular_ref)
                await session.commit()
                return count

        return asyncio.run(_delete())
    except Exception:
        logger.warning("Failed to delete chunks from PG for '%s'", circular_ref)
        return 0
