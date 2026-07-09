"""
Chroma vector store integration — V2 M1.

Stores document chunks and their embeddings in a persistent Chroma
collection for semantic retrieval.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.rag.config import RagConfig, VectorStoreConfig
from app.rag.schemas import Chunk, RetrievalResult

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Persistent Chroma vector store for regulatory document chunks.

    Usage::

        store = ChromaVectorStore(config)
        store.add_chunks(chunks, embeddings)
        results = store.search(query_embedding, top_k=10)
    """

    def __init__(self, config: RagConfig | VectorStoreConfig | None = None) -> None:
        if isinstance(config, RagConfig):
            chroma_cfg = config.vector_store.chroma
        elif isinstance(config, VectorStoreConfig):
            chroma_cfg = config.chroma
        else:
            chroma_cfg = RagConfig().vector_store.chroma

        self._persist_dir: str = chroma_cfg.persist_directory
        self._collection_name: str = chroma_cfg.collection_name
        self._client: object | None = None
        self._collection: object | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """Add chunks and their embeddings to the vector store.

        Args:
            chunks: List of Chunk objects to index.
            embeddings: Corresponding embedding vectors (same length as chunks).

        Returns:
            Number of documents added.

        Raises:
            ValueError: If chunks and embeddings have different lengths.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Length mismatch: {len(chunks)} chunks vs {len(embeddings)} embeddings"
            )

        if not chunks:
            return 0

        collection = self._get_collection()

        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [_metadata_dict(c) for c in chunks]

        # Chroma's add() upserts by default — safe to call multiple times.
        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info("Added %d chunks to collection '%s'", len(chunks), self._collection_name)
        return len(chunks)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
    ) -> list[RetrievalResult]:
        """Search for chunks similar to the query embedding.

        Args:
            query_embedding: The embedding of the query text.
            top_k: Maximum number of results to return.
            where: Optional Chroma metadata filter dict.

        Returns:
            List of RetrievalResult objects, ordered by descending similarity.
        """
        collection = self._get_collection()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        return self._parse_results(results)

    def get_by_circular_ref(self, circular_ref: str) -> list[Chunk]:
        """Retrieve all chunks for a specific circular."""
        collection = self._get_collection()
        results = collection.get(
            where={"circular_ref": circular_ref},
            include=["documents", "metadatas"],
        )
        return self._parse_get_results(results)

    def delete_circular(self, circular_ref: str) -> int:
        """Delete all chunks belonging to a circular. Returns count deleted."""
        collection = self._get_collection()
        existing = collection.get(
            where={"circular_ref": circular_ref},
            include=["metadatas"],
        )
        ids_to_delete = existing.get("ids", [])
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            logger.info(
                "Deleted %d chunks for circular '%s'", len(ids_to_delete), circular_ref
            )
        return len(ids_to_delete)

    def count(self) -> int:
        """Return the total number of chunks in the collection."""
        return self._get_collection().count()

    def count_by_circular(self, circular_ref: str) -> int:
        """Return the number of chunks for a specific circular."""
        results = self._get_collection().get(
            where={"circular_ref": circular_ref},
            include=[],
        )
        return len(results.get("ids", []))

    def list_circulars(self) -> list[str]:
        """Return all unique circular refs in the collection.

        Useful for discovering which circulars have been indexed when the
        circular registry file is missing or out of sync.
        """
        collection = self._get_collection()
        # Chroma doesn't have a "distinct values" query, so we fetch all
        # metadata and extract unique circular_ref values in-process.
        results = collection.get(include=["metadatas"])
        refs: set[str] = set()
        for meta in results.get("metadatas", []):
            if meta and "circular_ref" in meta:
                refs.add(meta["circular_ref"])
        return sorted(refs)

    def reset(self) -> None:
        """Delete the entire collection (for testing)."""
        try:
            client = self._get_client()
            client.delete_collection(self._collection_name)
            self._collection = None
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_client(self) -> object:
        """Get or create the Chroma persistent client."""
        if self._client is None:
            import chromadb
            persist_path = Path(self._persist_dir)
            persist_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(persist_path))
            logger.info("Chroma client initialised at '%s'", persist_path)
        return self._client

    def _get_collection(self) -> object:
        """Get or create the Chroma collection."""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "Chroma collection '%s' ready (%d documents)",
                self._collection_name,
                self._collection.count(),
            )
        return self._collection

    def _parse_results(self, raw: dict) -> list[RetrievalResult]:
        """Parse Chroma query results into RetrievalResult objects."""
        out: list[RetrievalResult] = []
        ids_list = raw.get("ids", [[]])
        docs_list = raw.get("documents", [[]])
        metas_list = raw.get("metadatas", [[]])
        dists_list = raw.get("distances", [[]])

        ids = ids_list[0] if ids_list else []
        docs = docs_list[0] if docs_list else []
        metas = metas_list[0] if metas_list else []
        dists = dists_list[0] if dists_list else []

        for i in range(len(ids)):
            # Chroma returns cosine distance for cosine space; convert to
            # similarity: similarity = 1 - distance.
            distance = dists[i] if i < len(dists) else 0.0
            similarity = 1.0 - distance

            out.append(
                RetrievalResult(
                    chunk_id=ids[i],
                    text=docs[i] if i < len(docs) else "",
                    score=round(similarity, 4),
                    metadata=metas[i] if i < len(metas) else {},
                )
            )

        return out

    def _parse_get_results(self, raw: dict) -> list[Chunk]:
        """Parse Chroma get() results into Chunk objects."""
        out: list[Chunk] = []
        ids = raw.get("ids", [])
        docs = raw.get("documents", [])
        metas = raw.get("metadatas", [])

        for i in range(len(ids)):
            meta_dict = metas[i] if i < len(metas) else {}
            chunk = Chunk(
                chunk_id=ids[i],
                text=docs[i] if i < len(docs) else "",
                metadata=_metadata_from_dict(meta_dict),
            )
            out.append(chunk)

        return out


# =============================================================================
# Helpers
# =============================================================================


def _metadata_dict(chunk: Chunk) -> dict:
    """Convert ChunkMetadata to a flat dict for Chroma storage.

    Chroma only supports str, int, float, bool metadata values.
    None values are omitted so Chroma's index doesn't complain.
    """
    m = chunk.metadata
    d: dict[str, str | int | float | bool] = {
        "circular_ref": m.circular_ref,
        "section_path": m.section_path,
        "chunk_index": m.chunk_index,
        "chunk_total": m.chunk_total,
        "char_count": m.char_count,
        "start_page": m.start_page,
        "end_page": m.end_page,
    }
    if m.roman_section is not None:
        d["roman_section"] = m.roman_section
    if m.roman_title is not None:
        d["roman_title"] = m.roman_title
    if m.topic_number is not None:
        d["topic_number"] = m.topic_number
    if m.topic_title is not None:
        d["topic_title"] = m.topic_title
    if m.sub_section is not None:
        d["sub_section"] = m.sub_section
    return d


def _metadata_from_dict(d: dict) -> object:
    """Reconstruct a ChunkMetadata from a flat dict."""
    from app.rag.schemas import ChunkMetadata

    return ChunkMetadata(
        circular_ref=d.get("circular_ref", ""),
        section_path=d.get("section_path", ""),
        roman_section=d.get("roman_section"),
        roman_title=d.get("roman_title"),
        topic_number=d.get("topic_number"),
        topic_title=d.get("topic_title"),
        sub_section=d.get("sub_section"),
        chunk_index=d.get("chunk_index", 0),
        chunk_total=d.get("chunk_total", 1),
        char_count=d.get("char_count", 0),
        start_page=d.get("start_page", 1),
        end_page=d.get("end_page", 1),
    )
