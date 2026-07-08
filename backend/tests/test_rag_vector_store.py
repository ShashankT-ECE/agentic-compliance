"""
Tests for Chroma vector store (V2 M1).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from app.rag.config import RagConfig
from app.rag.schemas import Chunk, ChunkMetadata
from app.rag.vector_store import ChromaVectorStore


# =============================================================================
# Helpers
# =============================================================================


def _make_chunk(
    chunk_id: str = "TEST::chunk::t1::000",
    text: str = "Regulatory text about margin collection.",
    circular_ref: str = "SEBI/HO/TEST",
    section_path: str = "I.1",
    topic_number: int = 1,
    chunk_index: int = 0,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            circular_ref=circular_ref,
            section_path=section_path,
            topic_number=topic_number,
            chunk_index=chunk_index,
            chunk_total=1,
            char_count=len(text),
        ),
    )


def _fake_embedding(dim: int = 384, seed: float = 0.1) -> list[float]:
    """Generate a deterministic pseudo-embedding for testing."""
    import hashlib
    h = hashlib.sha256(str(seed).encode()).digest()
    # Use hash bytes to generate dim floats in [0, 1)
    vals = []
    for i in range(dim):
        b = h[i % len(h)]
        vals.append(b / 255.0)
    # Normalize
    norm = sum(v * v for v in vals) ** 0.5
    return [v / norm for v in vals]


# =============================================================================
# Fixture
# =============================================================================


@pytest.fixture
def vector_store():
    """Create a ChromaVectorStore with a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = RagConfig()
        cfg.vector_store.chroma.persist_directory = tmpdir
        store = ChromaVectorStore(cfg)
        yield store
        store.reset()


# =============================================================================
# Tests
# =============================================================================


class TestAddAndRetrieve:
    def test_add_and_count(self, vector_store):
        chunks = [_make_chunk(chunk_id=f"T::c::t1::{i:03d}", chunk_index=i)
                  for i in range(3)]
        embeddings = [_fake_embedding(seed=i * 0.1) for i in range(3)]
        count = vector_store.add_chunks(chunks, embeddings)
        assert count == 3
        assert vector_store.count() == 3

    def test_empty_add_returns_zero(self, vector_store):
        assert vector_store.add_chunks([], []) == 0

    def test_length_mismatch_raises(self, vector_store):
        chunks = [_make_chunk()]
        with pytest.raises(ValueError, match="Length mismatch"):
            vector_store.add_chunks(chunks, [])

    def test_get_by_circular_ref(self, vector_store):
        chunks_a = [_make_chunk(circular_ref="CIRC-A", chunk_id="A::c::t1::000")]
        chunks_b = [_make_chunk(circular_ref="CIRC-B", chunk_id="B::c::t1::000")]
        vector_store.add_chunks(chunks_a, [_fake_embedding(seed=0)])
        vector_store.add_chunks(chunks_b, [_fake_embedding(seed=1)])

        results = vector_store.get_by_circular_ref("CIRC-A")
        assert len(results) == 1
        assert results[0].metadata.circular_ref == "CIRC-A"


class TestSearch:
    def test_search_returns_results(self, vector_store):
        chunks = [
            _make_chunk(chunk_id=f"Q::c::t1::{i:03d}", chunk_index=i,
                        text=f"Obligation text for topic {i}")
            for i in range(5)
        ]
        embeddings = [_fake_embedding(seed=i * 0.1) for i in range(5)]
        vector_store.add_chunks(chunks, embeddings)

        results = vector_store.search(_fake_embedding(seed=0.05), top_k=3)
        assert 1 <= len(results) <= 3
        for r in results:
            assert 0.0 <= r.score <= 1.0

    def test_search_with_metadata_filter(self, vector_store):
        chunks = [
            _make_chunk(chunk_id=f"MF::c::t1::{i:03d}", topic_number=1, chunk_index=i)
            for i in range(2)
        ]
        chunks += [
            _make_chunk(chunk_id=f"MF::c::t2::{i:03d}", topic_number=2, chunk_index=i)
            for i in range(2)
        ]
        embeddings = [_fake_embedding(seed=i * 0.1) for i in range(4)]
        vector_store.add_chunks(chunks, embeddings)

        results = vector_store.search(
            _fake_embedding(seed=0.05),
            top_k=10,
            where={"topic_number": 1},
        )
        for r in results:
            assert r.metadata.get("topic_number") == 1

    def test_search_empty_collection(self, vector_store):
        results = vector_store.search(_fake_embedding(), top_k=5)
        assert len(results) == 0


class TestDelete:
    def test_delete_circular(self, vector_store):
        chunks = [
            _make_chunk(circular_ref="DEL-ME", chunk_id=f"DM::c::t1::{i:03d}")
            for i in range(3)
        ]
        vector_store.add_chunks(chunks, [_fake_embedding(seed=i) for i in range(3)])
        assert vector_store.count_by_circular("DEL-ME") == 3

        deleted = vector_store.delete_circular("DEL-ME")
        assert deleted == 3
        assert vector_store.count_by_circular("DEL-ME") == 0

    def test_delete_nonexistent_circular(self, vector_store):
        deleted = vector_store.delete_circular("DOES-NOT-EXIST")
        assert deleted == 0


class TestPersistence:
    def test_data_survives_reopen(self, vector_store):
        chunks = [_make_chunk(chunk_id=f"P::c::t1::{i:03d}", chunk_index=i)
                  for i in range(2)]
        vector_store.add_chunks(chunks, [_fake_embedding(seed=i) for i in range(2)])
        assert vector_store.count() == 2

        # Reopen same store (same temp dir)
        from app.rag.config import RagConfig
        cfg = RagConfig()
        cfg.vector_store.chroma.persist_directory = vector_store._persist_dir
        store2 = ChromaVectorStore(cfg)
        try:
            assert store2.count() == 2
        finally:
            store2.reset()
