"""
Retrieval pipeline — V2 M1.

Orchestrates chunk retrieval for both semantic search queries and
parser integration (section-by-section text assembly).
"""

from __future__ import annotations

import logging

from app.rag.config import RagConfig, RetrievalConfig
from app.rag.embedder import LocalEmbedder
from app.rag.schemas import Chunk, RetrievalResult
from app.rag.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """Orchestrate retrieval from the vector store.

    Usage::

        pipeline = RetrievalPipeline(config)
        results = await pipeline.search("margin collection deadlines", top_k=10)
        text = await pipeline.get_text_for_parser("SEBI/HO/...")

    The pipeline holds references to the embedder and vector store,
    which are created lazily and cached at module level.
    """

    _embedder: LocalEmbedder | None = None
    _vector_store: ChromaVectorStore | None = None

    def __init__(self, config: RagConfig | None = None) -> None:
        self._config = config or RagConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        circular_ref: str | None = None,
        metadata_filter: dict | None = None,
    ) -> list[RetrievalResult]:
        """Semantic search across indexed circulars.

        Args:
            query: Natural language query.
            top_k: Max results (default from config).
            circular_ref: Optional circular to scope search to.
            metadata_filter: Optional Chroma where-clause dict.

        Returns:
            Ranked list of retrieval results.
        """
        top_k = top_k or self._config.retrieval.default_top_k
        embedder = self._get_embedder()
        store = self._get_vector_store()

        query_embedding = await embedder.encode_single(query)

        # Build metadata filter
        where = dict(metadata_filter) if metadata_filter else {}
        if circular_ref:
            where["circular_ref"] = circular_ref

        results = store.search(query_embedding, top_k=top_k, where=where or None)

        # Filter by similarity threshold
        threshold = self._config.retrieval.similarity_threshold
        filtered = [r for r in results if r.score >= threshold]

        return filtered

    async def get_text_for_parser(
        self,
        circular_ref: str,
    ) -> str:
        """Retrieve all chunk text for a circular, for parser consumption.

        Retrieves all chunks for the given circular and returns them
        concatenated in section order.  This is used by the pipeline
        when ``use_rag=True`` to send structured, pre-indexed text to
        the parser instead of extracting the full PDF.

        Args:
            circular_ref: SEBI circular reference number.

        Returns:
            Concatenated chunk text suitable for parse_circular().
        """
        store = self._get_vector_store()
        chunks = store.get_by_circular_ref(circular_ref)

        if not chunks:
            logger.warning("No chunks found for '%s'", circular_ref)
            return ""

        # Sort by topic_number, then chunk_index for coherent ordering.
        chunks.sort(key=_chunk_sort_key)

        texts = [c.text for c in chunks]
        return "\n\n".join(texts)

    async def is_indexed(self, circular_ref: str) -> bool:
        """Check whether a circular has been indexed in the vector store."""
        store = self._get_vector_store()
        return store.count_by_circular(circular_ref) > 0

    def get_chunk_count(self, circular_ref: str) -> int:
        """Return the number of indexed chunks for a circular."""
        return self._get_vector_store().count_by_circular(circular_ref)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_embedder(self) -> LocalEmbedder:
        if RetrievalPipeline._embedder is None:
            RetrievalPipeline._embedder = LocalEmbedder(self._config)
        return RetrievalPipeline._embedder

    def _get_vector_store(self) -> ChromaVectorStore:
        if RetrievalPipeline._vector_store is None:
            RetrievalPipeline._vector_store = ChromaVectorStore(self._config)
        return RetrievalPipeline._vector_store


def _chunk_sort_key(chunk: Chunk) -> tuple[int, int]:
    """Sort key: topic_number first, then chunk_index."""
    tn = chunk.metadata.topic_number or 0
    ci = chunk.metadata.chunk_index
    return (tn, ci)
