# Project Roadmap

> **Purpose**: Definitive milestone plan for the Agentic Compliance pipeline.
> **Priority**: Reference-level — defines what each milestone delivers and its success criteria.

---

## Milestone Map

```
M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9  [V1 COMPLETE ✅]
                                                         │
                                                    V2 (planned)
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

## M8 — Frontend ✅

**Status**: Complete

**Files**:
- `frontend/src/main.tsx` — React 19 root mount
- `frontend/src/App.tsx` — BrowserRouter, header/nav, Routes
- `frontend/src/App.css` — Full design system (CSS custom properties, cards, buttons, badges, tables, responsive)
- `frontend/src/pages/index.tsx` — Dashboard page (pipeline trigger, runs list, run detail, HITL queue, telemetry stats)
- `frontend/src/pages/report.tsx` — Report viewer (lookup form, completed runs, report generation)
- `frontend/src/store/useComplianceStore.ts` — Zustand state management (data slices, loading/error per action, 12 actions)
- `frontend/src/api/client.ts` — Typed native-fetch API client (all 12 M7 endpoints, 22 TypeScript interfaces)
- `frontend/src/components/CircularPanel.tsx` — Pipeline trigger form + run status display
- `frontend/src/components/FSMViewer.tsx` — SVG state diagram + transition/timeline tables
- `frontend/src/components/AuditReport.tsx` — Scoreboard, broker cards, verdicts table, hash chain status
- `frontend/src/components/TelemetryTable.tsx` — Sortable table, filters, pagination, expandable detail, ingest form

**Build**: `tsc` (strict) + `vite build` — zero errors, 50 modules, 3 output files

---

## M9 — End-to-End Demo & Final Validation ✅

**Status**: Complete

**Deliverables**:
- `backend/tests/fixtures/sample_circular.pdf` — Valid 2-page PDF from canonical V1 circular
- `backend/tests/fixtures/sample_telemetry.json` — 10 events, 3 brokers, 4 event types
- `backend/tests/conftest.py` — 5 demo fixtures (circular_path, circular_text, circular_ref, telemetry_records, telemetry_events)
- `backend/tests/test_integration.py` — 26 integration tests, 8 test classes
- `scripts/run_demo.sh` — Self-contained demo script (bash + inline Python, MockLLMClient, no API key needed)
- Bug fix: `_state_to_dict()` in `graph.py` (preserved Pydantic sub-models through state bridge)
- Bug fix: `extract_fsms()` in `fsm_extractor.py` (dict→ObligationClause normalization)

**Validation**: 389 tests passing, frontend build passing, Node 3 safety gate confirmed, hash chain verified with tamper detection

---

## V2 — Production Hardening

**Status**: Planned — NOT started

**Candidate scope** (to be reviewed and approved before implementation):
- PostgreSQL persistence — async SQLAlchemy ORM models + Alembic migrations
- Docker Compose full-stack — frontend (nginx) + backend + PostgreSQL
- CI/CD pipeline — GitHub Actions with test, build, deploy jobs
- Frontend test suite — Vitest + React Testing Library
- Authentication — API keys or JWT
- Real SEBI circular integration
- `docs/architecture.md` or regenerate `docs/architecture.pdf`
- API reference completion (12/12 endpoints with full schemas)
- Production hardening — rate limiting, structured logging, monitoring
- Code-quality cleanup — extract shared components, deduplicate helpers

---

## Roadmap Change Log

| Date | Change |
|------|--------|
| 2026-07-01 | Initial roadmap — M0 scaffold |
| 2026-07-03 | M5 (Evaluator) and M6 (Scoreboard) defined |
| 2026-07-04 | M6 and M7 completed, M8 defined |
| 2026-07-04 | M8 complete — frontend dashboard, FSM viewer, audit report, telemetry table |
| 2026-07-04 | M9 complete — end-to-end demo, 26 integration tests, demo script, final validation |
| 2026-07-04 | V1 COMPLETE — all M0–M9 merged, 389 tests passing |
