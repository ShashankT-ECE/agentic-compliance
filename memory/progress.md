# Progress Tracker

> **Purpose**: High-level project status. Understand everything in under 30 seconds.
> **Usage**: Mark `[x]` when complete, `[-]` when in progress, `[ ]` when pending.

---

## Overall Completion

**~60%** — Backend pipeline complete (M0–M7). Frontend (M8) is next.

---

## Backend

- [x] FastAPI app entry point (`main.py`) — ✅ M7
- [x] API routes — pipeline trigger, status, result — ✅ M7
- [x] API routes — HITL review (approve/reject/amend) — ✅ M4/M7
- [x] API routes — telemetry ingest and query — ✅ M7
- [x] API routes — compliance reports — ✅ M7
- [x] API dependency injection (`deps.py`) — ✅ M7
- [x] Data models — obligations (`models/obligation.py`) — ✅ M0
- [x] Data models — telemetry (`models/telemetry.py`) — ✅ M0
- [x] Data models — FSM (`models/fsm.py`) — ✅ M0
- [x] Data models — LockedFSM (`models/locked_fsm.py`) — ✅ M4
- [x] Data models — verdict (`models/verdict.py`) — ✅ M0
- [x] Data models — scoreboard (`models/scoreboard.py`) — ✅ M0
- [x] Utility — PDF ingestion (`utils/pdf_ingest.py`) — ✅ M1
- [x] Utility — hash chain integrity (`utils/hash_chain.py`) — ✅ M3
- [x] Utility — LLM client (`utils/llm_client.py`) — ✅ M1
- [x] Utility — telemetry generation (`utils/telemetry_gen.py`) — ✅ M5
- [x] Utility — state machine engine (`utils/state_machine.py`) — ✅ M5
- [x] Utility — timeline evaluator (`utils/timeline_evaluator.py`) — ✅ M5
- [x] Pipeline — state schema (`pipeline/state.py`) — ✅ M0
- [x] Pipeline — graph orchestration (`pipeline/graph.py`) — ✅ M7
- [x] Pipeline — runner (`pipeline/runner.py`) — ✅ M7
- [x] Node 1 — PDF Parser (`pipeline/nodes/parser.py`) — ✅ M1
- [x] Node 2 — FSM Extractor (`pipeline/nodes/fsm_extractor.py`) — ✅ M2
- [x] HITL Gate — (`pipeline/nodes/hitl_gate.py`) — ✅ M4
- [x] Node 3 — Assertion Evaluator (`pipeline/nodes/evaluator.py`) — ✅ M5
- [x] Node 4 — Scoreboard Generator (`pipeline/nodes/scoreboard.py`) — ✅ M6
- [ ] Database connection & migrations — M9

## Frontend

- [x] Vite + React app scaffold
- [x] Dependencies installed (184 packages, builds successfully)
- [x] TypeScript strict mode configured
- [ ] Dashboard page (`pages/index.tsx`) — M8
- [ ] Report page (`pages/report.tsx`) — M8
- [ ] Compliance store — Zustand (`store/useComplianceStore.ts`) — M8
- [ ] API client (`api/client.ts`) — M8
- [ ] CircularPanel component — M8
- [ ] FSMViewer component — M8
- [ ] AuditReport component — M8
- [ ] TelemetryTable component — M8

## LangGraph

- [x] LangGraph installed and validated (1.2.7)
- [x] 5-node pipeline graph compiles and executes — ✅ M7
- [x] Pipeline DAG definition (`graph.py`) — ✅ M7
- [x] State schema and routing — ✅ M0/M7
- [x] Node wiring (Parser → FSM Extractor → HITL → Evaluator → Scoreboard) — ✅ M7
- [x] Conditional HITL edge (approved → evaluator, pending/rejected → END) — ✅ M7
- [x] Error handling and retry logic — ✅ M7

## Nodes

- [x] Node 1 — PDF Parser (LLM allowed) — ✅ M1
- [x] Node 2 — FSM Extractor (LLM allowed) — ✅ M2
- [x] HITL Gate — (deterministic, no LLM) — ✅ M4
- [x] Node 3 — Assertion Evaluator (LLM strictly prohibited) — ✅ M5
- [x] Node 4 — Scoreboard Generator (formatting only) — ✅ M6

## Testing

- [x] `test_models.py` — 68 tests — ✅ M0
- [x] `test_parser.py` — 35 tests — ✅ M1
- [x] `test_fsm.py` — 34 tests — ✅ M2
- [x] `test_hash_chain.py` — 20 tests — ✅ M3
- [x] `test_hitl.py` — 46 tests — ✅ M4
- [x] `test_evaluator.py` — 69 tests — ✅ M5
- [x] `test_scoreboard.py` — 38 tests — ✅ M6
- [x] `test_orchestration.py` — 53 tests — ✅ M7
- [ ] Integration tests — full pipeline end-to-end
- [ ] Frontend tests — M8

**Suite total**: 363 tests — 363 passed, 0 failed

## Environment

- [x] Python 3.11.15 installed (via uv)
- [x] Backend venv created (backend/.venv)
- [x] 104+ Python packages installed
- [x] 184 frontend packages installed
- [x] LangGraph validated (1.2.7)
- [x] DeepSeek integration surface ready (swappable LLM client)
- [x] Frontend builds with zero errors
- [x] Docker configs complete
- [ ] DeepSeek API key configured
- [ ] poppler-utils installed (requires sudo)

## Memory System

- [x] `CLAUDE.md` — permanent operating manual
- [x] `memory/current_task.md` — exact resume point
- [x] `memory/progress.md` — high-level status tracker
- [x] `memory/project_handoff.md` — permanent project overview
- [x] `memory/session_handoff.md` — session summary
- [x] `memory/decision_log.md` — architectural decision records
- [x] `memory/graphify_handoff.md` — pipeline graph topology
- [x] `memory/project_roadmap.md` — milestone plan

## Documentation

- [ ] Architecture reference (`docs/architecture.pdf`) — **BROKEN: ASCII placeholder**
- [ ] API reference (`docs/api_reference.md`) — partial
- [x] README — setup and usage
- [x] Setup scripts — Linux (`scripts/setup_wsl.sh`)
- [x] Setup scripts — Windows (`scripts/setup_windows.ps1`)

## Demo Readiness

- [x] Pipeline executes end-to-end (headless mode)
- [ ] Dashboard displays compliance status — M8
- [ ] Audit report renders findings — M8
- [ ] FSM visualization works — M8
- [x] Data integrity (hash chain) verifiable
