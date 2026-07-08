"""Tests for retrieval pipeline (V2 M1)."""
from __future__ import annotations
import asyncio, tempfile
import pytest
from app.rag.config import RagConfig
from app.rag.embedder import LocalEmbedder
from app.rag.retrieval import RetrievalPipeline
from app.rag.schemas import Chunk, ChunkMetadata
from app.rag.vector_store import ChromaVectorStore

def _make_chunk(cid, text, circular_ref="TEST", topic=1, chunk_idx=0):
    return Chunk(chunk_id=cid, text=text, metadata=ChunkMetadata(
        circular_ref=circular_ref, section_path=f"I.{topic}",
        topic_number=topic, chunk_index=chunk_idx, chunk_total=1,
        char_count=len(text)))

@pytest.fixture
def populated_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = RagConfig()
        cfg.vector_store.chroma.persist_directory = tmpdir
        store = ChromaVectorStore(cfg)
        embedder = LocalEmbedder(cfg)
        chunks = [
            _make_chunk("T::c::t1::000", "Trading Members shall collect upfront VaR margins from clients in advance of trade.", "SEBI-001", topic=1),
            _make_chunk("T::c::t1::001", "The Stock Exchange shall verify antecedents before granting admission.", "SEBI-001", topic=2),
            _make_chunk("T::c::t2::000", "The internal audit shall be conducted half-yearly by an independent qualified CA.", "SEBI-001", topic=3),
            _make_chunk("T2::c::t1::000", "Clients must complete KYC documentation before account activation.", "SEBI-002", topic=1),
        ]
        embedder._ensure_loaded()
        embeddings = embedder._encode_sync([c.text for c in chunks])
        store.add_chunks(chunks, embeddings)
        pipeline = RetrievalPipeline(cfg)
        RetrievalPipeline._vector_store = store
        RetrievalPipeline._embedder = embedder
        yield pipeline
        store.reset()
        RetrievalPipeline._vector_store = None
        RetrievalPipeline._embedder = None

class TestSearch:
    def test_search_returns_results(self, populated_store):
        async def _run():
            r = await populated_store.search("margin collection from clients", top_k=3)
            assert len(r) >= 1
            for x in r: assert x.score >= 0.0 and x.text
        asyncio.run(_run())

    def test_search_with_circular_filter(self, populated_store):
        async def _run():
            r = await populated_store.search("client requirements", top_k=10, circular_ref="SEBI-001")
            assert len(r) >= 1
            for x in r: assert x.metadata.get("circular_ref") == "SEBI-001"
        asyncio.run(_run())

    def test_top_k_limit(self, populated_store):
        async def _run():
            r = await populated_store.search("audit", top_k=1)
            assert len(r) <= 1
        asyncio.run(_run())

class TestGetTextForParser:
    def test_retrieves_all_chunks(self, populated_store):
        async def _run():
            t = await populated_store.get_text_for_parser("SEBI-001")
            assert len(t) > 0
            assert "VaR margins" in t
        asyncio.run(_run())

    def test_unindexed_returns_empty(self, populated_store):
        async def _run():
            assert await populated_store.get_text_for_parser("NONEXISTENT") == ""
        asyncio.run(_run())

class TestIsIndexed:
    def test_indexed_check(self, populated_store):
        async def _run():
            assert await populated_store.is_indexed("SEBI-001")
            assert not await populated_store.is_indexed("NONEXISTENT")
        asyncio.run(_run())
