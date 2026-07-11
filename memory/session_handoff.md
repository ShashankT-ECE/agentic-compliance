# Session Handoff

---

## Session Overview

| Field | Value |
|-------|-------|
| **Date** | 2026-07-11 |
| **Developer** | Brad (Friend — Windows + WSL2) |
| **Branch** | `dev` |
| **Latest Commits** | `b71e86d` (perf), `1754c66` (M3+M4), `f231741` (M4 frontend), `32149c8` (M1) |
| **Repository State** | 642 tests pass. Frontend builds clean (93 modules). Doc polish in progress. |
| **Overall Status** | **V1.0.2 FROZEN — V2 M1–M4 COMPLETE — Hackathon polish in progress** |

---

## What Was Done — V2 M3 (Evidence Traceability)

### Architecture

Evidence models (`EvidenceReference`, `ChunkCitation`, `PageRegion`, `Rectangle`, `ObligationSource`, `FSMProvenance`) linking verdicts back to source chunks and PDF page regions.

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Evidence models | `app/models/evidence.py` | Provenance chain Pydantic models |
| Attribution strategy | `app/pipeline/attribution.py` | Protocol-based chunk→obligation mapping |
| Evidence service | `app/pipeline/evidence_service.py` | Orchestrates evidence assembly |
| Bbox extractor | `app/utils/bbox_extractor.py` | pdfplumber word-level position extraction |
| Evidence API | `app/api/routes/evidence.py` | 4 endpoints (verdict evidence, FSM evidence, chunk positions, PDF serving) |
| PDF.js viewer | `frontend/src/components/PDFViewer/` | In-browser PDF rendering with highlights |
| Evidence panel | `frontend/src/components/EvidencePanel/` | Provenance chain display |
| Evidence page | `frontend/src/pages/evidence.tsx` | Side-by-side PDF + evidence viewer |

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| **Conservative attribution** | All input chunks attributed to all output obligations. Safest for audit. |
| **AttributionStrategy Protocol** | Swappable without changing downstream code. |
| **Evidence models independent of PDF** | `PageRegion`/`Rectangle` not in `ChunkMetadata` — keep RAG and evidence layers decoupled. |
| **Bbox cache at `data/bbox/`** | Disk-cached per chunk_id. Extract once, serve many times. |
| **Batch bbox extraction** | Open PDF once, extract all chunks in one pass. |

---

## What Was Done — V2 M4 (PostgreSQL Migration)

### Architecture

9 SQLAlchemy ORM models replacing in-memory stores. 6 repository classes with PG-first, in-memory-fallback pattern.

### Components

| Component | File | Purpose |
|-----------|------|---------|
| DB models | `app/db/models.py` | 9 ORM models (circular_records, pipeline_runs, verdicts, locked_fsms, hitl_review_log, reports, evidence_references, rag_chunks, telemetry_events) |
| Repository base | `app/db/repos/base.py` | Base repository pattern |
| Circular repo | `app/db/repos/circular_repo.py` | Circular CRUD |
| Pipeline run repo | `app/db/repos/pipeline_run_repo.py` | Pipeline run persistence |
| Locked FSM repo | `app/db/repos/locked_fsm_repo.py` | LockedFSM persistence |
| HITL review repo | `app/db/repos/hitl_review_repo.py` | Append-only audit log |
| RAG chunk repo | `app/db/repos/rag_chunk_repo.py` | Chunk text persistence |
| Alembic migration | `alembic/versions/001_initial_schema.py` | Full initial schema |
| Database config | `app/database.py` | Async SQLAlchemy engine + session |

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| **PG-first, Chroma-fallback** | PG is the authoritative store for text/metadata. Chroma for embeddings only. |
| **Graceful degradation** | System runs fully (with in-memory stores + JSON files) when PG is unavailable. |
| **state_blob JSON column** | Full `CompliancePipelineState` serialized as JSON in pipeline_runs. Complete audit trail. |
| **hitl_review_log INSERT-only** | Immutable audit trail. Never UPDATE or DELETE. |

---

## M5–M6 — Pending

| M | Name | Key Deliverables |
|---|------|-----------------|
| M5 | Compliance Scenario Library | 8 scenario types (clean pass/fail, boundary, exception, missing events, out-of-order, duplicates). Each becomes a regression test. |
| M6 | Tamper-Evident Audit Log | Merkle tree over verdicts, root hash in reports, incremental proof generation. |

---

## Startup Instructions

```bash
cd /home/bradha/agentic-compliance
git checkout dev
git pull origin dev

# Kill stale processes
fuser -k 8000/tcp 2>/dev/null
fuser -k 5173/tcp 2>/dev/null

# Verify
cd backend
source .venv/bin/activate
python -m pytest tests/ -v        # 642 tests
cd ../frontend
npm run build                      # 93 modules

# Start PostgreSQL
docker compose up -d db

# Start backend
cd ../backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start frontend
cd ../frontend && npm run dev
```

**CRITICAL RULES:**
- Do not redesign M0–M4 — all milestones are independently verified.
- V1 is frozen — do not modify pipeline, models, evaluator, or API.
- Node 3 safety gate (no LLM) must never be violated.
- All 642 tests must continue to pass.
- `use_rag=False` default — V1 path unchanged.
- Server must be restarted after any backend code change.
