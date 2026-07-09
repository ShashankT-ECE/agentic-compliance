"""
Retrieval pipeline — V2 M2 (Chroma) → V2 M4 (Chroma + PostgreSQL).

Orchestrates chunk retrieval for both semantic search queries and
parser integration.

**V2 M4:** When an ``AsyncSession`` is provided, chunk text and metadata
are read from PostgreSQL (``rag_chunks`` table).  Chroma is used only
for ANN vector search.  When no session is given, falls back to the
V2 M2 behaviour (Chroma for everything).  This preserves backward
compatibility for the CLI and existing tests.
"""

from __future__ import annotations

import logging

from app.rag.config import RagConfig, RetrievalConfig
from app.rag.embedder import LocalEmbedder
from app.rag.schemas import Chunk, RetrievalResult
from app.rag.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """Orchestrate retrieval from the vector store and PostgreSQL.

    Usage::

        pipeline = RetrievalPipeline(config)
        results = await pipeline.search("margin collection deadlines", top_k=10)

    When an ``AsyncSession`` is provided, chunk text and metadata are
    hydrated from PostgreSQL.  Chroma is used only for ANN search.
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
        *,
        db_session=None,          # V2 M4: optional AsyncSession for PG hydration
    ) -> list[RetrievalResult]:
        """Semantic search across indexed circulars.

        Uses Chroma for ANN vector search.  When *db_session* is provided,
        chunk text and metadata are hydrated from PostgreSQL.
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
        results = [r for r in results if r.score >= threshold]

        # Hydrate from PG if a session is available
        if db_session is not None and results:
            chunk_ids = [r.chunk_id for r in results]
            try:
                from app.db.repos.rag_chunk_repo import RagChunkRepo
                repo = RagChunkRepo(db_session)
                pg_chunks = await repo.get_by_chunk_ids(chunk_ids)
                pg_map = {c.chunk_id: c for c in pg_chunks}
                for r in results:
                    if r.chunk_id in pg_map:
                        c = pg_map[r.chunk_id]
                        r.text = c.text
                        r.metadata = {
                            "circular_ref": c.metadata.circular_ref,
                            "section_path": c.metadata.section_path,
                            "topic_number": c.metadata.topic_number,
                            "chunk_index": c.metadata.chunk_index,
                            "start_page": c.metadata.start_page,
                            "end_page": c.metadata.end_page,
                        }
            except Exception:
                logger.debug("PG hydration skipped — session may be unavailable")

        return results

    async def get_text_for_parser(
        self,
        circular_ref: str,
        *,
        db_session=None,          # V2 M4: optional AsyncSession for PG hydration
    ) -> str:
        """Retrieve all chunk text for a circular, for parser consumption.

        When *db_session* is provided, reads from PostgreSQL.
        Otherwise, reads from Chroma.
        """
        if db_session is not None:
            try:
                from app.db.repos.rag_chunk_repo import RagChunkRepo
                repo = RagChunkRepo(db_session)
                chunks = await repo.get_by_circular_ref(circular_ref)
                if chunks:
                    texts = [c.text for c in chunks]
                    return "\n\n".join(texts)
                return ""
            except Exception:
                logger.debug("PG get_text_for_parser failed — falling back to Chroma")

        # Fallback: Chroma
        store = self._get_vector_store()
        chunks = store.get_by_circular_ref(circular_ref)
        if not chunks:
            logger.warning("No chunks found for '%s'", circular_ref)
            return ""
        chunks.sort(key=_chunk_sort_key)
        texts = [c.text for c in chunks]
        return "\n\n".join(texts)

    async def is_indexed(
        self,
        circular_ref: str,
        *,
        db_session=None,          # V2 M4: optional AsyncSession
    ) -> bool:
        """Check whether a circular has been indexed."""
        if db_session is not None:
            try:
                from app.db.repos.rag_chunk_repo import RagChunkRepo
                repo = RagChunkRepo(db_session)
                return await repo.count_by_circular_ref(circular_ref) > 0
            except Exception:
                logger.debug("PG is_indexed failed — falling back to Chroma")
        store = self._get_vector_store()
        return store.count_by_circular(circular_ref) > 0

    def get_chunk_count(
        self,
        circular_ref: str,
        *,
        db_session=None,          # V2 M4: optional AsyncSession (sync wrapper)
    ) -> int:
        """Return the number of indexed chunks for a circular."""
        if db_session is not None:
            import asyncio
            try:
                async def _count():
                    from app.db.repos.rag_chunk_repo import RagChunkRepo
                    repo = RagChunkRepo(db_session)
                    return await repo.count_by_circular_ref(circular_ref)
                return asyncio.run(_count())
            except Exception:
                logger.debug("PG get_chunk_count failed — falling back to Chroma")
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
