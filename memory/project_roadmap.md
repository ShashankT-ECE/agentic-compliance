# Project Roadmap

> **Purpose**: Definitive milestone plan for the Agentic Compliance pipeline.
> **Priority**: Reference-level — defines what each milestone delivers and its success criteria.

---

## Milestone Map

```
M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9
                                              ↑
                                          (current)
```

---

## M0 — Foundation ✅

**Status**: Complete

- All Pydantic models (`fsm.py`, `obligation.py`, `telemetry.py`, `locked_fsm.py`, `verdict.py`, `scoreboard.py`)
- `CompliancePipelineState` with 14 statuses
- Hash chain interface (`HashLink`, `HashChain`)
- Database config scaffold (`database.py`)
- 68 tests

---

## M1 — PDF Parser (Node 1) ✅

**Status**: Complete

- `pdf_ingest.py`: PDF text extraction via pdfplumber
- `llm_client.py`: Swappable LLM abstraction (`DeepSeekClient` + `MockLLMClient`)
- `parser.py`: LLM-assisted clause extraction with 3-pass JSON parser + `parser_prompt.md`
- 35 tests

---

## M2 — FSM Extractor (Node 2) ✅

**Status**: Complete

- `fsm_extractor.py`: LLM-assisted HybridFSM generation with canonical state validation
- FSM persistence to `data/extracted/{circular}/`
- 34 tests

---

## M3 — Hash Chain Utility ✅

**Status**: Complete

- `hash_chain.py`: `compute_hash`, `link`, `verify_chain`, `build_chain`
- SHA-256 linked-list with genesis anchor
- Tamper detection, reordering detection
- 20 tests

---

## M4 — HITL Gate ✅

**Status**: Complete

- `locked_fsm.py`: `LockedFSM` model with 6 validators, `AmendmentRecord`, `LockStatus`
- `hitl_gate.py`: `create_locked_fsms`, `approve_fsm`, `reject_fsm`, `amend_fsm`
- Integrity verification and hash-chain anchoring
- Persistence to `data/locked_fsms/{run_id}/`
- 6 API endpoints (list, get, approve, reject, amend, review history)
- 46 tests

---

## M5 — Assertion Evaluator (Node 3) ✅

**Status**: Complete

- `state_machine.py`: Deterministic FSM executor consuming `HybridFSM`
- `timeline_evaluator.py`: Deadline parsing (T+0/T+1/T+2/T+3/custom), computation, rule evaluation
- `telemetry_gen.py`: 9 synthetic sequence generators
- `evaluator.py`: `evaluate_compliance(locked_fsms, telemetry_events) → ComplianceVerdicts`
- Evidence trail per verdict: matched events, transition log, timeline status
- Zero LLM, zero randomness, 100% deterministic — verified by 6 safety gate tests
- 69 tests

---

## M6 — Scoreboard Generator (Node 4) ✅

**Status**: Complete

- `scoreboard.py`: `generate_scoreboard(verdicts, circular_id) → Scoreboard`
- Per-broker aggregation with compliance rates
- `ObligationResult` records with evidence summaries
- Hash-chain integrity seal on the scoreboard via M3 `build_chain()`
- 38 tests

---

## M7 — Backend API + LangGraph Orchestration ✅

**Status**: Complete

- `graph.py`: LangGraph `StateGraph` — Parser → FSM Extractor → HITL Gate → (conditional) → Evaluator → Scoreboard
- `runner.py`: `PipelineRunner` with `start()`, `resume()`, `run_headless()` modes
- `deps.py`: Dependency injection — LLM client, runner, run store
- `main.py`: FastAPI app with CORS, lifespan, router registration
- 12 API endpoints: pipeline trigger/status/result, HITL review, telemetry ingest/query, reports generate/retrieve
- All HTTP status codes: 200, 201, 400, 404, 500
- Pipeline state propagation via Pydantic model ↔ dict bridge
- 53 tests

---

## M8 — Frontend

**Status**: Pending — CURRENT

**Files**:
- `frontend/src/main.tsx`
- `frontend/src/pages/index.tsx` — Dashboard
- `frontend/src/pages/report.tsx` — Report viewer
- `frontend/src/store/useComplianceStore.ts` — Zustand state management
- `frontend/src/api/client.ts` — API client (Axios)
- `frontend/src/components/CircularPanel.tsx`
- `frontend/src/components/FSMViewer.tsx`
- `frontend/src/components/AuditReport.tsx`
- `frontend/src/components/TelemetryTable.tsx`

**Success Criteria**:
- [ ] Dashboard displays compliance status
- [ ] Report page renders audit findings
- [ ] FSM visualization works
- [ ] Telemetry table renders ingested events
- [ ] API client connects to all M7 endpoints
- [ ] Vite build succeeds with zero errors
- [ ] All existing backend tests still pass

---

## M9 — Database + Production Hardening

**Status**: Pending

- PostgreSQL persistence (replace in-memory stores)
- Docker Compose integration
- Authentication
- Production deployment config

---

## Roadmap Change Log

| Date | Change |
|------|--------|
| 2026-07-01 | Initial roadmap — M0 scaffold |
| 2026-07-03 | M5 (Evaluator) and M6 (Scoreboard) defined |
| 2026-07-04 | M6 and M7 completed, M8 defined |
