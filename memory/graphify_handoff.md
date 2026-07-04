# Graphify Handoff

> **Purpose**: Pipeline graph topology, state, and node/edge information for the Graphify visualization integration.
> **Updated**: After M9 — V1 complete with end-to-end demo validation.

---

## Graph Status

**V1 COMPLETE.** All 5 pipeline nodes + HITL gate are implemented. LangGraph StateGraph is wired with conditional routing. FastAPI provides 12 REST endpoints. React dashboard renders all pipeline stages. Demo script validates full flow in one command.

---

## Pipeline Topology (Final V1 State)

```
[Node 1: PDF Parser] ──→ [Node 2: FSM Extractor] ──→ [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]
       ✅ M1                      ✅ M2                    ✅ M4              ✅ M5                   ✅ M6
                                                           │
                                              ┌────────────┴────────────┐
                                              │                         │
                                         (all resolved)           (pending/rejected)
                                              │                         │
                                              ▼                         ▼
                                         [Evaluator]                  [END]
```

| Aspect | Detail |
|--------|--------|
| **Type** | Directed acyclic graph (DAG) with conditional branch |
| **Orchestration** | LangGraph `StateGraph` + `PipelineRunner` |
| **State** | `CompliancePipelineState` (Pydantic model) |
| **Nodes** | 5 (4 pipeline + 1 HITL gate) |
| **Edges** | 4 linear + 1 conditional (HITL decision) |
| **API** | FastAPI with 12 REST endpoints |
| **Frontend** | React 19 + TypeScript + Vite + Zustand (50 modules) |
| **Demo** | `scripts/run_demo.sh` — in-process, MockLLMClient, deterministic |
| **Tests** | 389 (68+35+34+20+46+69+38+53+26) — 0 failed |

## Nodes

| ID | Name | LLM? | Status | Input | Output |
|----|------|------|--------|-------|--------|
| 1 | PDF Parser | ✅ Yes | ✅ M1 | Circular PDF path | `List[ObligationClause]` |
| 2 | FSM Extractor | ✅ Yes | ✅ M2 | `List[ObligationClause]` | `List[HybridFSM]` |
| — | HITL Gate | ❌ Never | ✅ M4 | `List[HybridFSM]` | `List[LockedFSM]` (PENDING_REVIEW) |
| 3 | Assertion Evaluator | ❌ Never | ✅ M5 | `List[LockedFSM]` + `List[TelemetryEvent]` | `List[ComplianceVerdict]` |
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

## Pipeline State Schema

```python
CompliancePipelineState (Pydantic BaseModel):
  run_id: str                          # Unique pipeline run identifier
  status: PipelineStatus               # Current execution status
  circular_id: str                     # SEBI circular reference
  circular_path: str | None            # Filesystem path to source PDF
  telemetry_events: list[TelemetryEvent]  # Broker event data
  raw_text: str | None                 # Node 1 output
  obligation_clauses: list[ObligationClause]  # Node 1 output
  extracted_fsms: list[HybridFSM]      # Node 2 output
  locked_fsms: list[LockedFSM]         # HITL gate output (approved only after review)
  approved_by: str | None              # Reviewer identity
  approved_at: datetime | None         # Approval timestamp
  hitl_notes: str | None               # Reviewer notes
  compliance_verdicts: list[ComplianceVerdict]  # Node 3 output
  scoreboard: Scoreboard | None        # Node 4 output
  hash_chain_root: str | None          # Root hash of the integrity chain
  errors: list[PipelineError]          # Error log
  node_timings: dict[str, float]       # Per-node execution times
  metadata: dict[str, Any]            # Pipeline metadata
```

### PipelineStatus Enum

```
CREATED → PARSING → PARSED → EXTRACTING_FSM → FSM_EXTRACTED
                                                    │
                                                    ▼
                                          AWAITING_APPROVAL
                                           │           │
                                  (all resolved)  (any rejected)
                                           │           │
                                           ▼           ▼
                                      APPROVED     REJECTED
                                           │
                                           ▼
                                      EVALUATING → EVALUATED
                                           │
                                           ▼
                                      GENERATING_SCOREBOARD → COMPLETED
```

## API Endpoints (M7)

| Method | Path | Node |
|--------|------|------|
| `POST` | `/api/pipeline/trigger` | Starts pipeline (Nodes 1→2→HITL) |
| `GET` | `/api/pipeline/status/{run_id}` | Queries pipeline status |
| `GET` | `/api/pipeline/result/{run_id}` | Returns verdicts + scoreboard |
| `GET` | `/api/pipeline/hitl` | Lists HITL review items |
| `POST` | `/api/pipeline/hitl/{fsm_id}/approve` | Approves FSM at HITL gate |
| `POST` | `/api/pipeline/hitl/{fsm_id}/reject` | Rejects FSM at HITL gate |
| `POST` | `/api/pipeline/hitl/{fsm_id}/amend` | Amends FSM at HITL gate |
| `POST` | `/api/telemetry/ingest` | Ingests broker telemetry |
| `GET` | `/api/telemetry/query` | Queries ingested telemetry |
| `GET` | `/api/reports/generate/{run_id}` | Generates audit report |
| `GET` | `/api/reports/{report_id}` | Retrieves stored report |

## Data Flow (Complete)

```
[Circular PDF]
     │
     ▼ pdf_ingest.extract_text()
[raw_text: str]
     │
     ▼ parse_circular(llm_client) → M1
[obligation_clauses: List[ObligationClause]]
     │
     ▼ extract_fsms(llm_client) → M2
[extracted_fsms: List[HybridFSM]]
     │
     ▼ hitl_gate_node() → M4 — PAUSE
[locked_fsms: List[LockedFSM]] ← API-driven review (approve/reject/amend)
     │                            persist_locked_fsms() → data/locked_fsms/{run_id}/
     ▼ (on all-resolved)
[evaluator_node()] → M5
     │
     ▼
[compliance_verdicts: List[ComplianceVerdict]]
     │
     ▼ generate_scoreboard() → M6
[scoreboard: Scoreboard + hash_chain: HashChain]
     │
     ▼
[REST API response — 12 endpoints]
     │
     ▼
[React Dashboard — trigger, HITL review, telemetry, reports, FSM viewer]
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

## Graph Changes

| Date | Change | Description |
|------|--------|-------------|
| 2026-07-03 | Initial topology | V1 topology with HITL conditional edge |
| 2026-07-03 | M4 complete | HITL gate implemented |
| 2026-07-03 | M5 complete | Evaluator implemented (deterministic, no LLM) |
| 2026-07-04 | M6 complete | Scoreboard generator implemented |
| 2026-07-04 | M7 complete | LangGraph wiring + FastAPI orchestration layer |
| 2026-07-04 | M8 complete | React dashboard + typed API client + Zustand store |
| 2026-07-04 | M9 complete | 26 integration tests, demo script, state bridge fix, V1 final validation |

## State Bridge Implementation (M9 Fix)

The `graph.py` state bridge was fixed in M9 to preserve Pydantic sub-model types:

```python
def _state_to_dict(state: CompliancePipelineState) -> dict[str, Any]:
    """Return dict with Pydantic sub-models preserved (NOT serialised)."""
    return {
        "run_id": state.run_id,
        "status": state.status,
        "circular_id": state.circular_id,
        # ... all fields listed explicitly, preserving types
        "obligation_clauses": state.obligation_clauses,  # List[ObligationClause]
        "extracted_fsms": state.extracted_fsms,           # List[HybridFSM]
        "locked_fsms": state.locked_fsms,                 # List[LockedFSM]
        # ...
    }
```

`model_dump()` was replaced because it serialized sub-models to plain dicts, which broke `extract_fsms()` (expects `ObligationClause.model_dump()`) and `create_locked_fsms()` (expects `HybridFSM.fsm_id`).

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| test_models.py | 68 | ✅ |
| test_parser.py | 35 | ✅ |
| test_fsm.py | 34 | ✅ |
| test_hash_chain.py | 20 | ✅ |
| test_hitl.py | 46 | ✅ |
| test_evaluator.py | 69 | ✅ |
| test_scoreboard.py | 38 | ✅ |
| test_orchestration.py | 53 | ✅ |
| test_integration.py | 26 | ✅ |
| **Total** | **389** | **0 failed** |

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
