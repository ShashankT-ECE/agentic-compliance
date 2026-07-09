"""
Circular repository — V2 M4 Phase 1.

PostgreSQL-backed repository for ``circular_records``.
Replaces the JSON-file ``JsonCircularRegistry``.

Usage::

    async with session_factory() as session:
        repo = CircularRepo(session)
        records = await repo.list_all()
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import CircularRecordModel
from app.db.repos.base import BaseRepository
from app.rag.circular_registry import CircularRecord

logger = logging.getLogger(__name__)


class CircularRepo(BaseRepository):
    """Repository for ``circular_records`` table."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, circular_ref: str) -> CircularRecord | None:
        """Return a single record, or None if not found."""
        row = await self._session.get(CircularRecordModel, circular_ref)
        if row is None:
            return None
        return self._to_pydantic(row)

    async def list_all(self) -> list[CircularRecord]:
        """Return all registered circulars, sorted by reference."""
        stmt = select(CircularRecordModel).order_by(CircularRecordModel.circular_ref)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._to_pydantic(r) for r in rows]

    async def save(self, record: CircularRecord) -> None:
        """Insert or update a circular record (upsert)."""
        values = self._to_db_dict(record)
        stmt = pg_insert(CircularRecordModel).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["circular_ref"],
            set_={
                "pdf_path": stmt.excluded.pdf_path,
                "title": stmt.excluded.title,
                "document_hash": stmt.excluded.document_hash,
                "index_version": stmt.excluded.index_version,
                "indexed_at": stmt.excluded.indexed_at,
                "chunk_count": stmt.excluded.chunk_count,
                "char_count": stmt.excluded.char_count,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()
        logger.debug("Saved circular record '%s'", record.circular_ref)

    async def delete(self, circular_ref: str) -> bool:
        """Remove a circular record.  Returns True if it existed."""
        stmt = delete(CircularRecordModel).where(
            CircularRecordModel.circular_ref == circular_ref
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        deleted = result.rowcount > 0
        if deleted:
            logger.info("Deleted circular record '%s'", circular_ref)
        return deleted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pydantic(row: CircularRecordModel) -> CircularRecord:
        """Convert ORM row → Pydantic model."""
        indexed_at = ""
        if row.indexed_at is not None:
            dt = row.indexed_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            indexed_at = dt.isoformat().replace("+00:00", "Z")
        return CircularRecord(
            circular_ref=row.circular_ref,
            pdf_path=row.pdf_path,
            title=row.title,
            document_hash=row.document_hash,
            index_version=row.index_version,
            indexed_at=indexed_at,
            chunk_count=row.chunk_count,
            char_count=row.char_count,
        )

    @staticmethod
    def _to_db_dict(record: CircularRecord) -> dict:
        """Convert Pydantic model → DB column dict."""
        indexed_at = None
        if record.indexed_at:
            try:
                dt = datetime.fromisoformat(record.indexed_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                indexed_at = dt
            except ValueError:
                indexed_at = datetime.now(timezone.utc)

        return {
            "circular_ref": record.circular_ref,
            "pdf_path": record.pdf_path,
            "title": record.title,
            "document_hash": record.document_hash,
            "index_version": record.index_version,
            "indexed_at": indexed_at,
            "chunk_count": record.chunk_count,
            "char_count": record.char_count,
        }
