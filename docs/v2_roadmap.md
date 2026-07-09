# V2 Roadmap — Regulatory Intelligence Platform

> **Version**: 2.0 — 2026-07-09
> **Status**: Active — V2 M1 + M2 complete, M3 in design
> **Canonical source of truth** for V2 architecture decisions

---

## V2 Vision

Evolve from a single-circular compliance checker into a **production-grade regulatory
intelligence platform** that ingests the full SEBI regulatory corpus, extracts obligations
at scale, tracks regulatory change over time, and evaluates broker compliance with
deterministic, auditable, and explainable verdicts — every finding traceable back to
the exact regulatory text that produced it.

---

## Architecture (Post-M2)

Two domains, cleanly separated:

```
┌──────────────────────────────────────────────────────────────────┐
│                REGULATORY KNOWLEDGE LAYER                         │
│                                                                  │
│  Multi-Circular Retrieval                                        │
│  Evidence Traceability                                           │
│  Document/Circular Identity                                      │
│  Chunk Metadata                                                  │
│  Vector Retrieval                                                │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
                    Protocol Parser (LLM)
                             │
                             ▼
                      Obligation IR
                             │
                             ▼
                   FSM Generator (LLM)
                             │
                             ▼
                   Human Approval (HITL)
                             │
                             ▼
                      Locked FSM
                             │
                             ▼
                Deterministic Evaluator (Node 3)
                             │
                             ▼
                      Audit Report
                             │
                             ▼
                Tamper-Evident Audit Log
```

**Provenance chain:**

```
Circular → Page → Section → Chunk → Parser → Obligation → FSM → Evaluation → Verdict
```

---

## Architectural Principles (carried forward from V1)

| # | Principle | Constraint |
|---|-----------|------------|
| P1 | Deterministic evaluation | Node 3 must never call an LLM, make HTTP requests, or perform non-deterministic operations |
| P2 | Human-in-the-loop | Human approval required before any FSM enters the evaluator |
| P3 | Full audit trail | Every compliance finding must be traceable to the originating regulation text |
| P4 | Explainability | Every verdict must be explainable from the FSM + telemetry alone |
| P5 | Backward compatibility | V1 API surface preserved; all 410 V1 tests continue to pass |
| P6 | Incremental delivery | Each milestone produces a working, testable increment |
| P7 | Abstraction only when needed | Prefer extending existing code over rewriting; add abstractions only when multiple backends exist |

---

## Milestone Map

```
V2 M6: Tamper-Evident Audit Log
 │
V2 M5: Compliance Scenario Library
 │
V2 M4: PostgreSQL Migration
 │
V2 M3: Evidence Traceability   ← NEXT (in design)
 │
V2 M2: Multi-Circular Retrieval ✅
 │
V2 M1: Regulatory RAG Architecture ✅
 │
V1.0.2 (frozen baseline)
```

---

## M1 — Regulatory RAG Architecture ✅ COMPLETE

**Delivered**: Chroma vector store, bge-small embeddings (384-dim), topic-level chunking (200 chunks from 399-page Master Circular), retrieval pipeline, parser integration behind `use_rag` feature flag, YAML configuration, CLI.

**Commit**: `32149c8`

---

## M2 — Multi-Circular Retrieval ✅ COMPLETE

### Objective

Index multiple SEBI circulars simultaneously. Circular registry, multi-circular retrieval, cross-circular search, unified APIs for management.

### Deliverables

1. **CircularRegistry** — `CircularRegistryBackend` protocol (4 methods) + `JsonCircularRegistry` implementation. Records carry `document_hash` (SHA-256) and `index_version`.
2. **Module-level `build_record()` factory** — not tied to any persistence backend. Works with JSON, PostgreSQL, or future implementations.
3. **`list_circulars()` on ChromaVectorStore** — returns unique circular refs from Chroma metadata.
4. **3 new API endpoints**: `GET /circulars`, `POST /index-all`, `DELETE /circular/{ref:path}`.
5. **3 new CLI commands**: `list`, `index-all`, `delete`.
6. **`_encode_sync` bug fix** — lazily loads model on first call.
7. **Chunk provenance metadata preserved** — all retrieval paths carry full `ChunkMetadata`.

### Files created

| File | Purpose |
|------|---------|
| `backend/app/rag/circular_registry.py` | `CircularRecord`, `CircularRegistryBackend`, `JsonCircularRegistry`, `build_record()` |
| `backend/tests/test_rag_circular_registry.py` | 23 tests |
| `backend/tests/test_rag_multi_circular.py` | 10 tests |

### Files modified

| File | Change |
|------|--------|
| `backend/app/rag/__init__.py` | New exports |
| `backend/app/rag/vector_store.py` | `list_circulars()` |
| `backend/app/rag/embedder.py` | `_encode_sync` lazy-load fix |
| `backend/app/api/routes/rag.py` | 3 endpoints + registry integration |
| `backend/app/cli.py` | 3 commands |
| `backend/tests/test_rag_retrieval.py` | +6 cross-circular + provenance tests |
| `backend/tests/test_rag_vector_store.py` | +4 list_circulars tests |

### Test count: 490 (was 447, +43)

---

## M3 — Evidence Traceability (In Design)

### Objective

Every compliance decision must be traceable back to the exact regulatory text —
page number, chunk, and highlighted passage — so auditors can verify findings
without re-reading the entire circular.

### Key deliverables

1. **EvidenceReference schema** — links verdicts to source chunks with page/position data.
2. **Page-level citation** — every chunk carries page number(s) from PDF extraction.
3. **Bounding-box extraction** — pdfplumber or PyMuPDF extracts word-level positions.
4. **Provenance pipeline** — evidence flows through parser → obligation → FSM → verdict.
5. **Backend API** — `GET /api/evidence/{verdict_id}` returns source citations.
6. **Frontend PDF.js viewer** — renders circular PDF with highlighted passages.
7. **Clickable citations** — click a verdict → open PDF at the exact paragraph.

See M3 design document for full details.

---

## M4 — PostgreSQL Migration

### Objective

Replace in-memory stores and JSON files with PostgreSQL. Prepare for pgvector.

### Key deliverables

1. Replace `_run_store` (in-memory dict) with SQLAlchemy models.
2. Replace `_report_store` (in-memory dict) with DB.
3. Replace `JsonCircularRegistry` with `PostgresCircularRegistry`.
4. Add Alembic migrations.
5. Docker Compose with PostgreSQL service.
6. All 490 tests pass against PostgreSQL.

### Do NOT change evaluator behaviour.

---

## M5 — Compliance Scenario Library

### Objective

Replace synthetic telemetry with a reusable scenario library.

### Scenario types

| Scenario | Description |
|----------|-------------|
| Clean Pass | All obligations met within deadlines |
| Clean Fail | All obligations missed |
| Boundary Pass | Deadline met at exact cutoff |
| Boundary Fail | Deadline missed by 1 unit |
| Exception Cases | Edge cases (grace periods, partial compliance) |
| Missing Events | No telemetry for expected events |
| Out-of-order Events | Events arriving in non-chronological order |
| Duplicate Events | Same event_id submitted twice |

Every scenario becomes a regression test.

---

## M6 — Tamper-Evident Audit Log

### Objective

Implement Merkle-style hash-chained audit logs. Every report cryptographically
verifiable. For audit integrity, not blockchain.

### Key deliverables

1. Merkle tree over verdicts + evidence references.
2. Root hash published in each audit report.
3. Verification endpoint: `POST /api/audit/verify/{report_id}`.
4. Incremental proof generation (prove one verdict without revealing others).

---

## V1 Preservation Guarantees

| Guarantee | Enforcement |
|-----------|-------------|
| Node 3 deterministic | AST-level verification in CI (carried forward) |
| HITL gate preserved | No code removal from `hitl_gate.py` |
| 410 V1 tests pass | Run on every commit; fail = block merge |
| V1 API backward compatible | Existing endpoints unchanged; new endpoints are additive |
| use_rag=False default | V1 full-PDF path is the default |

---
