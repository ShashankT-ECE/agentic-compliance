# Graphify Handoff

> **Purpose**: Pipeline graph topology, state, and node/edge information for the Graphify visualization integration.
> **Updated**: 2026-07-08 — V1.0.2 overdue-transition integration + explanation column in working tree.

---

## Graph Status

**V1.0.1 COMMITTED + PUSHED.** All 5 pipeline nodes + HITL gate implemented and debugged. LangGraph StateGraph wired with conditional routing. FastAPI provides 13 REST endpoints. React dashboard renders all stages. Demo script validates full flow. Real DeepSeek v4 Pro API works end-to-end.

**V1.0.2 in working tree (9 files modified)**: Dashboard sync, workflow diagram redesign, terminology polish, determine_compliance_status fix, report compliance_pct fix, **overdue-transition integration**, **explanation column** (backend + frontend).

---

## Pipeline Topology (V1.0.2 State)

```
[Node 1: PDF Parser] ──→ [Node 2: FSM Extractor] ──→ [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]
       ✅ M1                      ✅ M2                    ✅ M4              ✅ M5 → V1.0.2          ✅ M6
                                                           │
                                              ┌────────────┴────────────┐
                                              │                         │
                                         (all resolved)           (pending/rejected)
                                              │                         │
                                              ▼                         ▼
                                         [Evaluator]                  [END]
                                 (FSM events → timeline overdue)
                                              │
                                              ▼
                                         [Report]
                                    (explanation column)
```

| Aspect | Detail |
|--------|--------|
| **Type** | Directed acyclic graph (DAG) with conditional branch |
| **Orchestration** | LangGraph `StateGraph` + `PipelineRunner` |
| **State** | `CompliancePipelineState` (Pydantic model) |
| **Nodes** | 5 (4 pipeline + 1 HITL gate) |
| **Edges** | 4 linear + 1 conditional (HITL decision) |
| **API** | FastAPI with 13 REST endpoints (12 original + resume) |
| **Frontend** | React 19 + TypeScript + Vite + Zustand (52 modules) |
| **Demo** | `scripts/run_demo.sh` — in-process, MockLLMClient, deterministic |
| **Tests** | 410 (68+39+34+20+46+75+38+53+37) — 0 failed |

## Key V1.0.2 Changes

### Evaluator: determine_compliance_status() trusts current_state (2026-07-07)

Node 3's `StateMachine.determine_compliance_status()` was re-derived from structural properties (`is_terminal`, `has_transitions`) rather than reading `self._current_state`. This caused all verdicts to return PENDING even when the FSM had transitioned to LATE. Fixed to trust `self._current_state` with a `deadline_met=False` override for regulatory LATE escalation.

### Evaluator: overdue_transition integrated (2026-07-08)

`TimelineEvaluator.evaluate_timeline_rule()` always computed `overdue_transition` but the evaluator never consumed it. The `deadline_met=False` override forced canonical status to LATE but `sm.current_state` remained PENDING. Fixed by:

1. `StateMachine.transition_to(target, reason)` — synthetically advances FSM state for timeline-driven transitions
2. `_evaluate_single_fsm()` — applies `overdue_transition` to the FSM for every timeline rule with `deadline_met=False`

Result: `current_state` and `status` are now consistent — both reflect the timeline advance.

### Report: explanation column (2026-07-08)

`_derive_explanation(verdict)` produces a one-sentence explanation from the evidence trail. Displayed as "Explanation" column in the frontend verdicts table. PENDING verdicts now explain why (e.g., `"Awaiting start event 'circular_issued' — not found in telemetry data."`).

---

## Nodes

| ID | Name | LLM? | Status | Input | Output |
|----|------|------|--------|-------|--------|
| 1 | PDF Parser | ✅ Yes | ✅ M1 → V1.0.1 | Circular PDF path | `List[ObligationClause]` |
| 2 | FSM Extractor | ✅ Yes | ✅ M2 → V1.0.1 | `List[ObligationClause]` | `List[HybridFSM]` |
| — | HITL Gate | ❌ Never | ✅ M4 → V1.0.1 | `List[HybridFSM]` | `List[LockedFSM]` (PENDING_REVIEW) |
| 3 | Assertion Evaluator | ❌ Never | ✅ M5 → V1.0.2 | `List[LockedFSM]` + `List[TelemetryEvent]` | `List[ComplianceVerdict]` |
| 4 | Scoreboard Generator | Format only | ✅ M6 | `List[ComplianceVerdict]` | `Scoreboard` + `HashChain` |

## Edges

| From | To | Condition | Status |
|------|----|-----------|--------|
| Node 1 | Node 2 | Always | ✅ M7 wired |
| Node 2 | HITL | Always | ✅ M7 wired |
| HITL | Node 3 | All resolved (APPROVED or AMENDED) | ✅ M7 conditional |
| HITL | END | Pending review or any REJECTED | ✅ M7 conditional |
| Node 3 | Node 4 | Always | ✅ M7 wired |
| Node 4 | END | Always | ✅ M7 wired |

## API Endpoints (V1.0.2)

| Method | Path | Node | Added |
|--------|------|------|-------|
| `POST` | `/api/pipeline/trigger` | Starts pipeline (Nodes 1→2→HITL) | M7 |
| `GET` | `/api/pipeline/status/{run_id}` | Queries pipeline status | M7 |
| `GET` | `/api/pipeline/result/{run_id}` | Returns verdicts + scoreboard | M7 |
| `POST` | `/api/pipeline/{run_id}/resume` | Resumes after HITL (evaluator→scoreboard) | **V1.0.1** |
| `GET` | `/api/pipeline/hitl` | Lists HITL review items | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approves obligation at HITL gate | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Rejects obligation at HITL gate | M7 |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amends obligation at HITL gate | M7 |
| `POST` | `/api/telemetry/ingest` | Ingests broker telemetry | M7 |
| `GET` | `/api/telemetry/query` | Queries ingested telemetry | M7 |
| `GET` | `/api/reports/generate/{run_id}` | Generates audit report | M7 → **V1.0.2** (compliance_pct fix + explanation) |
| `GET` | `/api/reports/{report_id}` | Retrieves stored report | M7 → **V1.0.2** (verdicts include explanation) |
| `GET` | `/health` | Health check | M7 |

## Data Flow (V1.0.2 Complete)

```
[Circular PDF]
     │
     ▼ pdf_ingest.extract_text()
[raw_text: str]
     │
     ▼ parse_circular(llm_client) → M1
     │  (max_tokens=16384, truncation recovery)
[obligation_clauses: List[ObligationClause]]
     │
     ▼ extract_fsms(llm_client) → M2
[extracted_fsms: List[HybridFSM]]
     │
     ▼ hitl_gate_node() → M4 — PAUSE
[locked_fsms: List[LockedFSM]] ← API-driven review (approve/reject/amend)
     │                            persist_locked_fsms() → data/locked_fsms/{run_id}/
     ▼ (on all-resolved)
[evaluator_node()] → M5 → V1.0.2 — deterministic, no LLM, AST-verified
     │  1. StateMachine.apply_events() → event-driven FSM transitions
     │  2. TimelineEvaluator.evaluate_timeline_rule() → overdue detection
     │  3. StateMachine.transition_to(overdue_transition) → timeline-driven advance ★NEW
     │  4. determine_compliance_status(deadline_met) → canonical status
     │  5. _map_status(canonical) → VerdictStatus
     │
     ▼
[compliance_verdicts: List[ComplianceVerdict]]
     │  current_state now reflects both event + timeline subsystems ★FIXED
     │
     ▼ generate_scoreboard() → M6
[scoreboard: Scoreboard + hash_chain: HashChain]
     │
     ▼ generate_report() → _derive_explanation() → explanation column ★NEW
[REST API response — 13 endpoints, verdicts include explanation field]
     │
     ▼
[React Dashboard — trigger, HITL review, telemetry, reports, compliance workflow]
     │  AuditReport → Explanation column (7th column in verdicts table) ★NEW
     │
     ▼
[scripts/run_demo.sh — end-to-end demo with MockLLMClient]
```

## Integrity Chain

```
SEBI circular → ObligationClause → HybridFSM → LockedFSM
                                                    │
                                          integrity_hash (SHA-256)
                                                    │
                                          hash_link (M3 chain)
                                                    │
                                          Scoreboard.hash_chain
                                                    │
                                          verify_chain() ✓
```

## Verdict Status Semantics (V1.0.2)

| FSM Current State | canonical → VerdictStatus | Meaning |
|---|---|---|
| PENDING | → PENDING | Nothing started yet (no events, no timeline trigger) |
| DUE | → PENDING | In progress, awaiting more events |
| COMPLIANT | → COMPLIANT | All required actions on time |
| LATE | → NON_COMPLIANT | Action done after deadline or deadline missed ★NOW CORRECT |
| NON_COMPLIANT | → NON_COMPLIANT | Deadline passed, no action |
| Any + deadline_met=False | → LATE → NON_COMPLIANT | Timeline override, FSM advanced via transition_to() ★NOW CORRECT |

## Explanation Column (V1.0.2)

| Verdict Status | Scenario | Example Explanation |
|---------------|----------|-------------------|
| COMPLIANT | All met | `"All obligations met within deadline."` |
| NON_COMPLIANT | Deadline missed | `"Deadline missed: 'trade_executed' occurred on 2025-05-12 but required action was not completed in time."` |
| PENDING | Start event missing | `"Awaiting start event 'circular_issued' — not found in telemetry data."` |
| PENDING | No matching events | `"No matching telemetry events found for this obligation's transition triggers."` |
| PENDING | In progress | `"In progress: reached 'DUE' — awaiting further events to reach a terminal state."` |

## Graph Changes

| Date | Change | Description |
|------|--------|-------------|
| 2026-07-03 | Initial topology | V1 topology with HITL conditional edge |
| 2026-07-03 | M4 complete | HITL gate implemented |
| 2026-07-03 | M5 complete | Evaluator implemented (deterministic, no LLM) |
| 2026-07-04 | M6 complete | Scoreboard generator implemented |
| 2026-07-04 | M7 complete | LangGraph wiring + FastAPI orchestration layer |
| 2026-07-04 | M8 complete | React dashboard + typed API client + Zustand store |
| 2026-07-04 | M9 complete | 26 integration tests, demo script, state bridge fix |
| 2026-07-06 | V1.0.1 | 8 root causes fixed, resume endpoint, HITL review page, enterprise UI, parser robustness, disk-authoritative HITL list, 404 tests |
| 2026-07-06 | V1.0.2 wip | Dashboard sync fix, linear workflow diagram, terminology polish |
| 2026-07-07 | V1.0.2 evaluator fix | determine_compliance_status() trusts current_state; report compliance_pct aligned with scoreboard |
| 2026-07-08 | V1.0.2 overdue integration | transition_to() + overdue_transition wired into evaluator; current_state now reflects timeline advances |
| 2026-07-08 | V1.0.2 explanation column | _derive_explanation() from evidence; 7th column in frontend verdicts table; 410 tests |

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| test_models.py | 68 | ✅ |
| test_parser.py | 39 (+4 truncation) | ✅ |
| test_fsm.py | 34 | ✅ |
| test_hash_chain.py | 20 | ✅ |
| test_hitl.py | 46 | ✅ |
| test_evaluator.py | 75 (+6 transition_to + overdue) | ✅ |
| test_scoreboard.py | 38 | ✅ |
| test_orchestration.py | 53 | ✅ |
| test_integration.py | 37 | ✅ |
| **Total** | **410** | **0 failed** |

## Demo Script

```
scripts/run_demo.sh

Flow:
  Phase 0 — Dependency checks (Python, fixtures)
  Phase 1 — Pipeline execution (Python, in-process)
    Step 1: Trigger pipeline (runner.start)
    Step 2: HITL queue (load_locked_fsms)
    Step 3: Auto-approve FSMs
    Step 4: Resume pipeline (runner.resume)
    Step 5: Compliance verdicts
    Step 6: Scoreboard
    Step 7: Hash chain verification + tamper test
    Step 8: Report generation

Features:
  - Uses MultiMockLLMClient (no API key needed)
  - Deterministic (same hash chain root every run)
  - Exit codes: 0=success, 1=deps, 2=pipeline, 3=hash-chain
```
