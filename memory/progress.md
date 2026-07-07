# Progress Tracker

> **Purpose**: High-level project status. Understand everything in under 30 seconds.
> **Usage**: Mark `[x]` when complete, `[-]` when in progress, `[ ]` when pending.

---

## Overall Completion

**V1.0.1 COMPLETE + PUSHED** — All M0–M9 milestones + interactive demo fixes + enterprise UI polish committed. 404 tests passing.

**V1.0.2 in working tree** — Dashboard sync fix, workflow diagram redesign, terminology cleanup, evaluator status fix, report formula fix. 5 uncommitted files.

---

## Backend

- [x] FastAPI app entry point (`main.py`) — ✅ M7 → ✅ V1.0.1 (load_dotenv added)
- [x] API routes — pipeline trigger, status, result — ✅ M7
- [x] API routes — HITL review (approve/reject/amend) — ✅ M4/M7
- [x] API routes — telemetry ingest and query — ✅ M7
- [x] API routes — compliance reports — ✅ M7 → ✅ V1.0.2 (compliance_pct formula fix)
- [x] API routes — pipeline resume (`POST /{run_id}/resume`) — ✅ V1.0.1
- [x] API dependency injection (`deps.py`) — ✅ M7
- [x] Data models — obligations (`models/obligation.py`) — ✅ M0
- [x] Data models — telemetry (`models/telemetry.py`) — ✅ M0
- [x] Data models — FSM (`models/fsm.py`) — ✅ M0
- [x] Data models — LockedFSM (`models/locked_fsm.py`) — ✅ M4
- [x] Data models — verdict (`models/verdict.py`) — ✅ M0
- [x] Data models — scoreboard (`models/scoreboard.py`) — ✅ M0
- [x] Utility — PDF ingestion (`utils/pdf_ingest.py`) — ✅ M1
- [x] Utility — hash chain integrity (`utils/hash_chain.py`) — ✅ M3
- [x] Utility — LLM client (`utils/llm_client.py`) — ✅ M1 → ✅ V1.0.1 (max_tokens=16384)
- [x] Utility — telemetry generation (`utils/telemetry_gen.py`) — ✅ M5
- [x] Utility — state machine engine (`utils/state_machine.py`) — ✅ M5 → ✅ V1.0.2 (determine_compliance_status fix)
- [x] Utility — timeline evaluator (`utils/timeline_evaluator.py`) — ✅ M5
- [x] Pipeline — state schema (`pipeline/state.py`) — ✅ M0
- [x] Pipeline — graph orchestration (`pipeline/graph.py`) — ✅ M7
- [x] Pipeline — runner (`pipeline/runner.py`) — ✅ M7
- [x] Node 1 — PDF Parser (`pipeline/nodes/parser.py`) — ✅ M1 → ✅ V1.0.1 (truncation recovery)
- [x] Node 2 — FSM Extractor (`pipeline/nodes/fsm_extractor.py`) — ✅ M2 → ✅ V1.0.1 (data path fix)
- [x] HITL Gate — (`pipeline/nodes/hitl_gate.py`) — ✅ M4 → ✅ V1.0.1 (data path fix)
- [x] Node 3 — Assertion Evaluator (`pipeline/nodes/evaluator.py`) — ✅ M5
- [x] Node 4 — Scoreboard Generator (`pipeline/nodes/scoreboard.py`) — ✅ M6
- [ ] Database connection & migrations — V2

## Frontend

- [x] Vite + React app scaffold — ✅ M8
- [x] Dependencies installed — ✅ M8
- [x] TypeScript strict mode configured — ✅ M8
- [x] `App.tsx` + `App.css` — layout, routing, enterprise design system — ✅ M8 → ✅ V1.0.1 (CSS rewrite)
- [x] `api/client.ts` — typed fetch client (12 endpoints + resume) — ✅ M8 → ✅ V1.0.1
- [x] `store/useComplianceStore.ts` — Zustand store (12 actions + resume) — ✅ M8 → ✅ V1.0.1
- [x] Dashboard page (`pages/index.tsx`) — ✅ M8 → ✅ V1.0.1 → ✅ V1.0.2 (sync fix in working tree)
- [x] Report page (`pages/report.tsx`) — ✅ M8
- [x] HITL review page (`pages/hitl.tsx`) — ✅ V1.0.1 → ✅ V1.0.2 (onReviewed sync in working tree)
- [x] CircularPanel component — ✅ M8
- [x] FSMViewer component — ✅ M8 → ✅ V1.0.1 (labels, no floating text) → ✅ V1.0.2 (linear layout in working tree)
- [x] AuditReport component — ✅ M8
- [x] TelemetryTable component — ✅ M8
- [ ] Frontend unit/component tests — V2

## LangGraph

- [x] LangGraph installed and validated (1.2.7) — ✅ M7
- [x] 5-node pipeline graph compiles and executes — ✅ M7
- [x] Pipeline DAG definition (`graph.py`) — ✅ M7
- [x] State schema and routing — ✅ M0/M7
- [x] Node wiring — ✅ M7
- [x] Conditional HITL edge — ✅ M7
- [x] Error handling and retry logic — ✅ M7
- [x] Pydantic state ↔ dict bridge fix — ✅ M9

## Nodes

- [x] Node 1 — PDF Parser (LLM allowed) — ✅ M1 → ✅ V1.0.1
- [x] Node 2 — FSM Extractor (LLM allowed) — ✅ M2 → ✅ V1.0.1
- [x] HITL Gate (deterministic, no LLM) — ✅ M4 → ✅ V1.0.1
- [x] Node 3 — Assertion Evaluator (LLM strictly prohibited) — ✅ M5 → ✅ V1.0.2 (determine_compliance_status fix)
- [x] Node 4 — Scoreboard Generator (formatting only) — ✅ M6

## Testing

- [x] `test_models.py` — 68 tests — ✅ M0
- [x] `test_parser.py` — 39 tests (35 original + 4 truncation recovery) — ✅ M1 → ✅ V1.0.1
- [x] `test_fsm.py` — 34 tests — ✅ M2
- [x] `test_hash_chain.py` — 20 tests — ✅ M3
- [x] `test_hitl.py` — 46 tests — ✅ M4 → ✅ V1.0.1 (monkeypatch fix)
- [x] `test_evaluator.py` — 69 tests — ✅ M5 → ✅ V1.0.2 (determine_compliance_status tests still pass with new logic)
- [x] `test_scoreboard.py` — 38 tests — ✅ M6
- [x] `test_orchestration.py` — 53 tests — ✅ M7
- [x] `test_integration.py` — 37 tests (26 original + 7 resume + 4 HITL list) — ✅ M9 → ✅ V1.0.1
- [ ] Frontend tests — V2
- [ ] CI automation — V2

**Suite total**: **404 tests — 404 passed, 0 failed**

## V1.0.1 — Interactive Demo Fixes + Enterprise UI

- [x] Root cause diagnosis (8 bugs identified) — ✅
- [x] `.env` loading fix — ✅
- [x] Resume endpoint (`POST /{run_id}/resume`) — ✅
- [x] HITL review page — ✅
- [x] Disk-authoritative HITL list — ✅
- [x] `get_pipeline_status` disk fallback — ✅
- [x] `_count_fsms()` enum fix — ✅
- [x] Telemetry merge on resume — ✅
- [x] Dashboard status sync via resume action — ✅
- [x] Data path resolution fix (backend/app/data → backend/data) — ✅
- [x] `.gitignore` pattern fix (`/*` → `/`) — ✅
- [x] `test_hitl.py` mutation fix — ✅
- [x] `HitlListResponse` model fix — ✅
- [x] `AmendAction` type fix — ✅
- [x] Resume completed-run guard — ✅
- [x] Parser `max_tokens` 4096 → 16384 — ✅
- [x] Parser truncation recovery (Attempt 4) — ✅
- [x] Regression tests (7 resume + 4 HITL list + 4 parser) — ✅
- [x] Enterprise CSS redesign — ✅
- [x] FSM → Compliance Obligation labels — ✅
- [x] Floating transition labels removed — ✅
- [x] Git commit `8845e8a` and push — ✅
- [x] Branch synchronization (6 of 7 branches) — ✅
- [x] HITL list rewrite (disk-authoritative, zero stale leaks) — ✅
- [x] Real DeepSeek v4 Pro end-to-end verification — ✅

## V1.0.2 — Final Demo Polish + Evaluator Fix (uncommitted)

- [x] Dashboard state sync fix (onReviewed calls fetchHitlList + fetchStatus) — ✅ (working tree)
- [x] Linear workflow diagram redesign (no overlapping arrows) — ✅ (working tree)
- [x] FSM-XXXX → OBL-XXXX formatting — ✅ (working tree)
- [x] Initial State → Current Status label — ✅ (working tree)
- [x] **determine_compliance_status() fix** — trust self._current_state — ✅ (working tree, today)
- [x] **Report compliance_pct formula fix** — match scoreboard — ✅ (working tree, today)
- [x] Backend test suite (404 passed) — ✅
- [x] Frontend build (52 modules, zero errors) — ✅
- [x] Live end-to-end API verification (non-compliant verdict confirmed) — ✅
- [ ] Final manual browser demo — pending
- [ ] Decide on demo fixture gap (3 FSMs still PENDING due to missing events) — pending
- [ ] Clean stale runtime data — pending
- [ ] Commit and push V1.0.2 — pending
- [ ] Declare V1 frozen — pending

## Environment

- [x] Python 3.11.15 installed (via uv)
- [x] Backend venv created (backend/.venv)
- [x] 104+ Python packages installed
- [x] 184 frontend packages installed
- [x] LangGraph validated (1.2.7)
- [x] DeepSeek API configured (key in backend/.env, model=deepseek-v4-pro)
- [x] Frontend builds with zero errors (52 modules)
- [x] Docker configs complete (basic)
- [ ] poppler-utils installed (requires sudo) — V2
- [ ] Docker Compose full-stack — V2

## Memory System

- [x] `CLAUDE.md` — permanent operating manual
- [x] `memory/current_task.md` — updated 2026-07-07
- [x] `memory/progress.md` — updated 2026-07-07
- [x] `memory/project_handoff.md` — updated 2026-07-07
- [x] `memory/session_handoff.md` — updated 2026-07-07
- [x] `memory/decision_log.md` — updated 2026-07-07
- [x] `memory/graphify_handoff.md` — updated 2026-07-07
- [x] `memory/project_roadmap.md` — unchanged (V2 scope)

## Documentation

- [ ] Architecture reference (`docs/architecture.pdf`) — **BROKEN: ASCII placeholder** → V2
- [ ] API reference (`docs/api_reference.md`) — partial (7/12 endpoints) → V2
- [x] README — setup and usage
- [x] Setup scripts — Linux (`scripts/setup_wsl.sh`)
- [x] Setup scripts — Windows (`scripts/setup_windows.ps1`)

## Demo Readiness

- [x] Pipeline executes end-to-end (headless mode)
- [x] Demo fixtures loaded and validated
- [x] `scripts/run_demo.sh` completes in one command (MockLLMClient)
- [x] Real DeepSeek API works end-to-end (4 clauses extracted)
- [x] Interactive frontend demo functional (HITL review page + resume)
- [x] Dashboard displays compliance status
- [x] Audit report renders findings
- [x] Compliance workflow visualization works
- [x] Data integrity (hash chain) verifiable
- [x] Tamper detection confirmed (4 attack vectors)
- [x] Verdict statuses are now meaningful (non_compliant for missed deadlines)
- [x] Report compliance percentage matches scoreboard formula
- [ ] Final clean end-to-end demo — pending (fixture gap decision + stale data cleanup)

---

## V2 — Next Version (not started)

- [ ] PostgreSQL persistence (replace in-memory stores)
- [ ] Database ORM models + Alembic migrations
- [ ] Docker Compose full-stack (frontend + nginx + PostgreSQL)
- [ ] CI/CD pipeline hardening
- [ ] Frontend test suite (Vitest + React Testing Library)
- [ ] Authentication (API keys or JWT)
- [ ] `docs/architecture.md` (replace broken PDF)
- [ ] API reference completion (12/12 endpoints)
- [ ] Production hardening (rate limiting, logging, monitoring)
- [ ] Real SEBI circular integration
- [ ] Code-quality cleanup (extract inline styles, deduplicate helpers)
