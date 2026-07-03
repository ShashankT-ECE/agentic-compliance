# Project Roadmap — Permanent Implementation Plan

> **Purpose**: The single source of truth for what to build, in what order, and when each milestone is done.
> **Usage**: Future sessions read this file, pick the next uncompleted milestone, and implement it. Do not skip milestones.
> **Updated**: After each milestone is completed — mark `[x]` and update completion date.
> **Priority**: This file is the primary planning document. It defers to `CLAUDE.md` for process rules and `project_handoff.md` for architecture invariants.

---

## Project Overview

**Agentic Compliance** — automated compliance verification for stock brokers against SEBI regulatory circulars.

The system ingests SEBI circular PDFs, extracts obligations as finite state machines (FSMs), evaluates broker telemetry data against those FSMs deterministically, and produces verifiable audit scoreboards with hash-chain integrity.

Built for the **SEBI Securities Market TechSprint Problem Statement 2**.

---

## Architecture Summary

```
[Node 1: PDF Parser] ──→ [Node 2: FSM Extractor] ──→ [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]
                                                          │
                                                          └──→ (rejected → Node 2 re-extract)
```

| Node | Name | LLM? | Function |
|------|------|------|----------|
| 1 | PDF Parser | ✅ Yes | Extract structured obligation clauses from circular PDFs using pdfplumber + LLM |
| 2 | FSM Extractor | ✅ Yes | Transform clauses into hybrid FSMs (state machine + timeline conditions) |
| — | HITL Gate | ❌ Human | Review, approve, or correct extracted FSMs before deterministic evaluation |
| 3 | Assertion Evaluator | ❌ Never | Match event-based telemetry against FSMs — fully deterministic |
| 4 | Scoreboard Generator | Format only | Aggregate verdicts into hash-chained audit scoreboard |

### Core Design Decisions (locked for V1)

| Decision | Value |
|----------|-------|
| Target obligation | Timeline-based (deadline compliance: T+1, T+3 day offsets) |
| FSM model | Hybrid — state machine (PENDING / DUE / COMPLIANT / LATE / NON_COMPLIANT) with embedded timeline conditions |
| Telemetry format | Event-based logs (broker_id, event_type, timestamp, payload) |
| HITL placement | Between Node 2 and Node 3 — human reviews FSMs, then evaluation runs |
| Hash chain | Required for V1 demo — chain covers locked FSMs and scoreboard entries |
| Strategy | Depth-first — one circular, one broker, full stack end-to-end |

---

## Canonical V1 Regulatory Source

**SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57** — Issued 28 April 2025
Subject: *"Timelines for collection of Margins other than Upfront Margins – Alignment to settlement cycle"*

This is the single SEBI circular used by every milestone in V1. All extracted obligations, generated FSMs, HITL reviews, compliance evaluations, and scoreboards are derived from this circular unless the developer explicitly changes the canonical source (in which case this section and `decision_log.md` must be updated).

| Milestone | Role of this circular |
|-----------|----------------------|
| M1 | Parses obligations from this circular |
| M2 | Generates HybridFSMs from obligations extracted from this circular |
| M3 | Hash-chains FSM snapshots derived from this circular |
| M4 | Performs HITL review on FSMs derived from this circular |
| M5 | Evaluates broker telemetry against obligations from this circular |
| M6 | Generates compliance scoreboards for this circular |
| M7 | Orchestrates the pipeline for this circular |
| M8 | Visualises compliance results for this circular |
| M9 | Demonstrates complete end-to-end workflow using this circular |

---

## Implementation Milestones

### [x] M0 — Foundation: Data Models & Pipeline State (Completed 2026-07-03)

**Objective**: Define every data structure the pipeline touches. Nothing downstream works without these schemas.

**Files to create/modify:**
- `backend/app/models/obligation.py` — `ObligationClause`, `ObligationType` enum
- `backend/app/models/telemetry.py` — `TelemetryEvent`, `BrokerInfo`
- `backend/app/models/fsm.py` — `HybridFSM`, `FSMState`, `FSMTransition`, `TimelineRule` (new file)
- `backend/app/models/verdict.py` — `ComplianceVerdict`, `VerdictStatus` (new file)
- `backend/app/models/scoreboard.py` — `Scoreboard`, `BrokerScore`, `HashLink` (new file)
- `backend/app/pipeline/state.py` — `CompliancePipelineState` (LangGraph State schema)
- `backend/app/utils/hash_chain.py` — hash chain interface (signatures + data structures; full implementation in M3)
- `backend/app/database.py` — SQLAlchemy async engine, session factory, Base (new file)
- Alembic initial migration (optional in V1 — can use `create_all` for sprint)

**Dependencies:** None (root of the dependency tree)

**Completion criteria:**
- [x] All Pydantic models defined with full type annotations and validators
- [x] Pipeline state schema includes all fields needed by all 4 nodes
- [x] Hash chain interface defined (types: `HashLink`, `HashChain`; functions: `compute_hash`, `link`, `verify`)
- [x] Database connection configured with async SQLAlchemy
- [x] All models have `model_validate` tests with representative data
- [x] `backend/requirements.txt` is current (already done)

---

### [x] M1 — PDF Parser (Node 1) (Completed 2026-07-03)

**Objective**: Extract structured obligation clauses from a SEBI circular PDF. This is the system's entry point.

**Files to create/modify:**
- `backend/app/utils/pdf_ingest.py` — PDF text extraction (pdfplumber), page slicing
- `backend/app/pipeline/nodes/parser.py` — parser node function
- LLM prompt template for obligation extraction (inline or `prompts/parser_prompt.md`)
- `backend/tests/test_parser.py` — parser unit tests
- `backend/tests/fixtures/circular_slice.txt` — real SEBI circular excerpt

**Dependencies:** M0 (models)

**LLM boundary:** Parser calls LLM to extract structured clauses from raw text. The abstraction makes this swappable.

**Completion criteria:**
- [x] `pdf_ingest.py` extracts clean text from PDF files (handles multi-column layouts)
- [x] Parser node produces `List[ObligationClause]` from a real circular text slice
- [x] Each clause includes: clause_id, clause_text, obligation_type (timeline), timeline_params (offset, grace_period, unit), effective_date, applicable_entities
- [x] Edge cases handled: malformed PDFs, missing fields in circular
- [x] Tests pass with at least one real circular excerpt
- [x] NO placeholder business logic

---

### [x] M2 — FSM Extractor (Node 2) (Completed 2026-07-03)

**Objective**: Transform parsed obligation clauses into hybrid FSMs — the central abstraction of the system.

**Files to create/modify:**
- `backend/app/pipeline/nodes/fsm_extractor.py` — FSM extraction node
- `backend/app/models/fsm.py` — full HybridFSM implementation (schema from M0, logic here)
- LLM prompt template for FSM generation
- `backend/tests/test_fsm.py` — FSM extraction tests

**Dependencies:** M1 (obligation clauses as input)

**LLM boundary:** FSM extractor calls LLM to generate state machines from obligation text. The model defines states, transitions, and timeline rules.

**HybridFSM structure (defined):**
```
HybridFSM:
  obligation_ref: str                  # Links back to source ObligationClause
  circular_ref: str
  states: List[FSMState]               # e.g., PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT
  initial_state: str
  transitions: List[FSMTransition]     # (from_state, to_state, trigger_event, conditions)
  timeline_rules: List[TimelineRule]   # deadline_offset, grace_period, time_unit, start_event
  metadata: dict                       # Source clause text, extraction confidence, etc.
```

**Completion criteria:**
- [x] FSM extractor produces `List[HybridFSM]` from `List[ObligationClause]`
- [x] FSMs correctly encode timeline-based obligations (deadlines relative to trigger events)
- [x] FSMs include all states: PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT
- [x] FSMs include at least one time-based transition (e.g., PENDING → LATE if deadline passes)
- [x] FSM validation rejects malformed state machines (unreachable states, missing transitions)
- [x] Extracted FSMs are persisted to `backend/data/extracted/` as JSON
- [x] Tests pass with parser output fixtures

---

### [x] M3 — Hash Chain Utility (Completed 2026-07-03)

**Objective**: Build the verifiable hash chain that ensures audit trail integrity for locked FSMs and scoreboard entries.

**Files to create/modify:**
- `backend/app/utils/hash_chain.py` — full implementation (interface from M0)
- `backend/tests/test_hash_chain.py` — hash chain tests (new file)

**Dependencies:** M0 (data structures)

**Design:**
- SHA-256 hash of serialized content
- Linked list structure: each link stores `(index, timestamp, data_hash, previous_hash, link_hash)`
- `compute_hash(data: bytes) -> str` — hash any serializable content
- `link(previous_link: HashLink, data: dict) -> HashLink` — create next link in chain
- `verify_chain(links: List[HashLink]) -> bool` — validate entire chain integrity
- Root hash anchors the chain (stored in pipeline state and scoreboard)

**Completion criteria:**
- [x] `compute_hash`, `link`, `verify_chain` implemented and tested
- [x] Chain verification detects tampering (modified data, broken link, reordered links)
- [x] Hash chain can serialize/deserialize to JSON for storage
- [x] Edge cases: empty chain, single-link chain, chain with 1000+ links
- [x] Tests pass with tampering scenarios

---

### [x] M4 — HITL Gate (Completed 2026-07-03)

**Objective**: Build the human review gate between Node 2 and Node 3. Humans review extracted FSMs, approve or correct them, and locked FSMs are released to the evaluator.

**Files to create/modify:**
- `backend/app/pipeline/nodes/hitl_gate.py` — conditional routing logic (new file)
- `backend/app/api/routes/pipeline.py` — HITL review endpoints (approve, reject, amend)
- `backend/app/models/locked_fsm.py` — `LockedFSM` schema with hash chain integration (new file)
- Pipeline state transition: `extracted_fsms` → `locked_fsms` on approval

**Dependencies:** M2 (FSM output), M3 (hash chain for FSM locking)

**Flow:**
1. Pipeline reaches HITL gate → pauses, returns extracted FSMs for review
2. Human sees FSMs via API/frontend → approves, rejects, or amends
3. On approval: FSMs are locked (hash-chained, timestamped, signed) → pipeline resumes to Node 3
4. On rejection/amendment: FSMs sent back to Node 2 context with human annotations

**HITL API endpoints:**
- `GET /pipeline/{id}/fsms` — list extracted FSMs pending review
- `POST /pipeline/{id}/fsms/approve` — approve as-is
- `POST /pipeline/{id}/fsms/reject` — reject with notes
- `POST /pipeline/{id}/fsms/amend` — submit corrected FSM

**Completion criteria:**
- [x] Locked FSM includes hash chain link, approval metadata, and original FSM data
- [x] Locked FSMs stored in `backend/data/locked_fsms/` (not committed to git — see `.gitignore`)
- [x] HITL endpoints accept approve/reject/amend with validation
- [x] Pipeline correctly resumes on approval or diverts on rejection
- [x] Hash chain verifies locked FSM integrity
- [x] Tests pass for all HITL paths (approve, reject, amend, invalid data)

---

### [ ] M5 — Assertion Evaluator (Node 3)

**Objective**: Deterministically match broker telemetry events against approved FSMs to produce compliance verdicts. This node must NEVER call an LLM.

**Files to create/modify:**
- `backend/app/pipeline/nodes/evaluator.py` — evaluator node (deterministic engine)
- `backend/app/utils/state_machine.py` — FSM evaluation engine (new file)
- `backend/app/utils/timeline_evaluator.py` — deadline/offset computation (new file)
- `backend/app/utils/telemetry_gen.py` — synthetic telemetry generator for tests
- `backend/tests/test_evaluator.py` — evaluator tests
- `backend/tests/fixtures/mock_telemetry.json` — expanded with realistic event sequences

**Dependencies:** M3 (hash chain not needed by evaluator itself), M4 (locked FSMs as input)

**Engine design:**
```
For each LockedFSM:
  1. Initialize FSM at initial_state with timer = PENDING
  2. Process telemetry events in chronological order:
     a. Match event to an FSM transition (event_type + conditions)
     b. If matched: execute transition (update state, record evidence)
     c. Check timeline_rules: if deadline elapsed → auto-transition (e.g., PENDING → LATE)
  3. After all events processed:
     a. Determine final compliance status from terminal state
     b. Generate ComplianceVerdict with evidence trail
```

**Key constraints:**
- Pure function: same FSMs + same events → same verdicts (deterministic)
- No LLM calls, no external API calls, no randomness
- Time computations use event timestamps, not wall clock
- Partial evaluation: if relevant events haven't arrived, state remains PENDING

**Completion criteria:**
- [ ] Evaluator processes events chronologically, matching them to FSM transitions
- [ ] Timeline conditions correctly compute deadlines (T+0, T+1, T+3 day offsets)
- [ ] Auto-transitions fire when deadlines elapse without required events
- [ ] Verdicts include evidence: which events were matched, timeline status, current state
- [ ] Deterministic: identical inputs produce identical outputs (tested with repeat runs)
- [ ] No LLM imports, no LLM calls, no LLM-adjacent logic in evaluator
- [ ] Tests pass: compliant path, non-compliant path, pending path, missing events, out-of-order events

---

### [ ] M6 — Scoreboard Generator (Node 4)

**Objective**: Aggregate compliance verdicts into a structured, hash-chained audit scoreboard.

**Files to create/modify:**
- `backend/app/pipeline/nodes/scoreboard.py` — scoreboard generation node
- `backend/app/models/scoreboard.py` — full implementation (schema from M0, logic here)
- `backend/tests/test_scoreboard.py` — scoreboard tests (new file)

**Dependencies:** M3 (hash chain), M5 (verdicts as input)

**Scoreboard structure:**
```
Scoreboard:
  circular_id: str
  generated_at: datetime
  broker_summaries: List[BrokerScore]
  hash_chain:
    root_hash: str
    chain: List[HashLink]          # One link per broker score + one for aggregate
    verified_at: datetime | None

BrokerScore:
  broker_id: str
  total_obligations: int
  compliant: int
  non_compliant: int
  pending: int
  compliance_rate: float           # compliant / (total - pending)
  obligation_details: List[ObligationResult]
  hash_link: HashLink              # Chain this broker's results

ObligationResult:
  obligation_ref: str
  fsm_ref: str
  status: VerdictStatus
  current_state: str
  evidence_summary: str
  evaluated_at: datetime
```

**Completion criteria:**
- [ ] Scoreboard aggregates verdicts per broker with obligation-level detail
- [ ] Each broker score is hash-chained into the scoreboard's hash chain
- [ ] Scoreboard persists to database
- [ ] Scoreboard is a Pydantic model with full validation
- [ ] Hash chain verification endpoint can validate scoreboard integrity
- [ ] Tests pass: single broker, multiple brokers, all-compliant, mixed results, empty results

---

### [ ] M7 — Backend API + Pipeline Orchestration

**Objective**: Wire all nodes into the LangGraph pipeline, expose API endpoints, and ensure the full backend runs end-to-end.

**Files to create/modify:**
- `backend/app/pipeline/graph.py` — LangGraph pipeline DAG definition
- `backend/app/api/routes/pipeline.py` — trigger, status, result, HITL review endpoints
- `backend/app/api/routes/telemetry.py` — telemetry ingestion and query
- `backend/app/api/routes/reports.py` — report generation and retrieval
- `backend/app/api/deps.py` — dependency injection (DB sessions, pipeline state)
- `backend/app/main.py` — FastAPI app with router registration, middleware, startup/shutdown
- `backend/app/pipeline/runner.py` — pipeline execution wrapper (new file)

**Dependencies:** M1-M6 (all nodes implemented)

**Pipeline endpoints:**
- `POST /api/pipeline/trigger` — start pipeline run (circular_id, telemetry_batch)
- `GET /api/pipeline/status/{run_id}` — current status (parsing, extracting, awaiting_approval, evaluating, scoring, complete, error)
- `GET /api/pipeline/result/{run_id}` — final scoreboard
- `GET /api/pipeline/{run_id}/fsms` — FSMs pending review (HITL)
- `POST /api/pipeline/{run_id}/fsms/approve` — approve FSMs
- `POST /api/pipeline/{run_id}/fsms/reject` — reject FSMs

**Telemetry endpoints:**
- `POST /api/telemetry/ingest` — ingest one or more telemetry events
- `GET /api/telemetry/query` — query events by broker, time range, event type

**Report endpoints:**
- `GET /api/reports/generate?run_id=...` — generate formatted report
- `GET /api/reports/{report_id}` — retrieve stored report

**Completion criteria:**
- [ ] LangGraph pipeline wires all 4 nodes + HITL conditional edge
- [ ] Pipeline state correctly propagates through all nodes
- [ ] All API endpoints return correct responses with proper status codes
- [ ] Error handling: invalid input → 400, not found → 404, pipeline error → 500 with details
- [ ] Pipeline runs can be triggered, status polled, and results retrieved
- [ ] Telemetry events can be ingested and queried
- [ ] FastAPI app starts without errors

---

### [ ] M8 — Frontend

**Objective**: Build the React dashboard that visualizes pipeline execution, FSM review, and compliance scoreboards.

**Files to create/modify:**
- `frontend/src/main.tsx` — app entry with routing
- `frontend/src/pages/index.tsx` — dashboard (pipeline status, broker overview)
- `frontend/src/pages/report.tsx` — detailed compliance report
- `frontend/src/store/useComplianceStore.ts` — Zustand store
- `frontend/src/api/client.ts` — API client for backend
- `frontend/src/components/CircularPanel/index.tsx` — parsed circular viewer
- `frontend/src/components/FSMViewer/index.tsx` — FSM visualization for HITL review
- `frontend/src/components/AuditReport/index.tsx` — scoreboard visualization
- `frontend/src/components/TelemetryTable/index.tsx` — telemetry event browser

**Dependencies:** M7 (API endpoints)

**Completion criteria:**
- [ ] Dashboard displays pipeline status (from API polling)
- [ ] HITL review page shows FSMs with approve/reject/amend actions
- [ ] Report page renders scoreboard with compliance rates per broker
- [ ] API client handles all backend endpoints
- [ ] Zustand store manages application state
- [ ] FSM viewer displays state machine as readable diagram (text-based or simple visual)
- [ ] Telemetry table shows events with filtering

---

### [ ] M9 — End-to-End Demo

**Objective**: Polish everything into a working demo for the TechSprint. One circular, complete pipeline, reproducible.

**Files to create/modify:**
- `backend/tests/test_integration.py` — full pipeline integration test
- `backend/data/circulars/` — place one real SEBI circular excerpt
- `backend/app/utils/telemetry_gen.py` — demo data generator
- `README.md` — demo walkthrough section
- Any edge-case handling discovered during integration testing

**Dependencies:** M8 (everything built)

**Demo scenario (defined):**
1. Select one SEBI circular with a timeline-based obligation
2. Extract a representative text slice → store in `backend/data/circulars/`
3. Run pipeline end-to-end: PDF text → parse → FSM extract → HITL approve → evaluate → scoreboard
4. Verify hash chain integrity of the output scoreboard
5. Frontend dashboard reflects the complete pipeline status
6. Frontend report page shows the scoreboard with per-obligation details

**Completion criteria:**
- [ ] Full end-to-end test passes with deterministic output
- [ ] One real SEBI circular text is available in the repository (in `backend/data/circulars/`)
- [ ] Demo telemetry data available (via `telemetry_gen.py` or fixture)
- [ ] Hash chain verification works on the demo output
- [ ] Pipeline can be triggered from the frontend
- [ ] Scoreboard renders in the frontend report page
- [ ] README contains a "Demo" section with exact steps to reproduce

---

## Milestone Dependency Graph

```
M0 (Foundation)
 ├── M1 (Parser) ─── M2 (FSM Extractor)
 │                      │
 │                      └── M4 (HITL Gate) ─── M5 (Evaluator) ─── M6 (Scoreboard)
 │                      │                                               │
 M3 (Hash Chain) ───────┘                                               │
 │                                                                      │
 └──────────────────────────────────────────────────────────────────────┘
                                                                         │
                                                                    M7 (API + Pipeline)
                                                                         │
                                                                    M8 (Frontend)
                                                                         │
                                                                    M9 (E2E Demo)
```

**Parallelizable work:** M3 (Hash Chain) can start alongside M1/M2 since both depend only on M0.

---

## Completion Criteria (Project Done)

- [ ] Pipeline executes end-to-end: PDF text → scoreboard with hash chain
- [ ] At least one real SEBI circular text is processable
- [ ] All 4 nodes + HITL gate are implemented and tested
- [ ] Backend API exposes pipeline trigger, telemetry ingest, and report retrieval
- [ ] Frontend displays pipeline status, FSM review, and scoreboard
- [ ] Hash chain integrity is verifiable from the scoreboard
- [ ] All tests pass (unit + integration)
- [ ] Demo walkthrough works from README instructions

---

## Non-Goals (Intentionally Excluded from V1)

- Multi-circular pipeline runs (only one circular per pipeline run)
- Threshold-based obligations (timeline-only for V1)
- Real-time/streaming telemetry ingestion (batch ingestion is fine)
- User authentication/authorization (API is open for the sprint)
- Advanced FSM visualization (graphical rendering — text-based or simple diagram is sufficient)
- Multi-broker UI (single broker view is enough for the demo)
- Production deployment (Docker Compose is sufficient)
- Performance optimization (correctness over speed)

---

## How To Use This Roadmap

1. **Start a session** → read `project_handoff.md` + `project_roadmap.md` + `session_handoff.md`
2. **Identify the next incomplete milestone** (first `[ ]` from top)
3. **If M0**: read from top. **If M1-M9**: ensure all dependency milestones are marked `[x]`
4. **Implement exactly one milestone** — all files, all tests, all completion criteria
5. **Update this file**: change `[ ]` to `[x]` with completion date
6. **Update `session_handoff.md`**: what was done, blockers, discoveries
7. **Update `current_task.md`**: the exact resume point for next time
8. **Commit and push** to `origin dev`
