# Graphify Handoff

> **Purpose**: Pipeline graph topology, state, and node/edge information for the Graphify visualization integration.
> **Updated**: Only when the pipeline graph structure changes.

---

## Graph Status

**Not yet configured.**

The pipeline graph structure is defined but the Graphify MCP server integration has not been implemented. This file will be populated once the LangGraph pipeline is wired and ready for visualization.

---

## Pipeline Topology (Planned)

```
[Node 1: PDF Parser] ──→ [Node 2: FSM Extractor] ──→ [HITL Gate] ──→ [Node 3: Evaluator] ──→ [Node 4: Scoreboard]
```

| Aspect | Detail |
|--------|--------|
| **Type** | Directed acyclic graph (DAG) |
| **Orchestration** | LangGraph |
| **Nodes** | 4 |
| **Edges** | 3 (sequential) + 1 conditional (HITL) |
| **State object** | Shared pipeline state through all nodes |

## Nodes

| ID | Name | LLM? | Description |
|----|------|------|-------------|
| 1 | PDF Parser | ✅ Yes | Parse circular PDFs → structured obligations |
| 2 | FSM Extractor | ✅ Yes | Obligations → finite state machines |
| 3 | Assertion Evaluator | ❌ Never | Telemetry × FSM → compliance verdicts |
| 4 | Scoreboard Generator | Format only | Verdicts → audit scoreboard |

## Edges

| From | To | Condition |
|------|----|-----------|
| Node 1 | Node 2 | Always |
| Node 2 | HITL | Always (human approval required) |
| HITL | Node 3 | On approval |
| Node 3 | Node 4 | Always |

## Graph Changes

| Date | Change | Description |
|------|--------|-------------|
| — | — | — |
