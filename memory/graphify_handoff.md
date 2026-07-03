# Graphify Handoff

> **Purpose**: Pipeline graph topology, state, and node/edge information for the Graphify visualization integration.
> **Updated**: Only when the pipeline graph structure changes.

---

## Graph Status

**Defined and accepted.** The pipeline graph topology is finalized for V1. No structural changes expected.

---

## Pipeline Topology

```
[Node 1: PDF Parser] ──→ [Node 2: FSM Extractor] ──→ [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]
                                                          │
                                                          │ (if rejected/corrections needed)
                                                          └──→ [Node 2: FSM Extractor] (re-extract/amend)
```

| Aspect | Detail |
|--------|--------|
| **Type** | Directed acyclic graph (DAG) with conditional branch |
| **Orchestration** | LangGraph |
| **Nodes** | 4 pipeline nodes + 1 HITL gate (external) |
| **Edges** | 4 sequential (always) + 1 conditional (HITL rejection → back to Node 2) |
| **State object** | Shared `CompliancePipelineState` flows through all nodes |

## Nodes

| ID | Name | LLM? | Input | Output |
|----|------|------|-------|--------|
| 1 | PDF Parser | ✅ Yes | Circular PDF path | `List[ObligationClause]` — structured clauses with timeline metadata |
| 2 | FSM Extractor | ✅ Yes | `List[ObligationClause]` | `List[HybridFSM]` — state machines with timeline conditions |
| — | HITL Gate | ❌ Human | `List[HybridFSM]` | Approved `List[HybridFSM]` (or rejection → re-extract) |
| 3 | Assertion Evaluator | ❌ Never | `List[HybridFSM]` + `List[TelemetryEvent]` | `List[ComplianceVerdict]` — per-obligation pass/fail with evidence |
| 4 | Scoreboard Generator | Format only | `List[ComplianceVerdict]` | `Scoreboard` — aggregated, hash-chained audit record |

## Edges

| From | To | Condition | Description |
|------|----|-----------|-------------|
| Node 1 | Node 2 | Always | Parsed clauses flow to FSM extractor |
| Node 2 | HITL | Always | Extracted FSMs presented for human review |
| HITL | Node 3 | On approval | Locked FSMs released to evaluator |
| HITL | Node 2 | On rejection/correction | FSMs sent back with human amendments |
| Node 3 | Node 4 | Always | Verdicts flow to scoreboard builder |

## Pipeline State Schema (Core Fields)

```
CompliancePipelineState:
  circular_id: str                    # SEBI circular reference number
  circular_path: str | None           # Path to source PDF
  raw_text: str | None                # Extracted PDF text (Node 1 output)
  obligation_clauses: List[ObligationClause] | None  # Parsed clauses (Node 1 output)
  extracted_fsms: List[HybridFSM] | None              # Generated FSMs (Node 2 output)
  locked_fsms: List[LockedFSM] | None                  # Approved FSMs (HITL output)
  telemetry_events: List[TelemetryEvent] | None        # Broker event data (external input)
  compliance_verdicts: List[ComplianceVerdict] | None  # Evaluation results (Node 3 output)
  scoreboard: Scoreboard | None                        # Final output (Node 4 output)
  status: PipelineStatus                # Overall pipeline execution status
  errors: List[PipelineError]           # Error log for observability
  hash_chain_root: str | None           # Root hash of the integrity chain
```

### Key Data Model Types (abbreviated)

| Type | Description |
|------|-------------|
| `ObligationClause` | Structured compliance requirement: circular_ref, clause_text, obligation_type (timeline/threshold/procedure), effective_date, applicable_entities, timeline_params (offset, grace_period, unit) |
| `HybridFSM` | State machine: states (PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT), transitions (triggering_events + conditions), timeline_rules (deadline_calculations), metadata (obligation_ref, circular_ref) |
| `LockedFSM` | `HybridFSM` + approved_by, approved_at, hash (SHA-256 of serialized FSM), previous_hash |
| `TelemetryEvent` | Source event: broker_id, event_type, timestamp, payload (dict), event_id |
| `ComplianceVerdict` | Result: obligation_ref, broker_id, status (COMPLIANT/NON_COMPLIANT/PENDING), current_state, evidence (matched_events, timeline_status), evaluated_at |
| `Scoreboard` | Aggregated: circular_id, broker_summaries: List[BrokerScore], hash_chain (root_hash, chain: List[HashLink]), generated_at |

## Graph Changes

| Date | Change | Description |
|------|--------|-------------|
| 2026-07-03 | Initial topology | V1 topology finalized with HITL conditional edge |
