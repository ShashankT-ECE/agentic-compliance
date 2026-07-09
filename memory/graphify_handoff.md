# Graphify Handoff

> **Purpose**: Pipeline graph topology, state, and node/edge information for the Graphify visualization integration.
> **Updated**: 2026-07-09 — V2 M1 (Regulatory RAG) complete, committed, pushed. M2 next.

---

## Graph Status

**V1.0.2 FROZEN — V2 M1 COMPLETE (`32149c8`).**

V2 M1 adds a RAG (Retrieval-Augmented Generation) layer upstream of the existing
5-node pipeline. The RAG layer pre-processes PDFs into structure-aware chunks,
generates embeddings via bge-small-en-v1.5, stores them in Chroma, and feeds
retrieved chunks to the parser when `use_rag=True`.

All V1 node implementations and the HITL gate are unchanged.

---

## Pipeline Topology (V2 M1)

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
│       ✅ M1 V2 M1               ✅ M2 V1.0.1              ✅ M4      │
│         │                                                           │
│         │ chunks?  ┌── yes → use chunked text                       │
│         │          └── no  → extract full PDF (V1 path)             │
│                                                                     │
│  [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]      │
│                      ✅ M5 V1.0.2              ✅ M6                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| Aspect | Detail |
|--------|--------|
| **Type** | DAG with conditional HITL branch + upstream RAG layer |
| **Orchestration** | LangGraph `StateGraph` + `PipelineRunner` |
| **State** | `CompliancePipelineState` (+ `chunks` field in V2 M1) |
| **Nodes** | 5 pipeline + 1 HITL gate + RAG layer (3 new modules) |
| **API** | FastAPI with 16 REST endpoints (13 V1 + 3 RAG) |
| **Frontend** | React 19 + TypeScript + Vite + Zustand (52 modules) |
| **Tests** | 447 (410 V1 + 37 RAG) — 0 failed |

## Key V2 M1 Changes

### RAG Layer

Three new modules form the RAG subsystem:

| Module | Class | Purpose |
|--------|-------|---------|
| `rag/chunker.py` | `DocumentChunker` | Topic-level chunking, 200 chunks from 399-page master circular |
| `rag/embedder.py` | `LocalEmbedder` | bge-small-en-v1.5 (384-dim), lazy loading, async |
| `rag/vector_store.py` | `ChromaVectorStore` | Persistent Chroma, CRUD + search + metadata filter |
| `rag/retrieval.py` | `RetrievalPipeline` | Semantic search + `get_text_for_parser()` |

### Parser Integration

| Change | File | Impact |
|--------|------|--------|
| `chunks` parameter | `parser.py:parse_circular()` | Optional list[str] — when provided, concatenated and used as input |
| `chunks` in state | `parser.py:parser_node()` | Reads `chunks` key from state dict; skips PDF extraction when present |
| `chunks` field | `state.py:CompliancePipelineState` | `chunks: list[str] \| None = None` |
| `chunks` param | `runner.py:PipelineRunner.start()` | Passes chunks through to state |
| `use_rag` flag | `pipeline.py:TriggerRequest` | Boolean, default `False` — enables RAG retrieval in trigger |

### New API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/rag/index` | Index a circular PDF into Chroma |
| `POST` | `/api/rag/query` | Semantic search across indexed circulars |
| `GET` | `/api/rag/status/{circular_ref}` | Check index status for a circular |

### Chunker Design

The chunker detects the SEBI Master Circular's 4-level hierarchy:
Roman sections (I-X) → Numbered topics (1-98) → Sub-sections (X.Y) → Sub-sub-sections (X.Y.Z)

Strategy: chunk at topic boundaries. Split large topics (>3,000 chars) at paragraph boundaries.
Merge small adjacent chunks within the same Roman section. Never merge across section boundaries.

Result: 200 chunks from 399-page master circular (avg 3,680 chars, range 10-81K).

## API Endpoints (V2 M1 — 16 total)

| Method | Path | Node | Added |
|--------|------|------|-------|
| `POST` | `/api/pipeline/trigger` | Starts pipeline (+ `use_rag` flag) | M7 → V2 M1 |
| `GET` | `/api/pipeline/status/{run_id}` | Queries pipeline status | M7 |
| `GET` | `/api/pipeline/result/{run_id}` | Returns verdicts + scoreboard | M7 |
| `POST` | `/api/pipeline/{run_id}/resume` | Resumes after HITL | V1.0.1 |
| `GET` | `/api/pipeline/hitl` | Lists HITL review items | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approves obligation | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Rejects obligation | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amends obligation | M7 |
| `POST` | `/api/telemetry/ingest` | Ingests broker telemetry | M7 |
| `GET` | `/api/telemetry/query` | Queries telemetry | M7 |
| `GET` | `/api/reports/generate/{run_id}` | Generates audit report | M7 → V1.0.2 |
| `GET` | `/api/reports/{report_id}` | Retrieves report | M7 → V1.0.2 |
| `POST` | `/api/rag/index` | Index circular into Chroma | **V2 M1** |
| `POST` | `/api/rag/query` | Semantic search | **V2 M1** |
| `GET` | `/api/rag/status/{circular_ref}` | Index status | **V2 M1** |
| `GET` | `/health` | Health check | M7 |

## Data Flow (V2 M1)

```
[SEBI Circular PDF]
     │
     ├── INDEX PATH (one-time) ──────────────────────────
     │   pdf_ingest.extract_text_by_page()
     │   DocumentChunker.chunk_pdf()
     │   200 chunks with metadata (section_path, topic, etc.)
     │   LocalEmbedder.encode(chunk_texts)
     │   ChromaVectorStore.add_chunks()
     │   ✓ Indexed
     │
     ├── QUERY PATH (on demand) ─────────────────────────
     │   POST /api/rag/query { query: "margin deadlines" }
     │   → LocalEmbedder.encode(query)
     │   → Chroma.search(query_embedding, top_k=10)
     │   → [RetrievalResult, ...]
     │
     └── PIPELINE PATH (use_rag=True) ──────────────────
         POST /api/pipeline/trigger { use_rag: true }
         → RetrievalPipeline.get_text_for_parser(circular_ref)
             → Chroma.get_by_circular_ref(circular_ref)
             → chunks sorted by topic_number, chunk_index
             → concatenated text
         → PipelineRunner.start(..., chunks=chunks)
         → parser_node reads chunks from state
         → parse_circular(input_text=concatenated_chunks)
         → [V1 pipeline continues unchanged]
         → HITL → Evaluator → Scoreboard → Report
```

## Graph Changes

| Date | Change | Description |
|------|--------|-------------|
| 2026-07-03 | Initial topology | V1 topology with HITL conditional edge |
| 2026-07-06 | V1.0.1 | 8 root causes fixed, enterprise UI, 404 tests |
| 2026-07-08 | V1.0.2 | Evaluator fix, explanation column, V1 frozen |
| 2026-07-09 | V2 M1 RAG | Chunker, embedder, Chroma, retrieval API, parser integration |
| 2026-07-09 | V2 M1 release | Committed `32149c8`, pushed to `origin/dev`. 447 tests. |

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| test_models.py | 68 | ✅ |
| test_parser.py | 39 | ✅ V2 M1 updated |
| test_fsm.py | 34 | ✅ |
| test_hash_chain.py | 20 | ✅ |
| test_hitl.py | 46 | ✅ |
| test_evaluator.py | 75 | ✅ |
| test_scoreboard.py | 38 | ✅ |
| test_orchestration.py | 53 | ✅ |
| test_integration.py | 37 | ✅ |
| test_rag_chunker.py | 13 | ✅ V2 M1 |
| test_rag_embedder.py | 8 | ✅ V2 M1 |
| test_rag_vector_store.py | 10 | ✅ V2 M1 |
| test_rag_retrieval.py | 6 | ✅ V2 M1 |
| **Total** | **447** | **0 failed** |

## Next Milestone — M2: Multi-Circular Retrieval

Planned graph changes:
- Circular registry model for tracking multiple indexed circulars
- Multi-circular indexing pipeline (batch index)
- Unified retrieval across all indexed circulars with `circular_ref` metadata
- API: `GET /api/rag/status` (list all indexed circulars)
- Cross-circular search without specifying `circular_ref` filter
