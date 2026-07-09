"""
Multi-circular API tests — V2 M2.

Tests the new RAG endpoints: list circulars, index-all, and delete
circular.  Uses FastAPI's TestClient with real Chroma (temp directory).
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag.circular_registry import reset_registry, JsonCircularRegistry
from app.rag.config import RagConfig
from app.rag.vector_store import ChromaVectorStore


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def temp_chroma_dir() -> str:
    """Temporary Chroma persistence directory."""
    with TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def temp_registry_path() -> Path:
    """Temporary registry file path."""
    with TemporaryDirectory() as tmp:
        yield Path(tmp) / "test_registry.json"


@pytest.fixture
def seeded_store(temp_chroma_dir: str, temp_registry_path: Path) -> ChromaVectorStore:
    """Chroma store with seed data and a clean registry.

    Patches ``load_rag_config`` so the API endpoints use the temp Chroma
    directory and temp registry file instead of the production defaults.
    """
    reset_registry()

    import app.rag.config as cfg
    original_load = cfg.load_rag_config

    def _temp_config(*args, **kwargs):
        c = original_load(*args, **kwargs)
        c.vector_store.chroma.persist_directory = temp_chroma_dir
        return c

    cfg.load_rag_config = _temp_config

    # Create registry pointing to temp file
    registry = JsonCircularRegistry(temp_registry_path)
    import app.rag.circular_registry as cr_module
    cr_module._registry = registry

    # Build store pointing to temp dir
    config = _temp_config()
    store = ChromaVectorStore(config)
    store.reset()

    # Seed two circulars with dummy chunks + embeddings
    from app.rag.schemas import Chunk, ChunkMetadata

    for i in range(2):
        ref = f"SEBI/CIR/2025/{i+1}"
        chunks = [
            Chunk(
                chunk_id=f"{ref.replace('/', '-')}-chunk-{j}",
                text=f"Chunk {j} text for {ref}. Margin collection deadline T+{j+1}.",
                metadata=ChunkMetadata(
                    circular_ref=ref,
                    section_path=f"I.{j+1}",
                    topic_number=j + 1,
                    chunk_index=j,
                    chunk_total=3,
                    char_count=50,
                ),
            )
            for j in range(3)
        ]
        import random
        random.seed(42 + i)
        embeddings = [[random.random() for _ in range(384)] for _ in range(3)]
        store.add_chunks(chunks, embeddings)

        # Also register in the registry
        from app.rag.circular_registry import CircularRecord
        registry.register(CircularRecord(
            circular_ref=ref,
            pdf_path=f"data/circulars/test-{i+1}.pdf",
            title=f"Test Circular {i+1}",
            document_hash=f"hash{i+1}",
            index_version="v2-m2",
            indexed_at="2026-07-09T12:00:00Z",
            chunk_count=3,
            char_count=150,
        ))

    yield store

    store.reset()
    reset_registry()
    cfg.load_rag_config = original_load


# =============================================================================
# Tests — GET /circulars
# =============================================================================


class TestListCirculars:
    def test_returns_all_circulars(self, client: TestClient, seeded_store: ChromaVectorStore) -> None:
        resp = client.get("/api/rag/circulars")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        refs = [c["circular_ref"] for c in data["circulars"]]
        assert "SEBI/CIR/2025/1" in refs
        assert "SEBI/CIR/2025/2" in refs

    def test_circular_has_registry_metadata(self, client: TestClient, seeded_store: ChromaVectorStore) -> None:
        resp = client.get("/api/rag/circulars")
        data = resp.json()
        c1 = next(c for c in data["circulars"] if c["circular_ref"] == "SEBI/CIR/2025/1")
        assert c1["title"] == "Test Circular 1"
        assert c1["document_hash"] == "hash1"
        assert c1["index_version"] == "v2-m2"
        assert c1["indexed_at"] != ""
        assert c1["chunk_count"] == 3
        assert c1["indexed"] is True

    def test_empty_when_nothing_indexed(self, client: TestClient, temp_chroma_dir: str, temp_registry_path: Path) -> None:
        """Empty registry + empty store = empty list."""
        reset_registry()
        import app.rag.circular_registry as cr_module
        cr_module._registry = JsonCircularRegistry(temp_registry_path)

        resp = client.get("/api/rag/circulars")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


# =============================================================================
# Tests — DELETE /circular/{ref}
# =============================================================================


class TestDeleteCircular:
    def test_delete_existing(self, client: TestClient, seeded_store: ChromaVectorStore) -> None:
        resp = client.delete("/api/rag/circular/SEBI/CIR/2025/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_chunks"] > 0
        assert data["deregistered"] is True

        # Verify it's gone
        resp2 = client.get("/api/rag/status/SEBI/CIR/2025/1")
        assert resp2.json()["indexed"] is False

        resp3 = client.get("/api/rag/circulars")
        refs = [c["circular_ref"] for c in resp3.json()["circulars"]]
        assert "SEBI/CIR/2025/1" not in refs

    def test_delete_nonexistent(self, client: TestClient, seeded_store: ChromaVectorStore) -> None:
        resp = client.delete("/api/rag/circular/NONEXISTENT")
        assert resp.status_code == 404

    def test_delete_idempotent(self, client: TestClient, seeded_store: ChromaVectorStore) -> None:
        """Second delete of same circular returns 404."""
        client.delete("/api/rag/circular/SEBI/CIR/2025/2")
        resp = client.delete("/api/rag/circular/SEBI/CIR/2025/2")
        assert resp.status_code == 404


# =============================================================================
# Tests — POST /index (registry integration)
# =============================================================================


class TestIndexRegistersCircular:
    def test_index_registers_in_registry(self, client: TestClient, temp_chroma_dir: str, temp_registry_path: Path) -> None:
        """Indexing a PDF also registers it."""
        reset_registry()
        import app.rag.circular_registry as cr_module
        cr_module._registry = JsonCircularRegistry(temp_registry_path)

        # Override config for temp dir
        import app.rag.config as cfg
        original_load = cfg.load_rag_config

        def _temp_config(*args, **kwargs):
            c = original_load(*args, **kwargs)
            c.vector_store.chroma.persist_directory = temp_chroma_dir
            return c

        cfg.load_rag_config = _temp_config

        try:
            # Use the real 2-page SEBI circular
            pdf_path = "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf"
            if not Path(pdf_path).exists():
                pytest.skip("Test circular PDF not found")

            resp = client.post("/api/rag/index", json={
                "circular_path": pdf_path,
                "circular_ref": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["chunks_created"] > 0

            # Check registry
            resp2 = client.get("/api/rag/circulars")
            circs = resp2.json()
            refs = [c["circular_ref"] for c in circs["circulars"]]
            assert "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57" in refs
        finally:
            cfg.load_rag_config = original_load
            reset_registry()


# =============================================================================
# Tests — POST /index-all
# =============================================================================


class TestIndexAll:
    def test_index_all_with_entries(self, client: TestClient, temp_chroma_dir: str, temp_registry_path: Path) -> None:
        """Index-all with explicit entries."""
        reset_registry()
        import app.rag.circular_registry as cr_module
        cr_module._registry = JsonCircularRegistry(temp_registry_path)

        import app.rag.config as cfg
        original_load = cfg.load_rag_config

        def _temp_config(*args, **kwargs):
            c = original_load(*args, **kwargs)
            c.vector_store.chroma.persist_directory = temp_chroma_dir
            return c

        cfg.load_rag_config = _temp_config

        try:
            pdf_path = "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf"
            if not Path(pdf_path).exists():
                pytest.skip("Test circular PDF not found")

            resp = client.post("/api/rag/index-all", json={
                "entries": [
                    {"circular_path": pdf_path, "circular_ref": "SEBI/TEST/1"},
                    {"circular_path": pdf_path, "circular_ref": "SEBI/TEST/2"},
                ]
            })
            assert resp.status_code == 201
            data = resp.json()
            assert len(data) == 2
            assert all(r["chunks_created"] > 0 for r in data)

            # Both should be in the list
            resp2 = client.get("/api/rag/circulars")
            refs = [c["circular_ref"] for c in resp2.json()["circulars"]]
            assert "SEBI/TEST/1" in refs
            assert "SEBI/TEST/2" in refs
        finally:
            cfg.load_rag_config = original_load
            reset_registry()

    def test_index_all_empty_entries_with_registry(self, client: TestClient, temp_chroma_dir: str, temp_registry_path: Path) -> None:
        """Index-all with no entries scans registry for un-indexed circulars."""
        reset_registry()
        import app.rag.circular_registry as cr_module
        cr_module._registry = JsonCircularRegistry(temp_registry_path)

        import app.rag.config as cfg
        original_load = cfg.load_rag_config

        def _temp_config(*args, **kwargs):
            c = original_load(*args, **kwargs)
            c.vector_store.chroma.persist_directory = temp_chroma_dir
            return c

        cfg.load_rag_config = _temp_config

        try:
            pdf_path = "data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57.pdf"
            if not Path(pdf_path).exists():
                pytest.skip("Test circular PDF not found")

            # Pre-register but don't index
            from app.rag.circular_registry import CircularRecord
            registry = cr_module._registry
            registry.register(CircularRecord(
                circular_ref="SEBI/PRE-REGISTERED/1",
                pdf_path=str(Path(pdf_path).resolve()),
                title="Pre-registered Test",
            ))

            resp = client.post("/api/rag/index-all", json={
                "entries": [],
                "directory": str(Path(pdf_path).parent),
            })
            assert resp.status_code == 201
            data = resp.json()
            assert len(data) >= 1

            # Pre-registered circular should now be indexed
            resp2 = client.get("/api/rag/status/SEBI/PRE-REGISTERED/1")
            assert resp2.json()["indexed"] is True
        finally:
            cfg.load_rag_config = original_load
            reset_registry()

    def test_index_all_no_entries_no_registry(self, client: TestClient, temp_chroma_dir: str, temp_registry_path: Path) -> None:
        """Index-all with no entries and empty registry scans directory for PDFs."""
        reset_registry()
        import app.rag.circular_registry as cr_module
        cr_module._registry = JsonCircularRegistry(temp_registry_path)

        import app.rag.config as cfg
        original_load = cfg.load_rag_config

        def _temp_config(*args, **kwargs):
            c = original_load(*args, **kwargs)
            c.vector_store.chroma.persist_directory = temp_chroma_dir
            return c

        cfg.load_rag_config = _temp_config

        try:
            resp = client.post("/api/rag/index-all", json={
                "entries": [],
                "directory": "data/circulars",
            })
            # Should index all PDFs in data/circulars/
            assert resp.status_code == 201
            data = resp.json()
            assert len(data) >= 1  # at least one PDF in the directory
        finally:
            cfg.load_rag_config = original_load
            reset_registry()
