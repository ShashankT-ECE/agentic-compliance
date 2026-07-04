# Current Task — Exact Resume Point

---

## Developer

Friend (Windows + WSL2)

## Date

2026-07-04

## Branch

`dev`

## Latest Commit

`d3c0023` — Merge pull request #3 from ShashankT-ECE/m7-orchestration

## Repository State

- `dev` == `origin/dev` — fully synchronized
- Working tree clean
- All M0–M7 milestones merged and verified
- 363 tests passing, 0 failing

---

## Current Feature

**M8 — Frontend**

---

## Current File

*Planning only. No implementation file active.*

---

## Last Completed Step

M7 (Backend API + LangGraph Orchestration) is complete, merged into `dev`, and independently verified.

### Architecture Implemented

```
[Circular PDF]
     │
     ▼  M1: parser_node()
[ObligationClauses]
     │
     ▼  M2: fsm_extractor_node()
[HybridFSMs]
     │
     ▼  M4: hitl_gate_node()
[LockedFSMs] ─── PAUSE (AWAITING_APPROVAL) ──→ API review (approve/reject/amend)
     │
     ▼  (on all-resolved)
[M5: evaluator_node()] ─── deterministic, no LLM
     │
     ▼
[ComplianceVerdicts]
     │
     ▼  M6: scoreboard_node()
[Scoreboard + HashChain]
     │
     ▼
[REST API: 12 endpoints via FastAPI + LangGraph]
```

### M7 Deliverables

| File | Purpose |
|------|---------|
| `backend/app/pipeline/graph.py` | LangGraph StateGraph — 5 nodes + conditional HITL routing |
| `backend/app/pipeline/runner.py` | PipelineRunner — start, resume, headless modes |
| `backend/app/api/deps.py` | Dependency injection — LLM client, runner, run store |
| `backend/app/api/routes/pipeline.py` | 6 pipeline + HITL endpoints |
| `backend/app/api/routes/telemetry.py` | Telemetry ingest + query endpoints |
| `backend/app/api/routes/reports.py` | Report generation + retrieval endpoints |
| `backend/app/main.py` | FastAPI app with CORS, lifespan, router registration |
| `backend/tests/test_orchestration.py` | 53 tests |

---

## Next Immediate Task

Implement M8 — Frontend dashboard:

1. Read `memory/project_roadmap.md` for M8 specification.
2. Implement `frontend/src/api/client.ts` — Axios API client for all 12 M7 endpoints.
3. Implement `frontend/src/store/useComplianceStore.ts` — Zustand store.
4. Implement `frontend/src/pages/index.tsx` — Dashboard page.
5. Implement `frontend/src/pages/report.tsx` — Report viewer page.
6. Implement components:
   - `frontend/src/components/CircularPanel.tsx`
   - `frontend/src/components/FSMViewer.tsx`
   - `frontend/src/components/AuditReport.tsx`
   - `frontend/src/components/TelemetryTable.tsx`
7. Update `frontend/src/main.tsx` — mount app.
8. Verify `npm run build` succeeds with zero errors.
9. Verify all 363 backend tests still pass.

---

## Files To Open Next

1. `memory/project_roadmap.md` — M8 specification
2. `frontend/package.json` — verify dependencies
3. `frontend/vite.config.ts` — verify build config
4. `frontend/src/` — implement components

---

## Commands To Run

```bash
cd /home/bradha/agentic-compliance/backend && source .venv/bin/activate
python -m pytest tests/ -v        # verify 363 tests pass

cd /home/bradha/agentic-compliance/frontend
npm run build                      # verify build succeeds
```

---

## Known Issues

- **DEEPSEEK_API_KEY not configured** — needed for Nodes 1/2 at runtime.
- **docs/architecture.pdf is broken** — ASCII placeholder, not real PDF.
- **poppler-utils not installed** — requires `sudo apt install poppler-utils`.
- **sudo requires password** — system-level apt installs need developer intervention.
- All in-memory stores (run state, telemetry, reports) — replace with PostgreSQL in M9.
- No authentication (V1 non-goal).

---

## Warnings

- Node 3 (Assertion Evaluator) must never call an LLM — hard architectural constraint.
- The 6 Node 3 safety gate tests in `test_evaluator.py` must always pass.
- `docs/architecture.pdf` is the canonical source of truth (broken).
- Do not redesign M0–M7 — all milestones are independently verified.
- Use feature branches and PR workflow for M8.
