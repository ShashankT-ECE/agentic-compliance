# Graphify Handoff

> **Purpose**: Pipeline graph topology, state, and node/edge information for the Graphify visualization integration.
> **Updated**: After M4 — HITL Gate implemented. Nodes 1, 2, and HITL Gate complete. Nodes 3, 4 pending.

---

## Graph Status

**Partial.** Nodes 1, 2, and the HITL gate are implemented and tested. Nodes 3 (Evaluator) and 4 (Scoreboard) are pending. LangGraph wiring is M7.

---

## Pipeline Topology (Current State After M4)

```
[Node 1: PDF Parser] ──→ [Node 2: FSM Extractor] ──→ [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]
       ✅ M1                      ✅ M2                    ✅ M4              🔜 M5                 🔜 M6
                                                           │
                                                           │ (if rejected)
                                                           └──→ [Node 2: FSM Extractor] (re-extract with hitl_notes)
```

| Aspect | Detail |
|--------|--------|
| **Type** | Directed acyclic graph (DAG) with conditional branch |
| **Orchestration** | LangGraph (M7 — not yet wired) |
| **Nodes implemented** | 2 pipeline nodes + 1 HITL gate |
| **Nodes pending** | 2 (Evaluator M5, Scoreboard M6) |
| **Edges** | 3 sequential (Node 1→2, Node 2→HITL, HITL→Node 3) + 1 conditional (HITL rejection → Node 2) |
| **State object** | `CompliancePipelineState` (Pydantic model, flows through all nodes) |

## Nodes

| ID | Name | LLM? | Status | Input | Output |
|----|------|------|--------|-------|--------|
| 1 | PDF Parser | ✅ Yes | ✅ M1 | Circular PDF path | `List[ObligationClause]` — structured clauses with timeline metadata |
| 2 | FSM Extractor | ✅ Yes | ✅ M2 | `List[ObligationClause]` | `List[HybridFSM]` — state machines with timeline conditions |
| — | HITL Gate | ❌ Never | ✅ M4 | `List[HybridFSM]` | `List[LockedFSM]` — human-reviewed, hash-sealed FSM snapshots |
| 3 | Assertion Evaluator | ❌ Never | 🔜 M5 | `List[LockedFSM]` + `List[TelemetryEvent]` | `List[ComplianceVerdict]` — per-obligation pass/fail with evidence |
| 4 | Scoreboard Generator | Format only | 🔜 M6 | `List[ComplianceVerdict]` | `Scoreboard` — aggregated, hash-chained audit record |

## Edges

| From | To | Condition | Status |
|------|----|-----------|--------|
| Node 1 | Node 2 | Always | ✅ Implemented |
| Node 2 | HITL | Always | ✅ Implemented |
| HITL | Node 3 | On all-resolved (all APPROVED or AMENDED) | 🔜 Pending (M7 wiring) |
| HITL | Node 2 | On any REJECTED | 🔜 Pending (M7 wiring) |
| Node 3 | Node 4 | Always | 🔜 Pending |
| Node 4 | END | Always | 🔜 Pending |

## Pipeline State Schema (After M4)

```python
CompliancePipelineState:
  # Run identity
  run_id: str                          # Unique pipeline run identifier
  status: PipelineStatus               # Current execution status

  # Input
  circular_id: str                     # SEBI circular reference (canonical: .../2025/57)
  circular_path: str | None            # Filesystem path to source PDF
  telemetry_events: list[TelemetryEvent]  # Broker event data

  # Node 1 output
  raw_text: str | None                 # Extracted PDF text
  obligation_clauses: list[ObligationClause]  # Parsed obligation clauses

  # Node 2 output
  extracted_fsms: list[HybridFSM]      # Generated FSMs

  # HITL gate output (M4 — LockedFSM type)
  locked_fsms: list[LockedFSM]         # Human-approved LockedFSMs
  approved_by: str | None              # Reviewer identity
  approved_at: datetime | None         # Approval timestamp
  hitl_notes: str | None               # Reviewer notes/rejection reasons

  # Node 3 output (pending M5)
  compliance_verdicts: list[ComplianceVerdict]  # Evaluation results

  # Node 4 output (pending M6)
  scoreboard: Scoreboard | None        # Final aggregated scoreboard

  # Integrity
  hash_chain_root: str | None          # Root hash of the integrity chain

  # Observability
  errors: list[PipelineError]          # Error log
  node_timings: dict[str, float]       # Per-node execution times
  metadata: dict[str, Any]            # Pipeline metadata
```

### PipelineStatus enum (current state)

```
CREATED → PARSING → PARSED → EXTRACTING_FSM → FSM_EXTRACTED
                                                    │
                                                    ▼
                                          AWAITING_APPROVAL  ←── (re-extracted from Node 2)
                                           │           │
                                  (all resolved)  (any rejected)
                                           │           │
                                           ▼           ▼
                                      APPROVED     REJECTED
                                           │           │
                                           ▼           ▼
                                      EVALUATING   Node 2 re-runs
                                           │
                                           ▼
                                      EVALUATED → GENERATING_SCOREBOARD → COMPLETED
```

## LockedFSM Model (M4)

```python
LockedFSM:
  # Identity
  locked_fsm_id: str              # "LOCKED-{uuid12}" — unique per locked record
  fsm_id: str                     # References HybridFSM.fsm_id
  obligation_ref: str             # References ObligationClause.clause_id
  circular_ref: str               # SEBI circular reference
  version: int                    # Starts at 1, increments on amendment

  # Content
  original_fsm: HybridFSM         # The FSM as extracted (v1) or amended (v2+)

  # Approval
  status: LockStatus              # PENDING_REVIEW | APPROVED | REJECTED | AMENDED
  reviewer: str | None            # Human reviewer identity
  reviewed_at: datetime | None    # Review timestamp
  review_comments: str | None     # Review rationale

  # Amendment history
  amendment_history: list[AmendmentRecord]  # Prior versions preserved

  # Integrity
  integrity_hash: str | None      # SHA-256 of serialized original_fsm
  hash_link: HashLink | None      # M3 hash chain anchor
```

## Hash Chain Integration (M3 → M4)

Every approved or amended LockedFSM is sealed into the hash chain:

1. `approve_fsm()` / `amend_fsm()` computes `integrity_hash = compute_hash(original_fsm.model_dump_json())`
2. A `HashLink` is created via M3 `link(previous_hash_link, link_data)`
3. `verify_locked_fsm_integrity()` recomputes the hash to detect tampering
4. `build_hitl_hash_chain()` collects all hash links into a `HashChain`
5. `verify_chain()` validates the full chain (M3)

## Data Flow Between Nodes (After M4)

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
[evaluator_node()] → M5 (pending)
     │
     ▼
[scoreboard_node()] → M6 (pending)
```

## Graph Changes

| Date | Change | Description |
|------|--------|-------------|
| 2026-07-03 | Initial topology | V1 topology finalized with HITL conditional edge |
| 2026-07-03 | M4 complete | HITL gate implemented: LockedFSM model, review workflow, API endpoints, hash chain integration |
