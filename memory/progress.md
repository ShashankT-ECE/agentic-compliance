# Progress Tracker

> **Purpose**: High-level project status. Understand everything in under 30 seconds.
> **Usage**: Mark `[x]` when complete, `[-]` when in progress, `[ ]` when pending.

---

## Overall Completion

**44%** — M0, M1, M2, M3, M4 complete. M5 (Assertion Evaluator) next.

---

## Milestone Summary

### M0 — Foundation: Data Models & Pipeline State ✅ (2026-07-03)
- All Pydantic models: `ObligationClause`, `TelemetryEvent`, `HybridFSM`, `ComplianceVerdict`, `Scoreboard`, `HashLink`, `HashChain`
- `CompliancePipelineState` with all 4-node + HITL fields
- `hash_chain.py`: `compute_hash`, `link`, `verify_chain`, `build_chain` (fully functional)
- `database.py`: async SQLAlchemy engine, session factory, Base
- 68 model tests

### M1 — PDF Parser (Node 1) ✅ (2026-07-03)
- `pdf_ingest.py`: pdfplumber extraction, multi-page, error handling (encrypted/corrupt/missing)
- `llm_client.py`: `LLMClient` ABC, `DeepSeekClient`, `MockLLMClient`
- `parser.py`: `parse_circular()` with 3-pass JSON extraction, Pydantic validation, `parser_node()`
- `parser_prompt.md`: 153-line SEBI-specific LLM prompt
- `circular_slice.txt`: verbatim excerpt from SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57
- 35 parser tests

### M2 — FSM Extractor (Node 2) ✅ (2026-07-03)
- `fsm_extractor.py`: `extract_fsms()`, pre-Pydantic canonical state validation, `persist_fsms()`, `fsm_extractor_node()`
- `fsm_extractor_prompt.md`: 200+ line LLM prompt with 5 canonical states, 3 examples, 5 edge cases
- Reuses M1 `LLMClient` abstraction and `_extract_json_from_response`
- FSMs persisted to `data/extracted/` as JSON
- 34 FSM tests

### M3 — Hash Chain Utility ✅ (2026-07-03)
- `hash_chain.py`: implementation completed in M0
- `test_hash_chain.py`: 20 tests (migrated from `test_models.py`)
- 1000+ link chain test, JSON serialization roundtrip
- Zero production code changes

### M4 — HITL Gate ✅ (2026-07-03)
- `locked_fsm.py`: `LockStatus` enum, `AmendmentRecord`, `LockedFSM` (6 Pydantic validators)
- `hitl_gate.py`: `create_locked_fsms`, `approve_fsm`, `reject_fsm`, `amend_fsm`, integrity verification, persistence, `hitl_gate_node`
- `pipeline.py` (routes): 6 HITL API endpoints (list, get, approve, reject, amend, review history)
- `state.py`: `locked_fsms` type changed to `list[LockedFSM]`
- Locked FSMs stored in `data/locked_fsms/{run_id}/`
- 46 HITL tests
- **Zero LLM calls in HITL gate**

---

## Backend

- [ ] FastAPI app entry point (`main.py`)
- [x] API routes — pipeline execution (HITL endpoints)
- [ ] API routes — telemetry ingestion
- [ ] API routes — compliance reports
- [ ] API dependency injection (`deps.py`)
- [x] Data models — obligations (`models/obligation.py`)
- [x] Data models — telemetry (`models/telemetry.py`)
- [x] Data models — FSM (`models/fsm.py`)
- [x] Data models — verdicts (`models/verdict.py`)
- [x] Data models — scoreboard (`models/scoreboard.py`)
- [x] Data models — locked FSM (`models/locked_fsm.py`)
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

## Nodes

- [x] Node 1 — PDF Parser (LLM allowed)
- [x] Node 2 — FSM Extractor (LLM allowed)
- [x] HITL Gate (no LLM — human review)
- [ ] Node 3 — Assertion Evaluator (LLM strictly prohibited)
- [ ] Node 4 — Scoreboard Generator (formatting only)

## Testing

- [x] Model validation tests (`tests/test_models.py`) — 68 tests
- [x] Parser tests (`tests/test_parser.py`) — 35 tests
- [x] FSM extractor tests (`tests/test_fsm.py`) — 34 tests
- [x] Hash chain tests (`tests/test_hash_chain.py`) — 20 tests
- [x] HITL tests (`tests/test_hitl.py`) — 46 tests
- [ ] Evaluator tests (`tests/test_evaluator.py`)
- [ ] Integration tests — full pipeline
- [x] Test fixtures and mock data

**Total: 203 tests, zero failures, zero warnings.**

## Memory System

- [x] All memory files populated and synchronized
- [x] `CLAUDE.md` — permanent operating manual
- [x] `memory/project_roadmap.md` — M0-M4 marked complete
- [x] `memory/decision_log.md` — 8 architectural decision records
- [x] `memory/graphify_handoff.md` — pipeline topology through M4

## Remaining Work

| Area | Status |
|------|--------|
| Telemetry generation (`telemetry_gen.py`) | Pending |
| Pipeline orchestration (`graph.py`) | Pending (M7) |
| FastAPI main app (`main.py`) | Pending (M7) |
| Frontend (React/Vite/Zustand) | Pending (M8) |
| Documentation (README, API ref, SEBI notes) | Pending |
| Docker/Docker Compose | Pending |
