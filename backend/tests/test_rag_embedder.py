"""
Tests for local embedding model wrapper (V2 M1).

Uses the real sentence-transformers model. On first run the model
(~133 MB) is downloaded and cached.
"""

from __future__ import annotations

import pytest
from app.rag.embedder import LocalEmbedder
from app.rag.config import RagConfig


@pytest.fixture(scope="module")
def embedder() -> LocalEmbedder:
    return LocalEmbedder(RagConfig())


class TestLazyLoading:
    def test_model_not_loaded_on_init(self):
        e = LocalEmbedder(RagConfig())
        assert not e.is_loaded

    def test_model_loaded_after_encode(self, embedder):
        _encode_sync(embedder, ["load test"])
        assert embedder.is_loaded


class TestEncoding:
    def test_dimension_is_384(self, embedder):
        assert embedder.dimension == 384

    def test_encode_returns_correct_shape(self, embedder):
        texts = [
            "The Trading Members are required to collect margins from clients.",
            "Stock Exchanges shall verify the antecedents of the applicant.",
        ]
        vectors = _encode_sync(embedder, texts)
        assert len(vectors) == 2
        for v in vectors:
            assert len(v) == embedder.dimension

    def test_encode_single(self, embedder):
        v = _encode_sync(embedder, ["SEBI circular reference number."])[0]
        assert len(v) == embedder.dimension

    def test_empty_list_raises(self):
        import asyncio
        async def _run():
            e = LocalEmbedder(RagConfig())
            with pytest.raises(ValueError, match="empty"):
                await e.encode([])
        asyncio.run(_run())

    def test_batch_consistent_with_individual(self, embedder):
        texts = [
            "margin collection deadline",
            "client registration requirements",
            "system audit obligations",
        ]
        batch = _encode_sync(embedder, texts)
        individual = [_encode_sync(embedder, [t])[0] for t in texts]
        for bv, iv in zip(batch, individual):
            assert len(bv) == len(iv)
            assert bv == pytest.approx(iv, rel=1e-4)

    def test_semantic_similarity_ordering(self, embedder):
        query = "margin collection from clients by settlement day"
        similar = "collection of margins other than upfront margins from clients"
        dissimilar = "registration of stock brokers with the exchange"

        qv = _encode_sync(embedder, [query])[0]
        sv = _encode_sync(embedder, [similar])[0]
        dv = _encode_sync(embedder, [dissimilar])[0]

        sim_similar = sum(x * y for x, y in zip(qv, sv))
        sim_dissimilar = sum(x * y for x, y in zip(qv, dv))

        assert sim_similar > sim_dissimilar, (
            f"Similar: {sim_similar:.4f}, Dissimilar: {sim_dissimilar:.4f}"
        )


def _encode_sync(embedder: LocalEmbedder, texts: list[str]) -> list[list[float]]:
    """Synchronous convenience wrapper for testing."""
    embedder._ensure_loaded()
    return embedder._encode_sync(texts)
