# Progress Tracker

> **Purpose**: High-level project status. Understand everything in under 30 seconds.
> **Usage**: Mark `[x]` when complete, `[-]` when in progress, `[ ]` when pending.

---

## Overall Completion

**V1.0.2 COMPLETE + FROZEN.**

**V2 M1 (Regulatory RAG) COMPLETE** — `32149c8`.

**V2 M2 (Multi-Circular Retrieval) COMPLETE** — 490 tests passing. Circular Registry
(Protocol + JSON backend), multi-circular indexing, cross-circular search,
chunk provenance metadata preserved.

---

## V2 Milestone Progress

| M | Name | Status | Key Delivery |
|---|------|--------|-------------|
| M1 | Regulatory RAG Architecture | ✅ Complete (`32149c8`) | Chroma, chunker, embedder, retrieval API |
| M2 | Multi-Circular Retrieval | ✅ Complete | Circular Registry, index-all, cross-circular search |
| M3 | Evidence Traceability | ⬅ NEXT | PDF.js, bounding-box highlighting, provenance chain |
| M4 | PostgreSQL Migration | [ ] Pending | PostgreSQL, Alembic, replace in-memory stores |
| M5 | Compliance Scenario Library | [ ] Pending | Reusable regression scenarios |
| M6 | Tamper-Evident Audit Log | [ ] Pending | Merkle-style hash-chained audit logs |

---

## M2 — Multi-Circular Retrieval (Complete)

### New modules

- [x] `backend/app/rag/circular_registry.py` — `CircularRegistryBackend` Protocol, `JsonCircularRegistry`, `build_record()`
- [x] `backend/tests/test_rag_circular_registry.py` — 23 tests (CRUD, persistence, hashing, singleton)
- [x] `backend/tests/test_rag_multi_circular.py` — 10 tests (list, index-all, delete API endpoints)

### Registry + vector store integration

- [x] `list_circulars()` on `ChromaVectorStore`
- [x] `CircularRecord` with `document_hash` and `index_version`
- [x] `build_record()` module-level factory (not tied to JSON backend)
- [x] `get_registry()` returns `CircularRegistryBackend` protocol type
- [x] `POST /api/rag/index` now registers circulars in registry
- [x] `_encode_sync` lazy-load bug fix

### API + CLI

- [x] `GET /api/rag/circulars` — list all indexed circulars
- [x] `POST /api/rag/index-all` — batch index from entries or directory scan
- [x] `DELETE /api/rag/circular/{circular_ref:path}` — remove circular from index + registry
- [x] `{circular_ref:path}` used on all URL params with slashes
- [x] CLI: `list`, `index-all`, `delete` commands

### M2 tests

- [x] `test_rag_circular_registry.py` — 23 tests (register, deregister, get, list, persistence, build_record, singleton, metadata completeness)
- [x] `test_rag_multi_circular.py` — 10 tests (list circulars, delete, index registers, index-all entries/registry/directory scan)
- [x] `test_rag_retrieval.py` — +6 tests (cross-circular search, filter exclusion, provenance metadata)
- [x] `test_rag_vector_store.py` — +4 tests (list_circulars empty/single/multi/slashes)

---

## Backend

- [x] FastAPI app entry point (`main.py`) — ✅ V1 → V2 M1 → V2 M2
- [x] API routes — pipeline trigger, status, result — ✅ V1
- [x] API routes — RAG (6 endpoints) — ✅ V2 M2
- [x] API routes — HITL review — ✅ V1
- [x] API routes — telemetry — ✅ V1
- [x] API routes — compliance reports — ✅ V1
- [x] API routes — pipeline resume — ✅ V1
- [x] CLI tool — 6 commands (index, search, stats, list, index-all, delete) — ✅ V2 M2
- [x] Data models — obligations, telemetry, FSM, LockedFSM, verdict, scoreboard — ✅ V1
- [x] Utility — PDF ingestion, hash chain, LLM client, state machine, timeline — ✅ V1
- [x] Pipeline — state, graph, runner — ✅ V1 → V2 M1
- [x] Node 1 — PDF Parser — ✅ V1 → V2 M1
- [x] Node 2 — FSM Extractor — ✅ V1
- [x] HITL Gate — ✅ V1
- [x] Node 3 — Assertion Evaluator — ✅ V1
- [x] Node 4 — Scoreboard Generator — ✅ V1
- [x] Circular Registry — ✅ V2 M2
- [ ] Evidence provenance tracking — V2 M3
- [ ] Database connection & migrations — V2 M4

## Frontend

- [x] Full React dashboard — ✅ M8 → ✅ V1.0.2
- [x] AuditReport with Explanation column — ✅ V1.0.2
- [ ] PDF.js viewer — V2 M3
- [ ] Evidence panel — V2 M3
- [ ] Frontend unit/component tests — V2 M4

## Testing

- [x] `test_models.py` — 68 tests — ✅
- [x] `test_parser.py` — 39 tests — ✅ V2 M1 updated
- [x] `test_fsm.py` — 34 tests — ✅
- [x] `test_hash_chain.py` — 20 tests — ✅
- [x] `test_hitl.py` — 46 tests — ✅
- [x] `test_evaluator.py` — 75 tests — ✅
- [x] `test_scoreboard.py` — 38 tests — ✅
- [x] `test_orchestration.py` — 53 tests — ✅
- [x] `test_integration.py` — 37 tests — ✅
- [x] `test_rag_chunker.py` — 13 tests — ✅ V2 M1
- [x] `test_rag_embedder.py` — 8 tests — ✅ V2 M1
- [x] `test_rag_vector_store.py` — 14 tests — ✅ V2 M2
- [x] `test_rag_retrieval.py` — 12 tests — ✅ V2 M2
- [x] `test_rag_circular_registry.py` — 23 tests — ✅ V2 M2
- [x] `test_rag_multi_circular.py` — 10 tests — ✅ V2 M2
- [ ] Evidence tests — V2 M3
- [ ] Frontend tests — V2 M4

**Suite total**: **490 tests — 490 passed, 0 failed**

## Environment

- [x] Python 3.11.15
- [x] DeepSeek v4 Pro API configured
- [x] Frontend builds with zero errors (52 modules)
- [x] bge-small-en-v1.5 embedding model downloaded and cached
- [x] Chroma persistent storage at `backend/data/chroma_db/`
- [x] Circular registry at `backend/data/circular_registry.json`
