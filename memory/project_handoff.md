# Project Handoff

> **Purpose**: Permanent project overview. Updated ONLY when the project itself changes.
> **Priority**: Level 2 in the canonical source hierarchy (after `docs/architecture.pdf`).

---

## Project Purpose

Automated compliance verification for stock brokers against SEBI regulatory circulars. Built for the **SEBI Securities Market TechSprint Problem Statement 2**.

The system ingests SEBI circular PDFs, extracts obligations as hybrid finite state machines, evaluates broker telemetry data against those obligations, and produces verifiable audit scoreboards with hash-chain integrity.

---

## Architecture Summary

```
                ┌── Regulatory Knowledge Layer (V2) ─────────────────────┐
                │                                                        │
                │  CircularRegistry (JSON)  ──  ChromaVectorStore        │
                │  Multi-circular indexing  ──  Semantic Search           │
                │  Cross-circular retrieval ──  Provenance metadata      │
                │                                                        │
                └────────────────────────┬───────────────────────────────┘
                                         │
PDF Parser (Node 1) → FSM Extractor (Node 2) → HITL Gate → Assertion Evaluator (Node 3) → Scoreboard (Node 4)
       ✅                    ✅                       ✅                  ✅ (deterministic)            ✅
                                                                                                               │
                                                        ┌────────────────────────────────────────────────────┘
                                                        ▼
                                            FastAPI + LangGraph Orchestration ✅
                                                        │
                                                        ▼
                                            React Dashboard ✅
                                                        │
                                                        ▼
                                            End-to-End Demo + Validation ✅
```

- **Regulatory Knowledge Layer (V2)**: Circular registry, multi-circular indexing, cross-circular retrieval, chunk provenance metadata.
- **Node 1 (PDF Parser)**: LLM-assisted — extracts structured obligation clauses from circular PDFs. Supports full-text (V1) and chunked (V2) input paths.
- **Node 2 (FSM Extractor)**: LLM-assisted — transforms parsed clauses into HybridFSM representations.
- **HITL Gate**: Deterministic — human reviews/approves/rejects/amends extracted FSMs before evaluation.
- **Node 3 (Assertion Evaluator)**: Strictly deterministic — matches telemetry against approved LockedFSMs. **No LLM allowed.**
- **Node 4 (Scoreboard Generator)**: Formatting only — aggregates verdicts with SHA-256 hash-chain integrity.
- **Frontend**: React 19 + TypeScript + Vite + Zustand dashboard.

## Implementation Milestones

| Milestone | Component | Status |
|-----------|-----------|--------|
| M0 | Foundation (models, state, utils) | ✅ Complete |
| M1 | PDF Parser (Node 1) | ✅ Complete |
| M2 | FSM Extractor (Node 2) | ✅ Complete |
| M3 | Hash Chain Utility | ✅ Complete |
| M4 | HITL Gate | ✅ Complete |
| M5 | Assertion Evaluator (Node 3) | ✅ Complete |
| M6 | Scoreboard Generator (Node 4) | ✅ Complete |
| M7 | Backend API + LangGraph Orchestration | ✅ Complete |
| M8 | Frontend Dashboard | ✅ Complete |
| M9 | End-to-End Demo & Final Validation | ✅ Complete |
| V1.0.1 | Interactive Demo Fixes + Enterprise UI | ✅ Complete (`8845e8a`) |
| V1.0.2 | Final Demo Polish + Evaluator Fix + Explanation UX | ✅ Complete (`401b659`) |
| V2 M1 | Regulatory RAG Architecture | ✅ Complete (`32149c8`) |
| V2 M2 | Multi-Circular Retrieval | ✅ Complete |
| V2 M3 | Evidence Traceability | ✅ Complete (`1754c66`) |
| V2 M4 | PostgreSQL Migration | ✅ Complete (`f231741`) |
| V2 M5 | Compliance Scenario Library | Pending |
| V2 M6 | Tamper-Evident Audit Log | Pending |

## Scope

- Parse SEBI circular PDFs and extract compliance obligations.
- Model obligations as hybrid finite state machines with timeline rules.
- Human-in-the-loop review of extracted FSMs (approve/reject/amend).
- Evaluate broker telemetry data against FSMs (deterministic only).
- Generate verifiable audit scoreboards with hash-chain integrity.
- REST API for pipeline trigger, HITL review, telemetry ingest, reports, and resume.
- RAG API for circular indexing, semantic search, multi-circular management.
- Circular Registry for tracking indexed circulars (document hash, index version).
- CLI for indexing, search, multi-circular management.
- React dashboard for compliance status visualization.
- 642 tests (410 V1 + 232 V2).
- Deterministic explanation column in audit reports.
- Evidence traceability chain: Circular → Page → Chunk → Obligation → FSM → Verdict (V2 M3).
- PDF bounding-box extraction with pdfplumber for source text highlighting (V2 M3).
- PDF.js viewer with clickable citation regions (V2 M3).
- PostgreSQL persistence: 9 tables, 6 repositories, Alembic migrations (V2 M4).
- Graceful degradation to in-memory stores + JSON fallback when PostgreSQL unavailable (V2 M4).
- LLM response caching for deterministic extraction across runs (V2 M4).
- Validated end-to-end against official SEBI circular `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57`.

## Important Constraints

| Constraint | Rule |
|------------|------|
| Node 3 LLM | **Never** call an LLM. All evaluation is deterministic. |
| Human approval | Required before Node 3 executes (HITL gate). |
| Determinism | Execution against operational data must be deterministic. |
| Auditability | Every compliance finding must be traceable to the originating regulation. |
| Explainability | All verdicts must be explainable from the FSM + telemetry alone. |
| V1 freeze | Do not modify V1 pipeline, models, evaluator, or API. |
| V1 backward compat | `use_rag=False` (default) — identical V1 path. |

## API Endpoints (V2 M2)

| Method | Path | Purpose | Added |
|--------|------|---------|-------|
| `GET` | `/health` | Health check | M7 |
| `POST` | `/api/pipeline/trigger` | Start pipeline run (supports `use_rag`) | M7 → V2 M1 |
| `GET` | `/api/pipeline/status/{run_id}` | Check run status | M7 |
| `GET` | `/api/pipeline/result/{run_id}` | Get compliance results | M7 |
| `POST` | `/api/pipeline/{run_id}/resume` | Resume pipeline after HITL review | V1.0.1 |
| `GET` | `/api/pipeline/hitl` | List HITL review items | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approve obligation | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Reject obligation | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amend obligation | M7 |
| `POST` | `/api/telemetry/ingest` | Ingest broker events | M7 |
| `GET` | `/api/telemetry/query` | Query telemetry | M7 |
| `GET` | `/api/reports/generate/{run_id}` | Generate audit report | M7 → V1.0.2 |
| `GET` | `/api/reports/{report_id}` | Retrieve report | M7 → V1.0.2 |
| `POST` | `/api/rag/index` | Index circular into Chroma | V2 M1 |
| `POST` | `/api/rag/query` | Semantic search | V2 M1 |
| `GET` | `/api/rag/status/{circular_ref}` | Index status | V2 M1 |
| `GET` | `/api/rag/circulars` | List all indexed circulars | **V2 M2** |
| `POST` | `/api/rag/index-all` | Batch-index circulars | **V2 M2** |
| `DELETE` | `/api/rag/circular/{circular_ref}` | Remove circular from index | **V2 M2** |
| `GET` | `/api/evidence/{verdict_id}` | Full evidence chain | **V2 M3** |
| `GET` | `/api/evidence/fsm/{locked_fsm_id}` | FSM source chunks | **V2 M3** |
| `GET` | `/api/chunks/{chunk_id}/positions` | Bounding-box positions | **V2 M3** |
| `GET` | `/api/circulars/{circular_ref}/pdf` | Serve source PDF | **V2 M3** |

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, LangGraph |
| RAG | Chroma (dev), bge-small-en-v1.5 embeddings, sentence-transformers |
| Circular Registry | JSON-file (dev) + PostgreSQL (prod) |
| Database | PostgreSQL 16 + asyncpg + SQLAlchemy 2.0 + Alembic |
| Frontend | TypeScript, React 19, Vite, Zustand |
| Database | In-memory stores + JSON files (V2) → PostgreSQL + pgvector (V2 M4) |
| Integrity | SHA-256 hash-chain |
| AI | DeepSeek v4 Pro (Nodes 1, 2) |
| Testing | pytest (490 tests) |
