# Project Handoff

> **Purpose**: Permanent project overview. Updated ONLY when the project itself changes.
> **Priority**: Level 2 in the canonical source hierarchy (after `docs/architecture.pdf`).

---

## Project Purpose

Automated compliance verification for stock brokers against SEBI regulatory circulars. Built for the **SEBI Securities Market TechSprint Problem Statement 2**.

The system ingests SEBI circular PDFs, extracts obligations as hybrid finite state machines, evaluates broker telemetry data against those obligations, and produces verifiable audit scoreboards with hash-chain integrity.

## Architecture Summary

```
PDF Parser (Node 1) → FSM Extractor (Node 2) → HITL Gate → Assertion Evaluator (Node 3) → Scoreboard (Node 4)
       ✅                ✅                        ✅                  ✅ (deterministic)            ✅
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

- **Node 1 (PDF Parser)**: LLM-assisted — extracts structured obligation clauses from circular PDFs. Uses DeepSeek v4 Pro with 16384 max_tokens + truncation recovery.
- **Node 2 (FSM Extractor)**: LLM-assisted — transforms parsed clauses into HybridFSM representations.
- **HITL Gate**: Deterministic — human reviews/approves/rejects/amends extracted FSMs before evaluation.
- **Node 3 (Assertion Evaluator)**: Strictly deterministic — matches telemetry against approved LockedFSMs. **No LLM allowed.** AST-verified. V1.0.2: `determine_compliance_status()` trusts FSM `current_state`; `overdue_transition` from timeline rules fed back into FSM via `transition_to()`.
- **Node 4 (Scoreboard Generator)**: Formatting only — aggregates verdicts into the audit scoreboard with SHA-256 hash-chain integrity.
- **Node 5 (Orchestration)**: LangGraph DAG + FastAPI REST API with 13 endpoints.
- **Frontend**: React 19 + TypeScript + Vite + Zustand dashboard with pipeline trigger, HITL review, compliance reports, workflow visualization, and telemetry table.

The pipeline is orchestrated via LangGraph as a directed acyclic graph with a conditional HITL branch.

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
| V1.0.1 | Interactive Demo Fixes + Enterprise UI | ✅ Complete (committed `8845e8a`) |
| V1.0.2 | Final Demo Polish + Evaluator Fix + Explanation UX | ✅ Complete (committed `401b659`) |
| V2 | Production Hardening | ⬅ NEXT — roadmap defined in `docs/v2_roadmap.md` |

## V2 Milestones (see `docs/v2_roadmap.md` for full details)

| M | Name | Summary |
|---|------|---------|
| M1 | Regulatory RAG Architecture | Document store, circular registry, retrieval pipeline foundation |
| M2 | PDF Chunking Strategy | Section-boundary-aware chunking for regulatory PDFs |
| M3 | Metadata Extraction | Circular identity, entity classification, supersession chains |
| M4 | Vector Database | Chroma (dev) → pgvector (prod), embedding pipeline |
| M5 | Hybrid Retrieval (BM25 + Vector) | Reciprocal rank fusion, re-ranking, retrieval benchmarks |
| M6 | Multi-Obligation Extraction | Section-by-section extraction, dedup, merge, quality scoring |
| M7 | Cross-Reference Resolution | Parse + resolve inter-circular legal references |
| M8 | Diff Agent | Compare circular versions, classify changes, assess impact |
| M9 | Multi-Circular Support | Cross-circular obligation index, conflict detection, unified scoreboard |
| M10 | Production Deployment | PostgreSQL, pgvector, auth, Docker Compose, CI/CD, observability |

**Target**: ~847 tests across 10 milestones. 6 milestones on the critical path.

## Scope

- Parse SEBI circular PDFs and extract compliance obligations.
- Model obligations as hybrid finite state machines with timeline rules.
- Human-in-the-loop review of extracted FSMs (approve/reject/amend).
- Evaluate broker telemetry data against FSMs (deterministic only).
- Generate verifiable audit scoreboards with hash-chain integrity.
- REST API for pipeline trigger, HITL review, telemetry ingest, reports, and resume.
- React dashboard for compliance status visualization.
- End-to-end demo script with MockLLMClient (no API key needed).
- Interactive browser demo via HITL review page.
- Real DeepSeek v4 Pro API integration with truncation recovery.
- 37 integration tests validating the full pipeline flow.
- 410 total tests.
- Deterministic explanation column in audit reports (derived from evidence trail).
- Timeline overdue transitions integrated into FSM evaluation (state/status consistency).
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

## API Endpoints (V1.0.2)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `POST` | `/api/pipeline/trigger` | Start pipeline run |
| `GET` | `/api/pipeline/status/{run_id}` | Check run status |
| `GET` | `/api/pipeline/result/{run_id}` | Get compliance results |
| `POST` | `/api/pipeline/{run_id}/resume` | Resume pipeline after HITL review |
| `GET` | `/api/pipeline/hitl` | List HITL review items (disk-authoritative) |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approve obligation |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Reject obligation |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amend obligation |
| `POST` | `/api/telemetry/ingest` | Ingest broker events |
| `GET` | `/api/telemetry/query` | Query telemetry |
| `GET` | `/api/reports/generate/{run_id}` | Generate audit report |
| `GET` | `/api/reports/{report_id}` | Retrieve report |

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, LangGraph |
| Frontend | TypeScript, React 19, Vite, Zustand |
| Database | In-memory stores (V1) → PostgreSQL async via SQLAlchemy (V2) |
| Integrity | SHA-256 hash-chain |
| Deployment | Docker Compose (basic) → full-stack (V2) |
| AI | DeepSeek v4 Pro (Nodes 1, 2) — swappable via LLMClient abstraction |
| Testing | pytest (410 tests), 37 integration tests |

## Coding Standards

- Production-ready, strongly typed, modular, reusable.
- Minimal duplication with comprehensive logging and clear error handling.
- Appropriate tests (unit + integration) and comments where useful.
- No placeholder business logic unless explicitly requested.
- Python: type hints everywhere, Pydantic for validation.
- TypeScript: strict mode, proper interfaces/types.

## Developers

- **Shashank** (Linux)
- **Brad** (Friend — Windows + WSL2)

Both use Claude Code with the DeepSeek API. Work is asynchronous — no scheduled sessions.

## Git Branches (as of 2026-07-08)

| Branch | Status | Notes |
|--------|--------|-------|
| `dev` | ✅ Active | V1.0.2 committed (`401b659`), pushed to `origin/dev`. V1 frozen. |
| `backup-m5` | ⚠️ Stale | Early-development stubs, 27 commits behind dev, do NOT merge |
| `docs-memory-sync` | ✅ Synced | Fast-forwarded to dev |
| `docs-v1-complete` | ✅ Synced | Fast-forwarded to dev |
| `m5-rebuild` | ✅ Synced | Fast-forwarded to dev |
| `m6-scoreboard` | ✅ Synced | Fast-forwarded to dev |
| `m7-orchestration` | ✅ Synced | Fast-forwarded to dev |
| `m8-frontend` | ✅ Synced | Fast-forwarded to dev |

## V2 Roadmap — Next Steps

See `progress.md` for detailed V2 Roadmap. Key areas:
- 399-page Master Circular support (chunked parsing, token budget)
- PostgreSQL persistence (replace in-memory stores)
- PDF upload UX (replace free-text path input)
- Docker Compose full-stack deployment
- Frontend test suite (Vitest + React Testing Library)
- Authentication (API keys / JWT)
- Production hardening (rate limiting, monitoring, logging)
- CI/CD pipeline
