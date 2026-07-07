# Decision Log

> **Purpose**: Permanent record of architectural decisions. Never store temporary notes or task tracking here.
> **Updated**: Only when an architectural decision is made, changed, or reversed.
> **Priority**: Level 4 in the canonical source hierarchy.

---

## Decision Records

### 2026-07-01 — Repository scaffold with pipeline-oriented architecture

- **Decision**: Create the canonical directory layout with Python backend (FastAPI + LangGraph), TypeScript/React frontend (Vite), docs, scripts, and memory.
- **Rationale**: Clean separation of concerns with a pipeline-oriented backend architecture and modern frontend toolchain. Enables asynchronous parallel development.
- **Alternatives considered**: Monolithic structure, separate repos for frontend/backend.
- **Impact**: Clear ownership boundaries. Frontend and backend can be developed independently. LangGraph provides the orchestration framework for the pipeline DAG.
- **Status**: Implemented.

### 2026-07-01 — Four-node compliance pipeline

- **Decision**: Structure the pipeline as four sequential nodes: PDF Parser (Node 1), FSM Extractor (Node 2), Assertion Evaluator (Node 3), Scoreboard Generator (Node 4), with a HITL gate between Node 2 and Node 3.
- **Rationale**: Each node has a single responsibility with clear inputs and outputs. LLM usage can be tightly controlled per node. Node 3 is isolated for deterministic-only execution. HITL gate inserted where LLM output must be human-verified before deterministic evaluation.
- **Alternatives considered**: Two-node design, monolithic evaluator, post-evaluation review.
- **Impact**: Node 3's strict no-LLM constraint is naturally enforced by the architecture. Clear HITL insertion point before Node 3.
- **Status**: Implemented (5 nodes with conditional HITL branch in M7).

### 2026-07-03 — Timeline-based obligation for V1

- **Decision**: Target timeline-based SEBI circulars for V1 (reporting/submission deadlines with T+1, T+3 day offsets).
- **Rationale**: Deadline compliance is the most common pattern in SEBI circulars. Timeline logic is naturally testable with synthetic event streams.
- **Alternatives considered**: Threshold-based (position limits), process compliance.
- **Status**: Accepted.

### 2026-07-03 — Hybrid FSM model (state machine + timeline conditions)

- **Decision**: Model compliance obligations as hybrid FSMs with embedded timeline conditions.
- **Rationale**: Pure state machines cannot elegantly express time-based obligations. Pure rule engines lose auditability. Hybrid approach supports both.
- **Impact**: FSM schema is more complex. Evaluator must interpret both state transitions and timeline conditions.
- **Status**: Accepted.

### 2026-07-03 — Event-based telemetry with production schema

- **Decision**: Telemetry is event-based (discrete timestamped events from broker systems). Pipeline consumes production schema from Day 1.
- **Rationale**: Event logs are the standard format for broker operational data. Designing for real schema prevents rework.
- **Status**: Accepted.

### 2026-07-03 — HITL gate reviews FSMs before evaluation

- **Decision**: Human-in-the-loop gate occurs after Node 2 and before Node 3. Human reviews extracted FSMs for correctness.
- **Rationale**: LLMs may misinterpret regulatory text. HITL catches extraction errors before they propagate into compliance verdicts.
- **Status**: Accepted.

### 2026-07-03 — Hash chain required for V1 demo

- **Decision**: Hash-chain integrity system operational alongside core pipeline for V1 demo.
- **Rationale**: Verifiable audit trails are a core differentiator for the TechSprint demo.
- **Status**: Accepted.

### 2026-07-03 — Depth-first implementation strategy

- **Decision**: Build end-to-end depth first (one circular, one broker, full pipeline) rather than horizontal breadth.
- **Rationale**: A complete working pipeline through all nodes demonstrates the full value proposition.
- **Status**: Accepted.

### 2026-07-03 — Canonical V1 regulatory source

- **Decision**: Canonical V1 regulatory source is **SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57** (28 April 2025), subject *"Timelines for collection of Margins other than Upfront Margins."*
- **Rationale**: Contains timeline-based obligations (T+1, advance-of-trade) that map cleanly to the HybridFSM model.
- **Status**: Accepted.

### 2026-07-03 — Deterministic FSM execution: first-match transition resolution

- **Decision**: When multiple transitions from current state match the same event trigger, take the first matching transition.
- **Rationale**: Must be fully deterministic. First-match provides a clear, reproducible rule.
- **Status**: Implemented in `state_machine.py`.

### 2026-07-03 — Timeline reference time: earliest event timestamp

- **Decision**: Use the earliest telemetry event's timestamp as the reference point for deadline computation when no explicit reference_time is provided.
- **Rationale**: Earliest event timestamp is the best available proxy for T+0. It's deterministic and always available.
- **Consequence**: Single-event scenarios always appear on-time. Meaningful late detection requires ≥2 events.
- **Status**: Implemented in `timeline_evaluator.py`.

### 2026-07-03 — End-of-trading-day deadline semantics

- **Decision**: T+N deadlines compute to 23:59:59 UTC on the target calendar date, not N×24 hours from reference.
- **Rationale**: SEBI circulars define deadlines as end-of-trading-day. Matches regulatory interpretation.
- **Status**: Implemented in `timeline_evaluator.py`.

### 2026-07-03 — Error-isolated FSM evaluation

- **Decision**: One malformed FSM produces an error verdict — remaining FSMs continue evaluating independently.
- **Rationale**: A single corrupt definition must not block the entire compliance run.
- **Status**: Implemented in `evaluator.py`.

### 2026-07-03 — Event-counted evidence trail with 1:1 telemetry mapping

- **Decision**: Evidence trail contains exactly one entry per telemetry event per FSM, with a `matched` boolean.
- **Rationale**: Auditors can trace every event against every obligation. Complete and independently verifiable.
- **Status**: Implemented in `evaluator.py`.

### 2026-07-03 — Compliance scoring rubric

- **Decision**: Five-tier scoring: COMPLIANT=1.0, DUE=0.75, PENDING=0.5, LATE=0.5, NON_COMPLIANT=0.0.
- **Rationale**: Distinguishes "nothing happened yet" (PENDING, 0.5) from "actively failing" (NON_COMPLIANT, 0.0).
- **Status**: Implemented in `evaluator.py`.

### 2026-07-04 — LangGraph + FastAPI as M7 orchestration layer

- **Decision**: Wire the pipeline via LangGraph's `StateGraph` using `CompliancePipelineState` (Pydantic model) as the shared state. Expose operations through FastAPI REST endpoints. Run nodes sequentially outside the compiled graph's full invoke cycle to support async LLM calls and HITL pause/resume.
- **Rationale**: LangGraph provides the DAG structure and conditional routing. FastAPI provides the HTTP API for external triggers and HITL review. The manual sequential execution (rather than full `graph.invoke()`) supports async LLM calls and the pause/resume pattern needed for human review.
- **Alternatives considered**: Full LangGraph invoke with async node support, Celery task queue, hand-rolled orchestrator.
- **Impact**: `build_pipeline_graph()` defines the topology; `PipelineRunner` executes nodes sequentially. State is persisted in-memory (V1) → PostgreSQL (V2).
- **Status**: Implemented in M7.

### 2026-07-04 — Pydantic state ↔ dict bridge for node compatibility

- **Decision**: LangGraph graph uses `CompliancePipelineState` (Pydantic model) as state type. Node wrapper functions in `graph.py` convert to dict manually (preserving Pydantic sub-models — ObligationClause, HybridFSM, LockedFSM) before calling existing M1-M4 node functions that expect dict state.
- **Rationale**: M1-M4 node functions were written before M7 and expect `dict.get()` access. Converting the state at the graph boundary avoids modifying all existing node functions. The initial implementation used `model_dump()` which serialized sub-models to plain dicts, breaking downstream nodes. Fixed in M9 to build dicts field-by-field.
- **Status**: Implemented in `graph.py` (`_state_to_dict()` — fixed in M9).

### 2026-07-04 — In-memory stores for V1 (database in V2)

- **Decision**: Pipeline run state, telemetry events, and reports use in-memory stores (`dict` with module-level accessors) for V1. Replace with PostgreSQL via SQLAlchemy in V2.
- **Rationale**: In-memory stores enable fast iteration during development and testing. The store accessor pattern (`_get_store()` / `_set_store()`) makes the swap to a database mechanical — only the store implementation changes, not the API or business logic.
- **Status**: Implemented. V2 migration planned.

### 2026-07-04 — Frontend stack: React 19 + TypeScript strict + Vite + Zustand + native fetch

- **Decision**: Frontend uses React 19 with TypeScript strict mode, Vite for build, Zustand for state management, and native `fetch` for HTTP (no Axios). CSS is custom properties-based (no Tailwind).
- **Rationale**: Zustand is lightweight and idiomatic for React 19. Native fetch avoids an extra dependency. CSS custom properties provide theming without a build-time utility framework.
- **Alternatives considered**: Axios, Redux, Tailwind CSS, Next.js.
- **Status**: Implemented in M8.

### 2026-07-04 — Demo mode: MockLLMClient with canned responses for reliable demos

- **Decision**: The demo script (`scripts/run_demo.sh`) and integration tests use `MockLLMClient` / `MultiMockLLMClient` with canned JSON responses that match the canonical V1 circular. No real LLM API key is required.
- **Rationale**: Demos must run reliably without depending on external API availability, network latency, or API key configuration. The canned responses are the same data the real LLM would produce — they exercise the exact same parser and FSM extractor code paths.
- **Impact**: The demo script is self-contained and deterministic (same hash chain root every run). Developers can validate the full pipeline in under 2 seconds with zero configuration.
- **Status**: Implemented in M9.

### 2026-07-04 — Integration test strategy: in-process PipelineRunner, no HTTP server

- **Decision**: Integration tests call `PipelineRunner` directly (in-process) rather than going through the FastAPI HTTP layer. Telemetry and report endpoints are tested via `TestClient`.
- **Rationale**: Pipeline execution is the primary integration concern. Testing via HTTP adds latency and complexity without additional coverage. The HTTP layer is independently tested in `test_orchestration.py` (53 tests).
- **Status**: Implemented in `test_integration.py` (26 tests, M9).

### 2026-07-06 — Disk-authoritative HITL list (no in-memory store dependency)

- **Decision**: `list_hitl_runs()` (no `run_id` path) reads exclusively from disk — `data/locked_fsms/` — rather than the in-memory `_run_store`. Disk is the authoritative source.
- **Rationale**: The in-memory store is volatile (lost on restart, accumulates stale entries). Disk is durable and verifiable. The prior two-source approach (memory + disk supplement) leaked stale runs.
- **Status**: Implemented in `pipeline.py`.

### 2026-07-06 — Truncated JSON array recovery in parser

- **Decision**: Added "Attempt 4" to `_extract_json_from_response()` — character-by-character depth tracking to recover complete top-level JSON objects from truncated LLM responses. Salvages partial results instead of failing entirely.
- **Rationale**: Real LLM APIs can truncate responses when `max_tokens` is exceeded. Recovering 2 of 3 clauses is better than losing all 3. Combined with `max_tokens=16384` (up from 4096) as defense in depth.
- **Status**: Implemented in `parser.py`. 4 regression tests added.

### 2026-07-06 — Data path resolution: `backend/data/` not `backend/app/data/`

- **Decision**: All `__file__`-based data path constants use 4× `.parent` (reaching `backend/`) instead of 3× `.parent` (which reached `backend/app/`).
- **Rationale**: The `.gitignore` was written for `backend/data/` — that was always the intended location. The code was off by one directory level. Fixing the code rather than the `.gitignore` preserves the original intent.
- **Status**: Implemented in `hitl_gate.py`, `fsm_extractor.py`, `pipeline.py`.

### 2026-07-06 — Enterprise UI design system (blue/slate/white palette)

- **Decision**: Frontend CSS redesigned with enterprise palette (blue brand #2563eb, slate neutrals #0f172a–#f8fafc). FSM terminology replaced with "Compliance Obligation" in presentation layer. TypeScript interfaces and backend models unchanged.
- **Rationale**: Target audience is SEBI compliance officers — the UI must feel like a professional regulatory tool, not a developer prototype. Technical terminology (FSM, state machine) is confusing to non-technical users.
- **Status**: Implemented in V1.0.1 (committed). Additional polish in V1.0.2 working tree.

### 2026-07-06 — Fixed-position SVG workflow diagram (linear layout)

- **Decision**: Replaced dynamic grid-based SVG state diagram with fixed-position linear layout: PENDING → DUE → LATE → NON_COMPLIANT, with COMPLIANT as a branch node above. No overlapping arrows.
- **Rationale**: The grid layout produced curved overlapping arrows when states were connected in non-grid patterns. A fixed layout matching the actual business workflow is clearer for compliance review.
- **Status**: Implemented in `FSMViewer/index.tsx` (V1.0.2 working tree).

### 2026-07-07 — determine_compliance_status() trusts FSM current state

- **Decision**: `StateMachine.determine_compliance_status()` now returns `self._current_state` as the canonical status, rather than re-deriving it from `(is_terminal, has_transitions, deadline_met)`. The FSM's transitions — including timeline-driven overdue transitions — are the source of truth for where the machine landed. Only `deadline_met=False` overrides (to LATE).
- **Rationale**: The old logic re-derived canonical status from structural properties (is_terminal, has_transitions) but ignored the FSM's actual current state. When the FSM reached LATE — which had an outgoing `grace_expired → NON_COMPLIANT` transition — the method saw "non-terminal + has transitions" and returned DUE, which mapped to PENDING. This caused ALL verdicts to display as PENDING regardless of the FSM's true state.
- **Impact**: Verdicts now correctly show `non_compliant` when the FSM reaches LATE. The `current_state` and `status` fields are now consistent — `_map_status(LATE) → NON_COMPLIANT`. Regression tests (404) continue to pass. One previously-dormant verdict (CL-02) now correctly shows NON_COMPLIANT because its timeline rule detected a missed T+1 deadline.
- **Status**: Implemented in `state_machine.py` (V1.0.2 working tree).

### 2026-07-07 — Report compliance percentage matches scoreboard formula

- **Decision**: Report `compliance_pct` now uses `compliant / (total - pending) * 100` (same as scoreboard's `compliance_rate`). When all verdicts are pending (evaluated=0), returns 100.0 ("nothing to fail yet").
- **Rationale**: The old formula `compliant / total * 100` counted pending verdicts in the denominator, producing 0% even when nothing had been evaluated. The scoreboard correctly excluded pending verdicts. The inconsistency was confusing — the report and scoreboard should agree.
- **Status**: Implemented in `reports.py` (V1.0.2 working tree).

### 2026-07-08 — Timeline overdue_transition applied to StateMachine before verdict construction

- **Decision**: `TimelineEvaluator.evaluate_timeline_rule()` already computed `overdue_transition` (e.g. `"LATE"`) when a deadline was missed, but the evaluator never consumed it. Added `StateMachine.transition_to(target_state, reason)` to synthetically advance the FSM, and integrated it in `_evaluate_single_fsm()` so that every timeline rule with `deadline_met=False` applies its `overdue_transition` before the verdict is built.
- **Rationale**: The `deadline_met=False` override in `determine_compliance_status()` forced the canonical status to LATE → NON_COMPLIANT, but `sm.current_state` remained PENDING because the FSM's overdue transition was never called. This created a `State=PENDING / Status=NON_COMPLIANT` split that was audibly inconsistent. The `overdue_transition` field was designed for exactly this purpose — it just needed to be wired into the evaluator.
- **Impact**: `ComplianceVerdict.current_state` now accurately reflects the FSM's post-timeline state (LATE, not PENDING). The two subsystems (event-driven FSM and time-driven timeline) are now properly integrated — timeline results feed back into the FSM rather than bypassing it. Evidence trail records `trigger="timeline_overdue"` so auditors can distinguish event-driven from timeline-driven transitions.
- **Status**: Implemented in `state_machine.py` and `evaluator.py` (V1.0.2 working tree). 6 new tests.

### 2026-07-08 — Deterministic explanation column for audit reports

- **Decision**: Each verdict in the audit report now carries a human-readable `explanation` field derived from the existing `evidence` object. `_derive_explanation()` is a pure function — no LLM, no external state, deterministic. Displayed as an "Explanation" column in the frontend verdicts table.
- **Rationale**: PENDING verdicts previously gave no indication why — users couldn't distinguish "this is a bug" from "this is correct — no matching telemetry events." The explanation (`"Awaiting start event 'circular_issued' — not found in telemetry data."`) makes the report self-explanatory without requiring an engineer to interpret FSM states and evidence trails.
- **Alternatives considered**: Expandable detail rows (higher complexity, more clicks), tooltip on status badge (too hidden), separate "diagnostics" section (overkill for V1).
- **Impact**: Backward compatible — `explanation` is optional on the TypeScript type. Reports generated before the change simply won't have the field. The explanation is stored in the in-memory `_report_store` alongside the verdict, so re-fetching the same report always returns the same explanation. No new API endpoints, no evaluator changes.
- **Status**: Implemented in `reports.py`, `client.ts`, and `AuditReport/index.tsx` (V1.0.2 working tree). Browser verification pending — column renders but shows fallback "—" for all rows (root cause not yet diagnosed).

---

## Template for New Entries

```markdown
### YYYY-MM-DD — Title

- **Decision**: What was decided.
- **Rationale**: Why this decision was made.
- **Alternatives considered**: Other options that were evaluated.
- **Impact**: Consequences of this decision (positive and negative).
- **Status**: Proposed / Accepted / Deprecated / Reversed.
```
