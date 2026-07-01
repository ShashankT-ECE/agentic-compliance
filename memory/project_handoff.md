# Project Handoff

> **Purpose**: Permanent project overview. Updated ONLY when the project itself changes.
> **Priority**: Level 2 in the canonical source hierarchy (after `docs/architecture.pdf`).

---

## Project Purpose

Automated compliance verification for stock brokers against SEBI regulatory circulars. Built for the **SEBI Securities Market TechSprint Problem Statement 2**.

The system ingests SEBI circular PDFs, extracts obligations as finite state machines (FSMs), evaluates broker telemetry data against those FSMs, and produces verifiable audit scoreboards with hash-chain integrity.

## Architecture Summary

```
PDF Parser (Node 1) → FSM Extractor (Node 2) → Assertion Evaluator (Node 3) → Scoreboard (Node 4)
```

- **Node 1 (PDF Parser)**: LLM-assisted — extracts structured obligation clauses from circular PDFs.
- **Node 2 (FSM Extractor)**: LLM-assisted — transforms parsed clauses into FSM representations.
- **Node 3 (Assertion Evaluator)**: Strictly deterministic — matches telemetry against FSMs. **No LLM allowed.**
- **Node 4 (Scoreboard Generator)**: Formatting only — aggregates results into the audit scoreboard.

The pipeline is orchestrated via LangGraph as a directed acyclic graph.

## Scope

- Parse SEBI circular PDFs and extract compliance obligations.
- Model obligations as finite state machines.
- Evaluate broker telemetry data against FSMs (deterministic only).
- Generate verifiable audit scoreboards with hash-chain integrity.
- Provide a React dashboard for compliance status visualization.

## Important Constraints

| Constraint | Rule |
|------------|------|
| Node 3 LLM | **Never** call an LLM. All evaluation is deterministic. |
| Human approval | Required before Node 3 executes (HITL gate). |
| Determinism | Execution against operational data must be deterministic. |
| Auditability | Every compliance finding must be traceable to the originating regulation. |
| Explainability | All verdicts must be explainable from the FSM + telemetry alone. |

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
