# Progress Tracker

> **Purpose**: High-level project status. Understand everything in under 30 seconds.
> **Usage**: Mark `[x]` when complete, `[-]` when in progress, `[ ]` when pending.

---

## Overall Completion

**V1.0.2 COMPLETE + FROZEN.**

**V2 M1–M4 COMPLETE** — 642 tests passing. Frontend builds clean (93 modules).

**V2 M5–M6 PENDING.**

---

## V2 Milestone Progress

| M | Name | Status | Key Delivery |
|---|------|--------|-------------|
| M1 | Regulatory RAG Architecture | ✅ Complete (`32149c8`) | Chroma, chunker, embedder, retrieval API |
| M2 | Multi-Circular Retrieval | ✅ Complete | Circular Registry, index-all, cross-circular search |
| M3 | Evidence Traceability | ✅ Complete (`1754c66`) | Evidence models, attribution, bbox extraction, PDF.js viewer |
| M4 | PostgreSQL Migration | ✅ Complete (`f231741`) | SQLAlchemy ORM, Alembic, 6 repositories, 9 tables |
| M5 | Compliance Scenario Library | [ ] Pending | Reusable regression scenarios |
| M6 | Tamper-Evident Audit Log | [ ] Pending | Merkle-style hash-chained audit logs |

---

## M3 — Evidence Traceability (Complete)

- [x] `EvidenceReference`, `ChunkCitation`, `PageRegion`, `Rectangle` models
- [x] `ObligationSource`, `FSMProvenance` provenance chain models
- [x] `ConservativeAttribution` strategy (Protocol-based, swappable)
- [x] `EvidenceService` — orchestration of evidence assembly
- [x] `BoundingBoxExtractor` — pdfplumber word-level position extraction
- [x] `GET /api/evidence/{verdict_id}` — full evidence chain API
- [x] `GET /api/evidence/fsm/{locked_fsm_id}` — FSM evidence API
- [x] `GET /api/chunks/{chunk_id}/positions` — bounding-box API
- [x] `GET /api/circulars/{circular_ref}/pdf` — PDF serving for PDF.js
- [x] Frontend PDF.js viewer with highlighted passages
- [x] Frontend EvidencePanel with provenance chain viewer

## M4 — PostgreSQL Migration (Complete)

- [x] 9 SQLAlchemy ORM models (all domain entities)
- [x] 6 repository classes with full CRUD operations
- [x] Alembic migration `001_initial_schema.py`
- [x] `RagChunkRepo` with PG-first, Chroma-fallback pattern
- [x] `PostgresCircularRegistry` — PG backend for circular registry
- [x] Graceful degradation — in-memory + JSON fallback when PG unavailable
- [x] DB test suite: 4 test files for repos

---

## Backend

- [x] FastAPI app entry point (`main.py`) — ✅ V1 → V2 M4
- [x] API routes — pipeline trigger, status, result — ✅ V1
- [x] API routes — RAG (6 endpoints) — ✅ V2 M2
- [x] API routes — Evidence (4 endpoints) — ✅ V2 M3
- [x] API routes — HITL review (10 endpoints) — ✅ V1
- [x] API routes — telemetry (3 endpoints) — ✅ V1
- [x] API routes — compliance reports (2 endpoints) — ✅ V1
- [x] API routes — pipeline resume — ✅ V1
- [x] CLI tool — 6 commands (index, search, stats, list, index-all, delete) — ✅ V2 M2
- [x] Data models — obligations, telemetry, FSM, LockedFSM, verdict, scoreboard, evidence — ✅
- [x] Utility — PDF ingestion, hash chain, LLM client, state machine, timeline, bbox — ✅
- [x] Pipeline — state, graph, runner — ✅ V1 → V2 M3
- [x] Node 1 — PDF Parser — ✅ V1 → V2 M1
- [x] Node 2 — FSM Extractor — ✅ V1
- [x] HITL Gate — ✅ V1
- [x] Node 3 — Assertion Evaluator — ✅ V1
- [x] Node 4 — Scoreboard Generator — ✅ V1
- [x] Circular Registry — ✅ V2 M2
- [x] Evidence provenance tracking — ✅ V2 M3
- [x] Database connection & migrations — ✅ V2 M4

## Frontend

- [x] Full React dashboard — ✅ M8 → ✅ V1.0.2
- [x] AuditReport with Explanation column — ✅ V1.0.2
- [x] HITL Review page — ✅ V1.0.2
- [x] PDF.js viewer — ✅ V2 M3
- [x] Evidence panel — ✅ V2 M3
- [x] Evidence page (side-by-side PDF + provenance) — ✅ V2 M3
- [ ] Frontend unit/component tests — V2 M5

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
- [x] `test_evidence_models.py` — ✅ V2 M3
- [x] `test_evidence_integration.py` — ✅ V2 M3
- [x] `test_attribution.py` — ✅ V2 M3
- [x] `test_bbox_extractor.py` — ✅ V2 M3
- [x] `test_api_evidence.py` — ✅ V2 M3
- [x] `test_db_circular_repo.py` — ✅ V2 M4
- [x] `test_db_locked_fsm_repo.py` — ✅ V2 M4
- [x] `test_db_pipeline_run_repo.py` — ✅ V2 M4
- [x] `test_db_rag_chunk_repo.py` — ✅ V2 M4
- [ ] Evidence tests — ✅ Complete
- [ ] Frontend tests — V2 M5

**Suite total**: **642 tests — 642 passed, 0 failed**

## Environment

- [x] Python 3.11.15
- [x] DeepSeek v4 Pro API configured
- [x] Frontend builds with zero errors (93 modules)
- [x] bge-small-en-v1.5 embedding model downloaded and cached
- [x] Chroma persistent storage at `backend/data/chroma_db/`
- [x] Circular registry at `backend/data/circular_registry.json`
- [x] PostgreSQL 16 with async SQLAlchemy + Alembic
- [x] LLM response caching for deterministic extraction
