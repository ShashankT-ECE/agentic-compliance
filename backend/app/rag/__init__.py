"""
RAG (Retrieval-Augmented Generation) subsystem — V2 M1.

Provides structure-aware chunking, local embeddings, Chroma vector storage,
and a retrieval pipeline for processing large regulatory PDFs.

Public API:
  - DocumentChunker       — chunk PDF text at section boundaries
  - LocalEmbedder         — generate embeddings via sentence-transformers
  - ChromaVectorStore     — store and query chunks in Chroma
  - RetrievalPipeline     — orchestrate retrieval for parser integration
  - RagConfig             — YAML-driven configuration

Imports are deferred to avoid circular dependencies and allow incremental
module availability during implementation.
"""

from app.rag.schemas import Chunk, ChunkMetadata, RetrievalResult
from app.rag.config import RagConfig, load_rag_config
from app.rag.chunker import DocumentChunker


def _lazy_import(name: str) -> object:
    """Lazy import a module by name to defer import errors."""
    import importlib
    return importlib.import_module(name)


# Lazy accessors for modules that may not be available yet.
_embedder_module: object | None = None
_vector_store_module: object | None = None
_retrieval_module: object | None = None


def _get_local_embedder() -> type:
    global _embedder_module
    if _embedder_module is None:
        from app.rag.embedder import LocalEmbedder as _LocalEmbedder
        _embedder_module = _LocalEmbedder
    return _embedder_module


def _get_chroma_vector_store() -> type:
    global _vector_store_module
    if _vector_store_module is None:
        from app.rag.vector_store import ChromaVectorStore as _ChromaVectorStore
        _vector_store_module = _ChromaVectorStore
    return _vector_store_module


def _get_retrieval_pipeline() -> type:
    global _retrieval_module
    if _retrieval_module is None:
        from app.rag.retrieval import RetrievalPipeline as _RetrievalPipeline
        _retrieval_module = _RetrievalPipeline
    return _retrieval_module


# Module-level aliases that resolve lazily.
def __getattr__(name: str) -> object:
    if name == "LocalEmbedder":
        return _get_local_embedder()
    if name == "ChromaVectorStore":
        return _get_chroma_vector_store()
    if name == "RetrievalPipeline":
        return _get_retrieval_pipeline()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Chunk",
    "ChunkMetadata",
    "RetrievalResult",
    "RagConfig",
    "load_rag_config",
    "DocumentChunker",
    "LocalEmbedder",
    "ChromaVectorStore",
    "RetrievalPipeline",
]
