# Progress Tracker

> **Purpose**: High-level project status. Understand everything in under 30 seconds.
> **Usage**: Mark `[x]` when complete, `[-]` when in progress, `[ ]` when pending.

---

## Overall Completion

**0%** — Repository scaffolded. No pipeline logic implemented yet.

---

## Backend

- [ ] FastAPI app entry point (`main.py`)
- [ ] API routes — pipeline execution
- [ ] API routes — telemetry ingestion
- [ ] API routes — compliance reports
- [ ] API dependency injection (`deps.py`)
- [ ] Data models — obligations (`models/obligation.py`)
- [ ] Data models — telemetry (`models/telemetry.py`)
- [ ] Utility — PDF ingestion (`utils/pdf_ingest.py`)
- [ ] Utility — hash chain integrity (`utils/hash_chain.py`)
- [ ] Utility — telemetry generation (`utils/telemetry_gen.py`)
- [ ] Pipeline — state schema (`pipeline/state.py`)
- [ ] Pipeline — graph orchestration (`pipeline/graph.py`)
- [ ] Node 1 — PDF Parser
- [ ] Node 2 — FSM Extractor
- [ ] Node 3 — Assertion Evaluator (deterministic only — no LLM)
- [ ] Node 4 — Scoreboard Generator
- [ ] Dockerfile
- [ ] Database connection & migrations

## Frontend

- [ ] Vite + React app scaffold
- [ ] Dashboard page (`pages/index.tsx`)
- [ ] Report page (`pages/report.tsx`)
- [ ] Compliance store — Zustand (`store/useComplianceStore.ts`)
- [ ] API client (`api/client.ts`)
- [ ] AuditReport component
- [ ] CircularPanel component
- [ ] FSMViewer component
- [ ] TelemetryTable component

## LangGraph

- [ ] Pipeline DAG definition
- [ ] State schema and routing
- [ ] Node wiring (Parser → FSM Extractor → Evaluator → Scoreboard)
- [ ] Error handling and retry logic

## Nodes

- [ ] Node 1 — PDF Parser (LLM allowed)
- [ ] Node 2 — FSM Extractor (LLM allowed)
- [ ] Node 3 — Assertion Evaluator (LLM strictly prohibited)
- [ ] Node 4 — Scoreboard Generator (formatting only)

## Testing

- [ ] Parser tests (`tests/test_parser.py`)
- [ ] FSM extractor tests (`tests/test_fsm.py`)
- [ ] Evaluator tests (`tests/test_evaluator.py`)
- [ ] Integration tests — full pipeline
- [ ] Test fixtures and mock data

## Memory System

- [x] `CLAUDE.md` — permanent operating manual
- [x] `memory/current_task.md` — exact resume point
- [x] `memory/progress.md` — high-level status tracker
- [x] `memory/project_handoff.md` — permanent project overview
- [x] `memory/session_handoff.md` — session summary template
- [x] `memory/decision_log.md` — architectural decision records
- [x] `memory/graphify_handoff.md` — pipeline graph topology

## Telemetry

- [ ] Telemetry ingestion endpoint
- [ ] Telemetry data validation
- [ ] Synthetic telemetry generator (`utils/telemetry_gen.py`)
- [ ] Telemetry query/filter API

## Documentation

- [ ] Architecture reference (`docs/architecture.pdf`) — canonical source
- [ ] API reference (`docs/api_reference.md`)
- [ ] SEBI circular notes (`docs/sebi_circular_notes.md`)
- [ ] README — setup and usage
- [ ] Setup scripts — Linux (`scripts/setup_wsl.sh`)
- [ ] Setup scripts — Windows (`scripts/setup_windows.ps1`)

## Demo Readiness

- [ ] Pipeline executes end-to-end
- [ ] Dashboard displays compliance status
- [ ] Audit report renders findings
- [ ] FSM visualization works
- [ ] Data integrity (hash chain) verifiable
