# Progress Tracker

> **Purpose**: High-level project status. Understand everything in under 30 seconds.
> **Usage**: Mark `[x]` when complete, `[-]` when in progress, `[ ]` when pending.

---

## Overall Completion

**33%** — M0, M1, M2, M3 complete. M4 (HITL Gate) next.

---

## Backend

- [ ] FastAPI app entry point (`main.py`)
- [ ] API routes — pipeline execution
- [ ] API routes — telemetry ingestion
- [ ] API routes — compliance reports
- [ ] API dependency injection (`deps.py`)
- [x] Data models — obligations (`models/obligation.py`)
- [x] Data models — telemetry (`models/telemetry.py`)
- [x] Data models — FSM (`models/fsm.py`)
- [x] Data models — verdicts (`models/verdict.py`)
- [x] Data models — scoreboard (`models/scoreboard.py`)
- [x] Utility — PDF ingestion (`utils/pdf_ingest.py`)
- [x] Utility — hash chain integrity (`utils/hash_chain.py`)
- [x] Utility — LLM client (`utils/llm_client.py`)
- [ ] Utility — telemetry generation (`utils/telemetry_gen.py`)
- [x] Pipeline — state schema (`pipeline/state.py`)
- [ ] Pipeline — graph orchestration (`pipeline/graph.py`)
- [x] Node 1 — PDF Parser
- [x] Node 2 — FSM Extractor
- [ ] Node 3 — Assertion Evaluator (deterministic only — no LLM)
- [ ] Node 4 — Scoreboard Generator
- [ ] Dockerfile
- [x] Database connection & migrations

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

- [x] Node 1 — PDF Parser (LLM allowed)
- [x] Node 2 — FSM Extractor (LLM allowed)
- [ ] Node 3 — Assertion Evaluator (LLM strictly prohibited)
- [ ] Node 4 — Scoreboard Generator (formatting only)

## Testing

- [x] Parser tests (`tests/test_parser.py`)
- [x] FSM extractor tests (`tests/test_fsm.py`)
- [ ] Evaluator tests (`tests/test_evaluator.py`)
- [ ] Integration tests — full pipeline
- [x] Test fixtures and mock data
- [x] Hash chain tests (`tests/test_hash_chain.py`)
- [x] Model validation tests (`tests/test_models.py`)

## Memory System

- [x] `CLAUDE.md` — permanent operating manual
- [x] `memory/current_task.md` — exact resume point
- [x] `memory/progress.md` — high-level status tracker
- [x] `memory/project_handoff.md` — permanent project overview
- [x] `memory/session_handoff.md` — session summary template
- [x] `memory/decision_log.md` — architectural decision records
- [x] `memory/graphify_handoff.md` — pipeline graph topology
- [x] `memory/project_roadmap.md` — permanent implementation plan

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
