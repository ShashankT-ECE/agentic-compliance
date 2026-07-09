"""
Tests for CircularRepo — V2 M4 Phase 1.

Uses in-memory async SQLite for database testing without requiring
a running PostgreSQL instance.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio

from app.database import Base
from app.db.repos.circular_repo import CircularRepo
from app.rag.circular_registry import CircularRecord


# =============================================================================
# Helpers
# =============================================================================


def _make_record(
    circular_ref: str = "SEBI/TEST/001",
    pdf_path: str = "data/circulars/test.pdf",
    title: str = "Test Circular",
    chunk_count: int = 10,
    char_count: int = 5000,
    document_hash: str = "a" * 64,
    indexed_at: str = "2026-07-09T12:00:00Z",
) -> CircularRecord:
    return CircularRecord(
        circular_ref=circular_ref,
        pdf_path=pdf_path,
        title=title,
        document_hash=document_hash,
        index_version="v2-m2",
        indexed_at=indexed_at,
        chunk_count=chunk_count,
        char_count=char_count,
    )


class _TestDB:
    """Context manager for an in-memory async SQLite database."""

    def __init__(self):
        self._engine = None
        self._factory = None
        self._session = None
        self.repo = None

    async def __aenter__(self):
        self._engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._session = self._factory()
        self.repo = CircularRepo(self._session)
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
        self.repo = CircularRepo(self._session)


# =============================================================================
# Tests
# =============================================================================


class TestCircularRepoSave:
    async def test_save_and_retrieve(self):
        async with _TestDB() as db:
            record = _make_record("SEBI/SAVE/001")
            await db.repo.save(record)
            await db.commit()
            await db.reopen()
            result = await db.repo.get("SEBI/SAVE/001")
            assert result is not None
            assert result.chunk_count == 10

    async def test_save_is_upsert(self):
        async with _TestDB() as db:
            await db.repo.save(_make_record("SEBI/UPSERT/001", chunk_count=5))
            await db.commit()
            await db.reopen()
            await db.repo.save(_make_record("SEBI/UPSERT/001", chunk_count=50, title="Updated"))
            await db.commit()
            await db.reopen()
            result = await db.repo.get("SEBI/UPSERT/001")
            assert result is not None
            assert result.chunk_count == 50
            assert result.title == "Updated"


class TestCircularRepoGet:
    async def test_get_existing(self):
        async with _TestDB() as db:
            await db.repo.save(_make_record("SEBI/GET/001"))
            await db.commit()
            await db.reopen()
            result = await db.repo.get("SEBI/GET/001")
            assert result is not None

    async def test_get_nonexistent(self):
        async with _TestDB() as db:
            result = await db.repo.get("NONEXISTENT")
            assert result is None


class TestCircularRepoListAll:
    async def test_list_all_empty(self):
        async with _TestDB() as db:
            assert await db.repo.list_all() == []

    async def test_list_all_sorted(self):
        async with _TestDB() as db:
            await db.repo.save(_make_record("SEBI/Z"))
            await db.repo.save(_make_record("SEBI/A"))
            await db.repo.save(_make_record("SEBI/M"))
            await db.commit()
            await db.reopen()
            result = await db.repo.list_all()
            refs = [r.circular_ref for r in result]
            assert refs == ["SEBI/A", "SEBI/M", "SEBI/Z"]


class TestCircularRepoDelete:
    async def test_delete_existing(self):
        async with _TestDB() as db:
            await db.repo.save(_make_record("SEBI/DEL/001"))
            await db.commit()
            await db.reopen()
            existed = await db.repo.delete("SEBI/DEL/001")
            await db.commit()
            await db.reopen()
            assert existed is True
            assert await db.repo.get("SEBI/DEL/001") is None

    async def test_delete_nonexistent(self):
        async with _TestDB() as db:
            assert await db.repo.delete("NONEXISTENT") is False


class TestPydanticRoundTrip:
    async def test_full_round_trip(self):
        record = _make_record()
        async with _TestDB() as db:
            await db.repo.save(record)
            await db.commit()
            await db.reopen()
            result = await db.repo.get(record.circular_ref)
            assert result is not None
            assert result.document_hash == record.document_hash
            assert result.chunk_count == record.chunk_count
            assert result.indexed_at == record.indexed_at

    async def test_null_indexed_at(self):
        async with _TestDB() as db:
            await db.repo.save(_make_record(indexed_at=""))
            await db.commit()
            await db.reopen()
            result = await db.repo.get(_make_record().circular_ref)
            assert result is not None
            assert result.indexed_at == ""
