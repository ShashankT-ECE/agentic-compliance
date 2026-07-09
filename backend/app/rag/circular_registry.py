"""
Circular Registry — V2 M2.

Tracks every indexed SEBI circular with identity metadata, content hashing,
and versioning.  Designed as an abstraction so the persistence mechanism can
be swapped (JSON file → PostgreSQL in M4) without changing callers.

Records include ``document_hash`` (SHA-256 of the PDF) and ``index_version``
to support incremental re-indexing and future embedding/chunking migrations.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default data directory, relative to the backend root.
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Current index version — bump when chunking or embedding logic changes.
_INDEX_VERSION = "v2-m2"


# =============================================================================
# Data model
# =============================================================================


class CircularRecord(BaseModel):
    """Metadata record for one indexed SEBI circular."""

    circular_ref: str = Field(..., description="SEBI circular reference number")
    pdf_path: str = Field(..., description="Filesystem path to the indexed PDF")
    title: str = Field(default="", description="Human-readable title or subject line")
    document_hash: str = Field(
        default="",
        description="SHA-256 hash of the PDF file at index time",
    )
    index_version: str = Field(
        default=_INDEX_VERSION,
        description="Index version identifier for migration tracking",
    )
    indexed_at: str = Field(
        default="",
        description="ISO-8601 UTC timestamp of the index operation",
    )
    chunk_count: int = Field(default=0, description="Number of chunks produced")
    char_count: int = Field(default=0, description="Total character count of all chunks")


# =============================================================================
# Abstract registry interface
# =============================================================================


class CircularRegistryBackend(Protocol):
    """Protocol that any circular-registry persistence layer must satisfy.

    The JSON-file implementation below is the initial backend.  PostgreSQL
    replaces it in M4 — callers are only coupled to this protocol, not to
    the concrete storage.
    """

    def register(self, record: CircularRecord) -> None:
        """Persist a new or updated circular record."""
        ...

    def deregister(self, circular_ref: str) -> bool:
        """Remove a circular record.  Returns True if it existed."""
        ...

    def get(self, circular_ref: str) -> CircularRecord | None:
        """Retrieve a single record, or None."""
        ...

    def list_all(self) -> list[CircularRecord]:
        """Return all registered circulars."""
        ...


# =============================================================================
# JSON-file implementation
# =============================================================================


class JsonCircularRegistry:
    """Disk-backed circular registry using a JSON file.

    Thread-safe for single-writer workloads (the CLI and APIs are both
    single-process).  The JSON file is readable/editable by operators if
    needed — consistent with the disk-authoritative HITL pattern.
    """

    def __init__(self, registry_path: str | Path | None = None) -> None:
        self._path = Path(registry_path) if registry_path else _DEFAULT_DATA_DIR / "circular_registry.json"
        self._records: dict[str, CircularRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, record: CircularRecord) -> None:
        """Add or update a circular record and persist to disk.

        If a record with the same ``circular_ref`` already exists, its
        fields are merged (new values override old).  This allows partial
        updates as well as full re-registration.
        """
        self._records[record.circular_ref] = record
        self._save()
        logger.info(
            "Registered '%s' (%d chunks, %d chars, v%s)",
            record.circular_ref,
            record.chunk_count,
            record.char_count,
            record.index_version,
        )

    def deregister(self, circular_ref: str) -> bool:
        """Remove a circular from the registry.  Returns True if removed."""
        existed = circular_ref in self._records
        if existed:
            del self._records[circular_ref]
            self._save()
            logger.info("Deregistered '%s'", circular_ref)
        return existed

    def get(self, circular_ref: str) -> CircularRecord | None:
        """Return the record for *circular_ref*, or None if not found."""
        return self._records.get(circular_ref)

    def list_all(self) -> list[CircularRecord]:
        """Return all registered circulars, sorted by reference."""
        return sorted(self._records.values(), key=lambda r: r.circular_ref)

    def count(self) -> int:
        """Return the number of registered circulars."""
        return len(self._records)

    # ------------------------------------------------------------------
    # Hash helpers    # (delegated to module-level functions)

    @staticmethod
    def hash_pdf(pdf_path: str | Path) -> str:
        """Compute SHA-256 hex digest of a PDF file."""
        return _hash_pdf(pdf_path)

    @classmethod
    def build_record(
        cls,
        circular_ref: str,
        pdf_path: str,
        *,
        title: str = "",
        chunk_count: int = 0,
        char_count: int = 0,
    ) -> CircularRecord:
        """Factory: build a fully populated record with current metadata."""
        return _build_record(
            circular_ref=circular_ref,
            pdf_path=pdf_path,
            title=title,
            chunk_count=chunk_count,
            char_count=char_count,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load records from the JSON file on disk."""
        if not self._path.exists():
            logger.debug("Registry file not found at %s — starting empty", self._path)
            self._records = {}
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                logger.warning("Registry file is not a JSON array — starting empty")
                self._records = {}
                return

            for entry in raw:
                try:
                    rec = CircularRecord.model_validate(entry)
                    self._records[rec.circular_ref] = rec
                except Exception:
                    logger.warning(
                        "Skipping invalid registry entry: %s...",
                        str(entry)[:120],
                    )
            logger.debug("Loaded %d record(s) from %s", len(self._records), self._path)
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to read registry file — starting empty")
            self._records = {}

    def _save(self) -> None:
        """Persist all records to the JSON file on disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.model_dump(mode="json") for r in self.list_all()]
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.debug("Wrote %d record(s) to %s", len(data), self._path)


# =============================================================================
# Module-level singleton (lazy)
# =============================================================================

_registry: JsonCircularRegistry | None = None


def get_registry(registry_path: str | Path | None = None) -> CircularRegistryBackend:
    """Return the module-level circular registry singleton.

    Tries PostgreSQL first.  If the database is not available, falls back
    to ``JsonCircularRegistry`` (JSON-file on disk).  This means the
    application works without PostgreSQL — the JSON file is the
    development/fallback persistence.

    Pass *registry_path* to override the default JSON file location
    (primarily for testing).  Ignored when PostgreSQL is active.
    """
    global _registry
    if _registry is None:
        pg_registry = _try_create_pg_registry()
        if pg_registry is not None:
            _registry = pg_registry
            logger.info("Using PostgreSQL-backed circular registry")
        else:
            _registry = JsonCircularRegistry(registry_path)
            logger.info("Using JSON-file circular registry (PostgreSQL not available)")
    return _registry


def reset_registry() -> None:
    """Reset the module-level singleton (for testing)."""
    global _registry
    _registry = None


def _try_create_pg_registry() -> object | None:
    """Attempt to create a PostgreSQL-backed registry.

    Returns None if PostgreSQL is not available (no connection, wrong
    credentials, etc.), so callers get a graceful fallback.
    """
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.circular_repo import CircularRepo

        # Test connectivity with a simple query
        async def _test() -> bool:
            try:
                async with AsyncSessionLocal() as session:
                    repo = CircularRepo(session)
                    await repo.list_all()  # light query — verifies table exists
                    return True
            except Exception:
                return False

        ok = asyncio.run(_test())
        if not ok:
            return None

        return PostgresCircularRegistry()
    except Exception:
        logger.debug("PostgreSQL registry not available — using JSON fallback")
        return None


# =============================================================================
# PostgreSQL-backed registry (V2 M4)
# =============================================================================


class PostgresCircularRegistry:
    """PostgreSQL-backed circular registry.

    Implements ``CircularRegistryBackend`` using ``CircularRepo``, bridging
    the async repository to the synchronous protocol via ``asyncio.run()``.
    In a future phase the protocol can be made async.
    """

    def register(self, record: CircularRecord) -> None:
        """Add or update a circular record in PostgreSQL."""
        import asyncio

        async def _run():
            from app.database import AsyncSessionLocal
            from app.db.repos.circular_repo import CircularRepo
            async with AsyncSessionLocal() as session:
                repo = CircularRepo(session)
                await repo.save(record)
                await session.commit()

        asyncio.run(_run())

    def deregister(self, circular_ref: str) -> bool:
        """Remove a circular record.  Returns True if it existed."""
        import asyncio

        async def _run() -> bool:
            from app.database import AsyncSessionLocal
            from app.db.repos.circular_repo import CircularRepo
            async with AsyncSessionLocal() as session:
                repo = CircularRepo(session)
                result = await repo.delete(circular_ref)
                await session.commit()
                return result

        return asyncio.run(_run())

    def get(self, circular_ref: str) -> CircularRecord | None:
        """Return a single record, or None if not found."""
        import asyncio

        async def _run() -> CircularRecord | None:
            from app.database import AsyncSessionLocal
            from app.db.repos.circular_repo import CircularRepo
            async with AsyncSessionLocal() as session:
                repo = CircularRepo(session)
                return await repo.get(circular_ref)

        return asyncio.run(_run())

    def list_all(self) -> list[CircularRecord]:
        """Return all registered circulars, sorted by reference."""
        import asyncio

        async def _run() -> list[CircularRecord]:
            from app.database import AsyncSessionLocal
            from app.db.repos.circular_repo import CircularRepo
            async with AsyncSessionLocal() as session:
                repo = CircularRepo(session)
                return await repo.list_all()

        return asyncio.run(_run())


# =============================================================================
# Module-level helpers (not tied to any persistence backend)
# =============================================================================


def _hash_pdf(pdf_path: str | Path) -> str:
    """Compute SHA-256 hex digest of a PDF file.

    Returns an empty string if the file cannot be read — callers should
    check for existence before calling this.
    """
    try:
        path = Path(pdf_path)
        if not path.exists():
            logger.warning("Cannot hash — file not found: %s", path)
            return ""
        sha = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except OSError:
        logger.exception("Failed to hash %s", pdf_path)
        return ""


def build_record(
    circular_ref: str,
    pdf_path: str,
    *,
    title: str = "",
    chunk_count: int = 0,
    char_count: int = 0,
) -> CircularRecord:
    """Build a fully populated ``CircularRecord`` with current metadata.

    Computes ``document_hash`` from the PDF and stamps ``indexed_at``
    with the current UTC time.  This is a plain function — not tied to any
    persistence backend — so it works with ``JsonCircularRegistry``,
    PostgreSQL, or any future registry implementation.
    """
    return CircularRecord(
        circular_ref=circular_ref,
        pdf_path=str(pdf_path),
        title=title,
        document_hash=_hash_pdf(pdf_path),
        index_version=_INDEX_VERSION,
        indexed_at=datetime.now(timezone.utc).isoformat(),
        chunk_count=chunk_count,
        char_count=char_count,
    )
