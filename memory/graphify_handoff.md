# Graphify Handoff

> **Purpose**: Pipeline graph topology, state, and node/edge information for the Graphify visualization integration.
> **Updated**: 2026-07-11 — V2 M1–M4 complete. M5–M6 pending.

---

## Graph Status

**V1.0.2 FROZEN — V2 M1–M4 COMPLETE.**

The V2 knowledge layer now includes:
- **RAG** (M1): Chroma vector store, bge-small embeddings, topic-level chunking, retrieval pipeline
- **Multi-Circular** (M2): Circular registry, cross-circular search, batch indexing
- **Evidence** (M3): Attribution strategy, bbox extraction, provenance chain, PDF.js viewer
- **PostgreSQL** (M4): 9 ORM tables, 6 repositories, Alembic migrations, graceful fallback

---

## Pipeline Topology (V2 M4)

```
┌── RAG LAYER (V2 M1) ──────────────────────────────────────────────┐
│                                                                     │
│  PDF → [Chunker] → [Embedder] → [Chroma Vector Store]               │
│         200 chunks    bge-small     persistent                       │
│                                                                     │
│  Query → [Embed] → [Chroma.search()] → Retrieved Chunks             │
│                                              │                      │
└──────────────────────────────────────────────┼──────────────────────┘
                                               │
                                               ▼
┌── PIPELINE (V1, preserved) ───────────────────────────────────────┐
│                                                                     │
│  [Node 1: PDF Parser] ──→ [Node 2: FSM Extractor] ──→ [HITL Gate]  │
│       ✅ V2 M1                     ✅ V2 M4              ✅          │
│         │                                                           │
│         │ chunks?  ┌── yes → use chunked text (RAG path)            │
│         │          └── no  → extract full PDF (V1 path)             │
│                                                                     │
│  [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]      │
│                      ✅ deterministic              ✅                │
│                         │                                           │
│                         ▼                                           │
│                  [Evidence Service]                                  │
│                      ✅ V2 M3                                        │
└─────────────────────────────────────────────────────────────────────┘

PERSISTENCE LAYER (V2 M4)
┌──────────────────────────────────────────────────────────────────┐
│  PostgreSQL 16                                                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ circular_records │  │ pipeline_runs    │  │ verdicts       │  │
│  │ locked_fsms      │  │ hitl_review_log  │  │ reports        │  │
│  │ evidence_refs    │  │ rag_chunks       │  │ telemetry_events│ │
│  └──────────────────┘  └──────────────────┘  └────────────────┘  │
│                                                                   │
│  Chroma (embedding vectors only)                                  │
│  JSON files + in-memory stores (graceful fallback)                │
└──────────────────────────────────────────────────────────────────┘
```

| Aspect | Detail |
|--------|--------|
| **Type** | DAG with conditional HITL branch + upstream RAG layer + evidence post-processing |
| **Orchestration** | LangGraph `StateGraph` + `PipelineRunner` |
| **State** | `CompliancePipelineState` (+ chunks, evidence_map fields) |
| **Nodes** | 5 pipeline + 1 HITL gate + RAG layer (4 modules) + Evidence layer (3 modules) |
| **API** | FastAPI with 25 REST endpoints (13 pipeline + 6 RAG + 4 evidence + 3 telemetry + 2 reports + 1 health) |
| **Frontend** | React 19 + TypeScript + Vite + Zustand (93 modules) |
| **Tests** | 642 (410 V1 + 232 V2) — 0 failed |
| **DB** | PostgreSQL 16 (9 tables) + Chroma (embeddings) + JSON fallback |

---

## V2 Change Log

| Date | Change | Description |
|------|--------|-------------|
| 2026-07-09 | V2 M1 RAG | Chunker, embedder, Chroma, retrieval API, parser integration |
| 2026-07-09 | V2 M2 Multi-Circular | Circular registry, index-all, cross-circular search, 3 API endpoints |
| 2026-07-09 | V2 M3 Evidence | Attribution, bbox extraction, evidence service, 4 API endpoints, PDF.js viewer |
| 2026-07-09 | V2 M4 PostgreSQL | 9 ORM models, 6 repositories, Alembic, graceful degradation |
| 2026-07-09 | perf(fsm) | Batch extraction, configurable DeepSeek timeout, LLM response caching |
| 2026-07-11 | Hackathon polish | README rewrite, Docker fixes, setup scripts, documentation cleanup |

---

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| test_models.py | 68 | ✅ |
| test_parser.py | 39 | ✅ |
| test_fsm.py | 34 | ✅ |
| test_hash_chain.py | 20 | ✅ |
| test_hitl.py | 46 | ✅ |
| test_evaluator.py | 75 | ✅ |
| test_scoreboard.py | 38 | ✅ |
| test_orchestration.py | 53 | ✅ |
| test_integration.py | 37 | ✅ |
| test_rag_chunker.py | 13 | ✅ |
| test_rag_embedder.py | 8 | ✅ |
| test_rag_vector_store.py | 14 | ✅ |
| test_rag_retrieval.py | 12 | ✅ |
| test_rag_circular_registry.py | 23 | ✅ |
| test_rag_multi_circular.py | 10 | ✅ |
| test_evidence_models.py | ✅ | ✅ |
| test_evidence_integration.py | ✅ | ✅ |
| test_attribution.py | ✅ | ✅ |
| test_bbox_extractor.py | ✅ | ✅ |
| test_api_evidence.py | ✅ | ✅ |
| test_db_circular_repo.py | ✅ | ✅ |
| test_db_locked_fsm_repo.py | ✅ | ✅ |
| test_db_pipeline_run_repo.py | ✅ | ✅ |
| test_db_rag_chunk_repo.py | ✅ | ✅ |
| **Total** | **642** | **0 failed** |
