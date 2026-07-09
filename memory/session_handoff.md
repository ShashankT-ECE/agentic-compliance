# Session Handoff

---

## Session Overview

| Field | Value |
|-------|-------|
| **Date** | 2026-07-09 |
| **Developer** | Brad (Friend — Windows + WSL2) |
| **Branch** | `dev` |
| **Latest Commit** | Pending — `feat(v2-m2): implement multi-circular retrieval` |
| **Repository State** | M2 implementation complete, uncommitted. All tests pass. |
| **Overall Status** | **V1.0.2 FROZEN — V2 M1 + M2 COMPLETE — M3 NEXT** |

---

## What Was Done — V2 M2 (Multi-Circular Retrieval)

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     REGULATORY KNOWLEDGE LAYER                       │
│                                                                     │
│  CircularRegistry (JSON)   ChromaVectorStore (persistent)           │
│  ┌─────────────────────┐   ┌──────────────────────────────────┐    │
│  │ circular_ref        │──→│ chunks + embeddings per circular │    │
│  │ pdf_path            │   │ list_circulars()                 │    │
│  │ document_hash       │   │ count_by_circular()              │    │
│  │ index_version       │   │ get_by_circular_ref()            │    │
│  │ indexed_at          │   │ delete_circular()                │    │
│  │ chunk_count         │   └──────────────────────────────────┘    │
│  │ char_count          │                                           │
│  └─────────────────────┘                                           │
│           │                              │                          │
│  GET /api/rag/circulars          RetrievalPipeline                 │
│  POST /api/rag/index-all         .search(query, circular_ref=X)    │
│  DELETE /api/rag/circular/{ref}  .get_text_for_parser(ref)         │
│                                                                     │
│  CLI: list | index-all | delete                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### New files created (2)

| File | Purpose |
|------|---------|
| `backend/app/rag/circular_registry.py` | `CircularRecord` model, `CircularRegistryBackend` Protocol, `JsonCircularRegistry`, module-level `build_record()` |
| `backend/tests/test_rag_multi_circular.py` | 10 tests for new API endpoints (list, index-all, delete) |

### Files modified (6)

| File | Change |
|------|--------|
| `backend/app/rag/__init__.py` | +6 exports (CircularRecord, Backend, build_record, get_registry, reset_registry) |
| `backend/app/rag/vector_store.py` | `list_circulars()` method |
| `backend/app/rag/embedder.py` | `_encode_sync()` calls `_ensure_loaded()` (bug fix) |
| `backend/app/api/routes/rag.py` | 3 new endpoints + `index` now registers in registry |
| `backend/app/cli.py` | 3 new commands: `list`, `index-all`, `delete` |
| `backend/tests/test_rag_retrieval.py` | +6 tests (cross-circular search + chunk provenance) |
| `backend/tests/test_rag_vector_store.py` | +4 tests (list_circulars) |

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| **`CircularRegistryBackend` Protocol** | 4-method protocol. JSON now, PostgreSQL in M4. Callers never import the concrete implementation. |
| **`build_record()` module-level function** | Not tied to any persistence backend. Works with JSON, PostgreSQL, or future backends. |
| **`get_registry()` returns Protocol type** | Callers are type-safe against the protocol, not `JsonCircularRegistry`. |
| **`{circular_ref:path}` on all URL params** | SEBI refs contain slashes. FastAPI `:path` converter preserves them. |
| **document_hash + index_version** | SHA-256 hash of PDF at index time + version tag. Supports incremental re-indexing and embedding migration. |
| **Chunk provenance preserved** | All `RetrievalResult` objects carry full metadata (circular_ref, section_path, topic_number, etc.) — M3 ready. |

### Test results

| Suite | Tests | Status |
|-------|-------|--------|
| V1 (unchanged) | 410 | ✅ 410 passed |
| M1 RAG | 37 | ✅ 37 passed |
| M2 Registry | 23 | ✅ 23 passed |
| M2 Multi-circular API | 10 | ✅ 10 passed |
| M2 Retrieval + Vector Store | +10 | ✅ 10 passed |
| **Total** | **490** | **490 passed, 0 failed, 1 warning** |

---

## Remaining Known Issues

- **399-page Master Circular parser stress** — `max_tokens=16384` consumed by v4 Pro reasoning. RAG path mitigates this.
- **HITL queue accumulates historical runs** — stale directories from test runs.
- **PDF path UX** — backend expects backend-root-relative paths.
- `docs/architecture.pdf` broken (ASCII placeholder) — V2.
- In-memory stores — V2 M4 (PostgreSQL).
- No authentication — V2 M4.
- Docker Compose incomplete — V2 M4.
- Frontend tests — V2 M4.
- Chroma not yet indexed (collection is empty).
- Registry JSON file is a dev mechanism — M4 DB migration.

---

## Next Milestone

**V2 M3 — Evidence Traceability**

Objective: Every compliance decision traceable back to exact regulatory text.

See M3 design document section in the session output for detailed design.

---

## Startup Instructions

```bash
cd /home/bradha/agentic-compliance
git checkout dev
git pull origin dev

# Kill stale server
fuser -k 8000/tcp 2>/dev/null

# Verify
cd backend
source .venv/bin/activate
python -m pytest tests/ -v        # 490 tests
cd ../frontend
npm run build                      # 52 modules

# Index a circular (first time)
python -m app.cli index \
  --pdf-path data/circulars/SEBI-HO-MIRSD-MIRSD-PoD-P-CIR-2025-57-official.pdf \
  --circular-ref "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"

# List indexed circulars
python -m app.cli list

# Search indexed circulars
python -m app.cli search --query "margin collection deadline" --top-k 5

# Start backend
cd ../backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start frontend
cd ../frontend && npm run dev
```

**CRITICAL RULES:**
- Do not redesign M0–M2 — all milestones are independently verified.
- V1 is frozen — do not modify pipeline, models, evaluator, or API.
- Node 3 safety gate (no LLM) must never be violated.
- All 490 tests must continue to pass.
- `use_rag=False` default — V1 path unchanged.
- Parser contract should remain stable.
- RetrievalPipeline should remain stable unless absolutely necessary.
- Server must be restarted after any backend code change.
