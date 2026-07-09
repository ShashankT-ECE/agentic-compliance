"""
Tests for RagChunkRepo — V2 M4 Phase 2.

Uses in-memory async SQLite for database testing.
"""

from __future__ import annotations

import asyncio
import random

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.db.repos.rag_chunk_repo import RagChunkRepo
from app.rag.schemas import Chunk, ChunkMetadata

pytestmark = pytest.mark.asyncio


# =============================================================================
# Helpers
# =============================================================================


def _make_chunk(
    chunk_id: str = "C::1",
    text: str = "Sample regulatory text.",
    circular_ref: str = "SEBI/TEST/001",
    topic_number: int = 1,
    chunk_index: int = 0,
    start_page: int = 1,
    end_page: int = 1,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            circular_ref=circular_ref,
            section_path=f"I.{topic_number}",
            topic_number=topic_number,
            chunk_index=chunk_index,
            chunk_total=3,
            char_count=len(text),
            start_page=start_page,
            end_page=end_page,
        ),
    )


class _TestDB:
    """Context manager for in-memory async SQLite."""

    def __init__(self):
        self._engine = None
        self._factory = None
        self._session = None
        self.repo = None

    async def __aenter__(self):
        self._engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._factory = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)
        self._session = self._factory()
        self.repo = RagChunkRepo(self._session)
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
        if self._engine:
            await self._engine.dispose()

    async def commit(self):
        await self._session.commit()

    async def reopen(self):
        await self._session.close()
        self._session = self._factory()
        self.repo = RagChunkRepo(self._session)


# =============================================================================
# Tests
# =============================================================================


class TestSaveBatch:
    async def test_save_and_retrieve(self):
        async with _TestDB() as db:
            await db.repo.save_batch([_make_chunk("C::1", "First chunk.")])
            await db.commit()
            await db.reopen()
            chunks = await db.repo.get_by_chunk_ids(["C::1"])
            assert len(chunks) == 1
            assert chunks[0].text == "First chunk."

    async def test_save_is_upsert(self):
        async with _TestDB() as db:
            await db.repo.save_batch([_make_chunk("C::upsert", "Original.")])
            await db.commit()
            await db.reopen()
            await db.repo.save_batch([_make_chunk("C::upsert", "Updated.")])
            await db.commit()
            await db.reopen()
            chunks = await db.repo.get_by_chunk_ids(["C::upsert"])
            assert len(chunks) == 1
            assert chunks[0].text == "Updated."

    async def test_empty_batch(self):
        async with _TestDB() as db:
            count = await db.repo.save_batch([])
            assert count == 0

    async def test_large_batch(self):
        chunks = [_make_chunk(f"C::{i}", f"Chunk {i} text.") for i in range(50)]
        async with _TestDB() as db:
            count = await db.repo.save_batch(chunks)
            await db.commit()
            await db.reopen()
            ids = [f"C::{i}" for i in range(50)]
            result = await db.repo.get_by_chunk_ids(ids)
            assert len(result) == 50


class TestGetByCircularRef:
    async def test_returns_chunks_sorted(self):
        async with _TestDB() as db:
            chunks = [
                _make_chunk("C::T3", chunk_index=2, topic_number=3, circular_ref="REF-A"),
                _make_chunk("C::T1", chunk_index=0, topic_number=1, circular_ref="REF-A"),
                _make_chunk("C::T2", chunk_index=0, topic_number=2, circular_ref="REF-A"),
            ]
            await db.repo.save_batch(chunks)
            await db.commit()
            await db.reopen()
            result = await db.repo.get_by_circular_ref("REF-A")
            assert len(result) == 3
            # Must be sorted by (topic_number, chunk_index)
            topics = [c.metadata.topic_number for c in result]
            assert topics == [1, 2, 3]

    async def test_empty_circular(self):
        async with _TestDB() as db:
            result = await db.repo.get_by_circular_ref("NONEXISTENT")
            assert result == []

    async def test_different_circulars_isolated(self):
        async with _TestDB() as db:
            await db.repo.save_batch([_make_chunk("A::1", circular_ref="REF-A")])
            await db.repo.save_batch([_make_chunk("B::1", circular_ref="REF-B")])
            await db.commit()
            await db.reopen()
            a = await db.repo.get_by_circular_ref("REF-A")
            b = await db.repo.get_by_circular_ref("REF-B")
            assert len(a) == 1
            assert len(b) == 1
            assert a[0].chunk_id == "A::1"
            assert b[0].chunk_id == "B::1"


class TestCount:
    async def test_count_by_circular(self):
        async with _TestDB() as db:
            await db.repo.save_batch([
                _make_chunk("C::1", circular_ref="REF-A"),
                _make_chunk("C::2", circular_ref="REF-A"),
                _make_chunk("C::3", circular_ref="REF-B"),
            ])
            await db.commit()
            assert await db.repo.count_by_circular_ref("REF-A") == 2
            assert await db.repo.count_by_circular_ref("REF-B") == 1
            assert await db.repo.count_by_circular_ref("NONEXISTENT") == 0

    async def test_total_count(self):
        async with _TestDB() as db:
            await db.repo.save_batch([
                _make_chunk("C::1", circular_ref="REF-A"),
                _make_chunk("C::2", circular_ref="REF-B"),
            ])
            await db.commit()
            assert await db.repo.total_count() == 2


class TestListCirculars:
    async def test_list_circulars(self):
        async with _TestDB() as db:
            await db.repo.save_batch([
                _make_chunk("A::1", circular_ref="REF-B"),
                _make_chunk("A::2", circular_ref="REF-A"),
                _make_chunk("A::3", circular_ref="REF-A"),
            ])
            await db.commit()
            refs = await db.repo.list_circulars()
            assert refs == ["REF-A", "REF-B"]

    async def test_empty(self):
        async with _TestDB() as db:
            assert await db.repo.list_circulars() == []


class TestDelete:
    async def test_delete_by_circular_ref(self):
        async with _TestDB() as db:
            await db.repo.save_batch([_make_chunk("D::1", circular_ref="REF-DEL")])
            await db.commit()
            count = await db.repo.delete_by_circular_ref("REF-DEL")
            await db.commit()
            assert count == 1
            assert await db.repo.count_by_circular_ref("REF-DEL") == 0

    async def test_delete_nonexistent(self):
        async with _TestDB() as db:
            count = await db.repo.delete_by_circular_ref("NONEXISTENT")
            await db.commit()
            assert count == 0

    async def test_delete_only_targeted_circular(self):
        async with _TestDB() as db:
            await db.repo.save_batch([
                _make_chunk("D::1", circular_ref="REF-A"),
                _make_chunk("D::2", circular_ref="REF-B"),
            ])
            await db.commit()
            await db.repo.delete_by_circular_ref("REF-A")
            await db.commit()
            await db.reopen()
            assert await db.repo.count_by_circular_ref("REF-A") == 0
            assert await db.repo.count_by_circular_ref("REF-B") == 1


class TestPageRangePersistence:
    """start_page and end_page survive JSONB round-trip."""

    async def test_page_range_round_trip(self):
        chunk = _make_chunk("PG::1", "Text spanning pages.", start_page=3, end_page=5)
        async with _TestDB() as db:
            await db.repo.save_batch([chunk])
            await db.commit()
            await db.reopen()
            result = await db.repo.get_by_chunk_ids(["PG::1"])
            assert len(result) == 1
            assert result[0].metadata.start_page == 3
            assert result[0].metadata.end_page == 5
