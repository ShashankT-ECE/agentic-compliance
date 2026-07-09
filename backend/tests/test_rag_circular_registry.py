"""
Tests for Circular Registry — V2 M2.

Covers the JsonCircularRegistry CRUD operations, document hashing,
record factory, file persistence, and the module-level singleton.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.rag.circular_registry import (
    CircularRecord,
    JsonCircularRegistry,
    _INDEX_VERSION,
    get_registry,
    reset_registry,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry_file() -> Path:
    """Temporary registry file path (does not exist)."""
    with TemporaryDirectory() as tmp:
        yield Path(tmp) / "test_registry.json"


@pytest.fixture
def registry(registry_file: Path) -> JsonCircularRegistry:
    """Empty registry backed by a temp file."""
    return JsonCircularRegistry(registry_file)


@pytest.fixture
def sample_record() -> CircularRecord:
    """A fully populated sample record."""
    return CircularRecord(
        circular_ref="SEBI/HO/MIRSD/P/CIR/2025/57",
        pdf_path="data/circulars/test-circular.pdf",
        title="Timelines for collection of Margins",
        document_hash="abc123def",
        index_version="v2-m2",
        indexed_at="2026-07-09T12:00:00Z",
        chunk_count=200,
        char_count=736000,
    )


# =============================================================================
# Tests — Register
# =============================================================================


class TestRegister:
    def test_register_adds_record(self, registry: JsonCircularRegistry, sample_record: CircularRecord) -> None:
        registry.register(sample_record)
        assert registry.count() == 1

    def test_register_persists_to_disk(self, registry: JsonCircularRegistry, sample_record: CircularRecord, registry_file: Path) -> None:
        registry.register(sample_record)
        assert registry_file.exists()
        data = json.loads(registry_file.read_text())
        assert len(data) == 1
        assert data[0]["circular_ref"] == sample_record.circular_ref

    def test_register_updates_existing(self, registry: JsonCircularRegistry, sample_record: CircularRecord) -> None:
        registry.register(sample_record)
        updated = sample_record.model_copy(update={"chunk_count": 500, "document_hash": "newhash"})
        registry.register(updated)
        assert registry.count() == 1
        retrieved = registry.get(sample_record.circular_ref)
        assert retrieved is not None
        assert retrieved.chunk_count == 500
        assert retrieved.document_hash == "newhash"

    def test_register_multiple_circulars(self, registry: JsonCircularRegistry) -> None:
        for i in range(3):
            rec = CircularRecord(
                circular_ref=f"SEBI/CIR/2025/{i}",
                pdf_path=f"data/circulars/test-{i}.pdf",
            )
            registry.register(rec)
        assert registry.count() == 3


# =============================================================================
# Tests — Deregister
# =============================================================================


class TestDeregister:
    def test_deregister_existing(self, registry: JsonCircularRegistry, sample_record: CircularRecord) -> None:
        registry.register(sample_record)
        result = registry.deregister(sample_record.circular_ref)
        assert result is True
        assert registry.count() == 0
        assert registry.get(sample_record.circular_ref) is None

    def test_deregister_nonexistent(self, registry: JsonCircularRegistry) -> None:
        result = registry.deregister("NONEXISTENT")
        assert result is False

    def test_deregister_persists(self, registry: JsonCircularRegistry, sample_record: CircularRecord, registry_file: Path) -> None:
        registry.register(sample_record)
        registry.deregister(sample_record.circular_ref)
        data = json.loads(registry_file.read_text())
        assert len(data) == 0


# =============================================================================
# Tests — Get
# =============================================================================


class TestGet:
    def test_get_existing(self, registry: JsonCircularRegistry, sample_record: CircularRecord) -> None:
        registry.register(sample_record)
        retrieved = registry.get(sample_record.circular_ref)
        assert retrieved is not None
        assert retrieved.circular_ref == sample_record.circular_ref
        assert retrieved.chunk_count == sample_record.chunk_count

    def test_get_nonexistent(self, registry: JsonCircularRegistry) -> None:
        assert registry.get("NONEXISTENT") is None


# =============================================================================
# Tests — List all
# =============================================================================


class TestListAll:
    def test_list_all_empty(self, registry: JsonCircularRegistry) -> None:
        assert registry.list_all() == []

    def test_list_all_sorted(self, registry: JsonCircularRegistry) -> None:
        refs = ["SEBI/CIR/2025/C", "SEBI/CIR/2025/A", "SEBI/CIR/2025/B"]
        for ref in refs:
            registry.register(CircularRecord(circular_ref=ref, pdf_path=f"data/{ref}.pdf"))
        result = registry.list_all()
        assert [r.circular_ref for r in result] == sorted(refs)


# =============================================================================
# Tests — Persistence (survives re-open)
# =============================================================================


class TestPersistence:
    def test_data_survives_reopen(self, registry_file: Path, sample_record: CircularRecord) -> None:
        reg1 = JsonCircularRegistry(registry_file)
        reg1.register(sample_record)

        # Re-open with the same file
        reg2 = JsonCircularRegistry(registry_file)
        assert reg2.count() == 1
        assert reg2.get(sample_record.circular_ref) is not None

    def test_empty_file_starts_clean(self, registry_file: Path) -> None:
        registry_file.write_text("[]")
        reg = JsonCircularRegistry(registry_file)
        assert reg.count() == 0

    def test_corrupt_file_starts_clean(self, registry_file: Path) -> None:
        registry_file.write_text("not valid json {")
        reg = JsonCircularRegistry(registry_file)
        assert reg.count() == 0

    def test_wrong_shape_starts_clean(self, registry_file: Path) -> None:
        registry_file.write_text('{"key": "not a list"}')
        reg = JsonCircularRegistry(registry_file)
        assert reg.count() == 0


# =============================================================================
# Tests — Build record (factory)
# =============================================================================


class TestBuildRecord:
    def test_build_record_defaults(self) -> None:
        """Build record without a real PDF — hash will be empty."""
        from app.rag.circular_registry import build_record

        rec = build_record(
            circular_ref="TEST/001",
            pdf_path="/nonexistent/path.pdf",
            title="Test Circular",
            chunk_count=10,
            char_count=5000,
        )
        assert rec.circular_ref == "TEST/001"
        assert rec.title == "Test Circular"
        assert rec.document_hash == ""  # nonexistent file
        assert rec.index_version == _INDEX_VERSION
        assert rec.chunk_count == 10
        assert rec.char_count == 5000
        assert rec.indexed_at != ""

    def test_build_record_with_real_pdf(self) -> None:
        """Build with a real PDF to verify hash computation."""
        from app.rag.config import _DEFAULT_CONFIG_PATH
        from app.rag.circular_registry import build_record

        # Use the rag.yaml config file as a stand-in for a real file
        rec = build_record(
            circular_ref="TEST/002",
            pdf_path=str(_DEFAULT_CONFIG_PATH),
        )
        assert rec.document_hash != ""
        assert len(rec.document_hash) == 64  # SHA-256 hex
        assert rec.indexed_at != ""


# =============================================================================
# Tests — Module-level singleton
# =============================================================================


class TestSingleton:
    def test_get_registry_returns_same_instance(self) -> None:
        reset_registry()
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_get_registry_with_custom_path(self) -> None:
        reset_registry()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom.json"
            reg = get_registry(path)
            assert reg._path == path
        reset_registry()


# =============================================================================
# Tests — Metadata completeness (M3 readiness)
# =============================================================================


class TestMetadataCompleteness:
    """Ensure records carry provenance metadata that M3 can build on."""

    def test_record_has_document_hash(self, sample_record: CircularRecord) -> None:
        assert sample_record.document_hash != ""

    def test_record_has_index_version(self, sample_record: CircularRecord) -> None:
        assert sample_record.index_version != ""

    def test_record_has_indexed_at(self, sample_record: CircularRecord) -> None:
        assert sample_record.indexed_at != ""

    def test_json_roundtrip(self, sample_record: CircularRecord) -> None:
        """Model dump → parse preserves all fields."""
        data = sample_record.model_dump(mode="json")
        parsed = CircularRecord.model_validate(data)
        assert parsed.circular_ref == sample_record.circular_ref
        assert parsed.document_hash == sample_record.document_hash
        assert parsed.index_version == sample_record.index_version
        assert parsed.chunk_count == sample_record.chunk_count
