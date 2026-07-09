"""
RAG chunk repository — V2 M4 Phase 2.

PostgreSQL-backed repository for ``rag_chunks`` — the authoritative
store for chunk text and metadata.  Chroma stores only embedding vectors.

This repository belongs to the Regulatory Knowledge Layer and is
independent of pipeline runs.  All public methods are async.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RagChunkModel
from app.db.repos.base import BaseRepository
from app.rag.schemas import Chunk, ChunkMetadata

logger = logging.getLogger(__name__)


class RagChunkRepo(BaseRepository):
    """Repository for ``rag_chunks`` table.

    Chunk text and structured metadata live here.  Embedding vectors live
    in Chroma.  The ``RetrievalPipeline`` coordinates both stores.
    """

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save_batch(self, chunks: list[Chunk]) -> int:
        """Insert or update a batch of chunks (upsert by chunk_id).

        Returns the number of rows affected.
        """
        if not chunks:
            return 0

        now = datetime.now(timezone.utc)
        values = [
            self._to_db_dict(c, now) for c in chunks
        ]

        stmt = pg_insert(RagChunkModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["chunk_id"],
            set_={
                "text": stmt.excluded.text,
                "chunk_metadata": stmt.excluded.chunk_metadata,
                "created_at": RagChunkModel.created_at,  # keep original
            },
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        logger.info("Saved %d chunk(s) to rag_chunks", len(chunks))
        return result.rowcount

    async def delete_by_circular_ref(self, circular_ref: str) -> int:
        """Delete all chunks for a circular.  Returns count deleted."""
        stmt = (
            delete(RagChunkModel)
            .where(RagChunkModel.circular_ref == circular_ref)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        count = result.rowcount
        logger.info("Deleted %d chunk(s) for '%s' from rag_chunks", count, circular_ref)
        return count

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_chunk_ids(self, chunk_ids: list[str]) -> list[Chunk]:
        """Return chunks for a list of chunk IDs, preserving input order."""
        if not chunk_ids:
            return []

        stmt = (
            select(RagChunkModel)
            .where(RagChunkModel.chunk_id.in_(chunk_ids))
        )
        result = await self._session.execute(stmt)
        rows = {r.chunk_id: r for r in result.scalars().all()}
        # Return in input order
        chunks: list[Chunk] = []
        for cid in chunk_ids:
            row = rows.get(cid)
            if row:
                chunks.append(self._to_pydantic(row))
        return chunks

    async def get_by_circular_ref(self, circular_ref: str) -> list[Chunk]:
        """Return all chunks for a circular, ordered by topic/chunk."""
        stmt = (
            select(RagChunkModel)
            .where(RagChunkModel.circular_ref == circular_ref)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        chunks = [self._to_pydantic(r) for r in rows]
        # Sort by topic_number, then chunk_index (extracted from metadata)
        chunks.sort(key=_chunk_sort_key_from_pydantic)
        return chunks

    async def count_by_circular_ref(self, circular_ref: str) -> int:
        """Return the number of chunks for a circular."""
        stmt = (
            select(func.count())
            .select_from(RagChunkModel)
            .where(RagChunkModel.circular_ref == circular_ref)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_circulars(self) -> list[str]:
        """Return all unique circular_refs with chunks."""
        stmt = (
            select(RagChunkModel.circular_ref)
            .distinct()
            .order_by(RagChunkModel.circular_ref)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def total_count(self) -> int:
        """Return total number of chunks across all circulars."""
        stmt = select(func.count()).select_from(RagChunkModel)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pydantic(row: RagChunkModel) -> Chunk:
        """Convert ORM row → Pydantic Chunk model."""
        meta_dict = row.chunk_metadata if isinstance(row.chunk_metadata, dict) else {}
        return Chunk(
            chunk_id=row.chunk_id,
            text=row.text,
            metadata=_metadata_from_jsonb(meta_dict),
        )

    @staticmethod
    def _to_db_dict(chunk: Chunk, now: datetime | None = None) -> dict:
        """Convert Pydantic Chunk → DB column dict."""
        return {
            "chunk_id": chunk.chunk_id,
            "circular_ref": chunk.metadata.circular_ref,
            "text": chunk.text,
            "chunk_metadata": chunk.metadata.model_dump(mode="json"),
            "created_at": now or datetime.now(timezone.utc),
        }


# =============================================================================
# Module-level helpers
# =============================================================================


def _metadata_from_jsonb(d: dict) -> ChunkMetadata:
    """Reconstruct ChunkMetadata from a JSONB dict."""
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


def _chunk_sort_key_from_pydantic(chunk: Chunk) -> tuple[int, int]:
    """Sort key: topic_number first, then chunk_index."""
    tn = chunk.metadata.topic_number or 0
    ci = chunk.metadata.chunk_index
    return (tn, ci)
