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

- **Node 1 (PDF Parser)**: LLM-assisted — extracts structured obligation clauses from circular PDFs.
- **Node 2 (FSM Extractor)**: LLM-assisted — transforms parsed clauses into hybrid FSM representations.
- **HITL Gate**: Human reviews and approves/corrects extracted FSMs before deterministic evaluation runs.
- **Node 3 (Assertion Evaluator)**: Strictly deterministic — matches event-based telemetry against FSMs. **No LLM allowed.**
- **Node 4 (Scoreboard Generator)**: Formatting only — aggregates results into audit scoreboard with hash-chain integrity.

The pipeline is orchestrated via LangGraph as a directed acyclic graph with a conditional HITL edge.

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

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, LangGraph |
| Frontend | TypeScript, React, Vite, Zustand |
| Database | PostgreSQL (async via SQLAlchemy) |
| Integrity | Hash-chain locking for FSM snapshots and audit trails |
| Deployment | Docker Compose, GitHub Actions |
| AI | DeepSeek API (via Claude Code) |

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
| `CLAUDE.md` | Permanent operating manual |
