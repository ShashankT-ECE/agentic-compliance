# Project Handoff

> **Purpose**: Permanent project overview. Updated ONLY when the project itself changes.
> **Priority**: Level 2 in the canonical source hierarchy (after `docs/architecture.pdf`).

---

## Project Purpose

Automated compliance verification for stock brokers against SEBI regulatory circulars. Built for the **SEBI Securities Market TechSprint Problem Statement 2**.

The system ingests SEBI circular PDFs, extracts obligations as finite state machines (FSMs), evaluates broker telemetry data against those FSMs, and produces verifiable audit scoreboards with hash-chain integrity.

## Architecture Summary

```
PDF Parser (Node 1) → FSM Extractor (Node 2) → HITL Gate → Assertion Evaluator (Node 3) → Scoreboard (Node 4)
       ✅ M1                ✅ M2               ✅ M4           ✅ M5 (deterministic)           ✅ M6
                                                                                                    │
                                                          ┌─────────────────────────────────────────┘
                                                          ▼
                                              FastAPI + LangGraph Orchestration (M7 ✅)
                                                          │
                                                          ▼
                                              React Dashboard (M8 ✅)
                                                          │
                                                          ▼
                                              End-to-End Demo + Validation (M9 ✅)
```

- **Node 1 (PDF Parser)**: LLM-assisted — extracts structured obligation clauses from circular PDFs.
- **Node 2 (FSM Extractor)**: LLM-assisted — transforms parsed clauses into HybridFSM representations.
- **HITL Gate**: Deterministic — human reviews/approves/rejects/amends extracted FSMs before evaluation.
- **Node 3 (Assertion Evaluator)**: Strictly deterministic — matches telemetry against approved LockedFSMs. **No LLM allowed.**
- **Node 4 (Scoreboard Generator)**: Formatting only — aggregates verdicts into the audit scoreboard with hash-chain integrity.
- **Node 5 (Orchestration)**: LangGraph DAG + FastAPI REST API with 12 endpoints.
- **Frontend**: React + TypeScript + Vite dashboard with pipeline trigger, HITL review, compliance reports, FSM visualization, and telemetry table.

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
| V2 | Production Hardening | ⬅ NEXT |

## Scope

- Parse SEBI circular PDFs and extract compliance obligations.
- Model obligations as hybrid finite state machines with timeline rules.
- Human-in-the-loop review of extracted FSMs (approve/reject/amend).
- Evaluate broker telemetry data against FSMs (deterministic only).
- Generate verifiable audit scoreboards with hash-chain integrity.
- REST API for pipeline trigger, HITL review, telemetry ingest, and reports.
- React dashboard for compliance status visualization.
- End-to-end demo script with MockLLMClient (no API key needed).
- 26 integration tests validating the full pipeline flow.

## Important Constraints

| Constraint | Rule |
|------------|------|
| Node 3 LLM | **Never** call an LLM. All evaluation is deterministic. |
| Human approval | Required before Node 3 executes (HITL gate). |
| Determinism | Execution against operational data must be deterministic. |
| Auditability | Every compliance finding must be traceable to the originating regulation. |
| Explainability | All verdicts must be explainable from the FSM + telemetry alone. |

## API Endpoints (M7)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `POST` | `/api/pipeline/trigger` | Start pipeline run |
| `GET` | `/api/pipeline/status/{run_id}` | Check run status |
| `GET` | `/api/pipeline/result/{run_id}` | Get compliance results |
| `GET` | `/api/pipeline/hitl` | List HITL review items |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approve FSM |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Reject FSM |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amend FSM |
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
| Integrity | SHA-256 hash-chain (M3) |
| Deployment | Docker Compose (basic) → full-stack (V2) |
| AI | DeepSeek API (Nodes 1, 2) — swappable via LLMClient abstraction |
| Testing | pytest (389 tests), 26 integration tests |

## Coding Standards

- Production-ready, strongly typed, modular, reusable.
- Minimal duplication with comprehensive logging and clear error handling.
- Appropriate tests (unit + integration) and comments where useful.
- No placeholder business logic unless explicitly requested.
- Python: type hints everywhere, Pydantic for validation.
- TypeScript: strict mode, proper interfaces/types.

## Developers

- **Shashank** (Linux)
- **Friend** (Windows + WSL2)

Both use Claude Code with the DeepSeek API. Work is asynchronous — no scheduled sessions.
