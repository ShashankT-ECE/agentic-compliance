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
```

- **Node 1 (PDF Parser)**: LLM-assisted — extracts structured obligation clauses from circular PDFs using pdfplumber + DeepSeek API. ✅ M1
- **Node 2 (FSM Extractor)**: LLM-assisted — transforms parsed clauses into hybrid FSM representations (state machine + timeline conditions). ✅ M2
- **HITL Gate**: Human reviews and approves/corrects extracted FSMs. LockedFSM records sealed into hash chain. **No LLM allowed.** ✅ M4
- **Node 3 (Assertion Evaluator)**: Strictly deterministic — matches event-based telemetry against locked FSMs. **No LLM allowed.** 🔜 M5
- **Node 4 (Scoreboard Generator)**: Formatting only — aggregates results into hash-chained audit scoreboard. 🔜 M6

The pipeline is orchestrated via LangGraph as a directed acyclic graph with a conditional HITL edge (M7).

## V1 Scope (2026-07-03)

| Aspect | Decision |
|--------|----------|
| **Canonical circular** | SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57 (28 April 2025) — Margin Collection Timelines |
| **Target obligation** | Timeline-based (deadline compliance: T+1, T+3, etc.) |
| **FSM model** | Hybrid — state machine wrapper with embedded timeline conditions |
| **Telemetry** | Event-based logs conforming to production schema |
| **HITL gate** | Human reviews extracted FSMs before Node 3 executes |
| **Hash chain** | Required for V1 demo |
| **Strategy** | Depth-first: one circular, one broker, full stack end-to-end |

## Important Constraints

| Constraint | Rule |
|------------|------|
| Node 3 LLM | **Never** call an LLM. All evaluation is deterministic. |
| Human approval | Required before Node 3 executes (FSM review gate). |
| Determinism | Execution against operational data must be deterministic. |
| Auditability | Every compliance finding must be traceable to the originating regulation. |
| Explainability | All verdicts must be explainable from the FSM + telemetry alone. |
| Circular source | Obligations are always extracted from real SEBI circulars (never hand-authored). |
| Telemetry format | Pipeline consumes event logs following the production schema from Day 1. |
| HITL node LLM | HITL gate (M4) must never call an LLM — all logic is deterministic. |

## Current Implementation Status

| Milestone | Status | Date | Tests |
|-----------|--------|------|-------|
| M0 — Foundation | ✅ Complete | 2026-07-03 | 68 |
| M1 — PDF Parser | ✅ Complete | 2026-07-03 | 35 |
| M2 — FSM Extractor | ✅ Complete | 2026-07-03 | 34 |
| M3 — Hash Chain | ✅ Complete | 2026-07-03 | 20 |
| M4 — HITL Gate | ✅ Complete | 2026-07-03 | 46 |
| M5 — Evaluator | 🔜 Next | — | — |
| M6 — Scoreboard | ⏳ Pending | — | — |
| M7 — API + Pipeline | ⏳ Pending | — | — |
| M8 — Frontend | ⏳ Pending | — | — |
| M9 — E2E Demo | ⏳ Pending | — | — |

**Total: 203 tests, zero failures, zero warnings.**

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI, LangGraph |
| Frontend | TypeScript, React, Vite, Zustand |
| Database | PostgreSQL (async via SQLAlchemy) |
| Integrity | SHA-256 hash-chain locking for FSM snapshots and audit trails (M3) |
| PDF extraction | pdfplumber (M1) |
| LLM | DeepSeek API via swappable LLMClient abstraction (M1) |
| Testing | pytest, pytest-asyncio, httpx (FastAPI TestClient) |
| Deployment | Docker Compose, GitHub Actions |

## Key Directories

| Directory | Contents |
|-----------|----------|
| `backend/app/models/` | `obligation.py`, `telemetry.py`, `fsm.py`, `verdict.py`, `scoreboard.py`, `locked_fsm.py` |
| `backend/app/pipeline/` | `state.py`, `nodes/parser.py`, `nodes/fsm_extractor.py`, `nodes/hitl_gate.py` |
| `backend/app/utils/` | `hash_chain.py`, `llm_client.py`, `pdf_ingest.py` |
| `backend/app/prompts/` | `parser_prompt.md`, `fsm_extractor_prompt.md` |
| `backend/app/api/routes/` | `pipeline.py` (HITL endpoints) |
| `backend/data/extracted/` | M2 FSM output (per-circular JSON + index) |
| `backend/data/locked_fsms/` | M4 LockedFSM records (per-run JSON + pipeline state + review log + hash chain) |
| `backend/tests/` | 5 test files + fixtures |

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

## Key Reference Files

| File | Purpose |
|------|---------|
| `memory/project_roadmap.md` | Permanent implementation plan with milestones and completion criteria |
| `memory/decision_log.md` | Architectural decision records |
| `memory/graphify_handoff.md` | Pipeline graph topology and state schema |
| `memory/current_task.md` | Exact resume point for the current session |
| `memory/session_handoff.md` | Last session summary |
| `memory/progress.md` | High-level checkbox tracker |
| `CLAUDE.md` | Permanent operating manual |
