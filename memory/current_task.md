# Current Task — Exact Resume Point

---

## Developer

Brad (Friend — Windows + WSL2)

## Date

2026-07-09

## Branch

`dev`

## Latest Commit

To be committed — `feat(v2-m2): implement multi-circular retrieval`

## Repository State

- **Working tree has uncommitted changes** — M2 implementation complete, awaiting commit.
- **490 tests pass, 0 fail** (410 V1 + 80 RAG).
- **Frontend builds clean** (52 modules, zero errors).
- **V1 is frozen.** V2 M1 and M2 are complete.

---

## Current Feature

**V2 M2 — Multi-Circular Retrieval** ✅ COMPLETE

The platform now supports multiple SEBI circulars with:
- Circular Registry (`CircularRegistryBackend` protocol + `JsonCircularRegistry`)
- Registry records with `document_hash` (SHA-256) and `index_version`
- `list_circulars()` on ChromaVectorStore
- `GET /api/rag/circulars` — list all indexed circulars
- `POST /api/rag/index-all` — batch-index circulars
- `DELETE /api/rag/circular/{ref:path}` — remove a circular
- CLI commands: `list`, `index-all`, `delete`
- `build_record()` module-level factory (not tied to JSON backend)
- Chunk provenance metadata preserved through all retrieval paths

---

## V1.0.2 — COMPLETE ✅ (FROZEN)

All V1.0.2 work committed as `401b659` and pushed. V1 frozen — no further changes
except critical bug fixes.

---

## V2 M1 — Regulatory RAG — COMPLETE ✅

M1 delivered: Chroma vector store, bge-small embeddings, topic-level chunking,
retrieval pipeline, parser integration behind `use_rag` feature flag.
Committed as `32149c8`.

---

## V2 M2 — Multi-Circular Retrieval — COMPLETE ✅

### Architecture delivered

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

### New files (2)

| File | Purpose |
|------|---------|
| `backend/app/rag/circular_registry.py` | `CircularRecord`, `CircularRegistryBackend` Protocol, `JsonCircularRegistry`, `build_record()` |
| `backend/tests/test_rag_circular_registry.py` | 23 tests — CRUD, persistence, hashing, singleton, metadata completeness |

### Modified files (5)

| File | Change |
|------|--------|
| `backend/app/rag/__init__.py` | Export `CircularRecord`, `CircularRegistryBackend`, `build_record`, `get_registry`, `reset_registry` |
| `backend/app/rag/vector_store.py` | `list_circulars()` method |
| `backend/app/rag/embedder.py` | `_encode_sync` lazily loads model (bug fix) |
| `backend/app/api/routes/rag.py` | 3 new endpoints + `index` now registers circulars |
| `backend/app/cli.py` | 3 new commands: `list`, `index-all`, `delete` |

### New tests (20)

| File | Tests |
|------|-------|
| `tests/test_rag_circular_registry.py` | 23 tests |
| `tests/test_rag_multi_circular.py` | 10 tests |
| `tests/test_rag_retrieval.py` | +6 (cross-circular search + provenance) |
| `tests/test_rag_vector_store.py` | +4 (`list_circulars`) |

### Key metrics

| Metric | Value |
|--------|-------|
| Total test suite | 490 tests (was 447, +43) |
| New API endpoints | 3 |
| New CLI commands | 3 |
| New files | 2 |
| Modified files | 5 |
| Registry backend | JSON-file with `CircularRegistryBackend` Protocol |
| Record fields | `circular_ref`, `pdf_path`, `title`, `document_hash`, `index_version`, `indexed_at`, `chunk_count`, `char_count` |
| Chunk provenance | Preserved through all search/retrieval paths (M3 ready) |

---

## Next Milestone

**V2 M3 — Evidence Traceability** (see `docs/v2_roadmap.md`)

Objective: Every compliance decision traceable back to exact regulatory text.
PDF.js integration, bounding-box highlighting, page-level citations,
clickable report-to-regulation links.

---

## Exact Next Task

1. Review M3 design document.
2. Implement M3: evidence model, provenance pipeline, PDF.js integration.
3. Add tests.
4. Run full regression.

---

## Warnings

- Node 3 (Assertion Evaluator) must never call an LLM — hard architectural constraint.
- The 6 Node 3 safety gate tests + AST-level verification must always pass.
- Do not redesign M0–M9 — all milestones are independently verified.
- `backup-m5` branch has early-development stubs — do NOT merge into it.
- Server must be restarted after any backend code change.
- **Do NOT modify V1 pipeline, models, evaluator, or API** — V1 is frozen.
- **V1 backward compat preserved** — `use_rag=False` default, 410 V1 tests pass.
