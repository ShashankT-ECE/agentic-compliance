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


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/index", response_model=IndexResponse, status_code=201)
def index_circular(request: IndexRequest) -> dict:
    """Index a circular PDF into the RAG vector store.

    Chunks the PDF, generates embeddings, and stores them in Chroma.
    This is a synchronous operation that may take several seconds for
    large documents.
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

    # 3. Store in Chroma
    try:
        store = ChromaVectorStore(config)
        store.add_chunks(chunks, embeddings)
    except Exception as e:
        logger.exception("Vector store write failed")
        raise HTTPException(status_code=500, detail=f"Vector store write failed: {e}")

    return {
        "circular_ref": request.circular_ref,
        "chunks_created": len(chunks),
        "chunks_indexed": store.count_by_circular(request.circular_ref),
        "message": f"Indexed {len(chunks)} chunks for '{request.circular_ref}'",
    }


@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest) -> dict:
    """Search indexed circulars with a natural language query."""
    from app.rag.config import load_rag_config
    from app.rag.retrieval import RetrievalPipeline

    config = load_rag_config()
    pipeline = RetrievalPipeline(config)

    try:
        results = await pipeline.search(
            query=request.query,
            top_k=request.top_k,
            circular_ref=request.circular_ref,
        )
    except Exception as e:
        logger.exception("RAG query failed")
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    total = pipeline.get_chunk_count(request.circular_ref) if request.circular_ref else 0

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


@router.get("/status/{circular_ref}", response_model=StatusResponse)
def rag_status(circular_ref: str) -> dict:
    """Check whether a circular has been indexed."""
    from app.rag.config import load_rag_config
    from app.rag.vector_store import ChromaVectorStore

    config = load_rag_config()
    store = ChromaVectorStore(config)
    count = store.count_by_circular(circular_ref)

    return {
        "circular_ref": circular_ref,
        "indexed": count > 0,
        "chunk_count": count,
    }
