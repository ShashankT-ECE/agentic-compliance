"""
Compliance pipeline graph definition (M7).

Orchestrates the execution order of pipeline nodes as a LangGraph StateGraph:

  [Parser] → [FSM Extractor] → [HITL Gate] → (conditional)
                                                    ├── all resolved → [Evaluator] → [Scoreboard] → END
                                                    └── any rejected → END (re-extraction via API)

The HITL gate pauses the pipeline at AWAITING_APPROVAL.  Human reviewers
approve/reject/amend FSMs via the API, then the pipeline is resumed.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.pipeline.state import CompliancePipelineState, PipelineStatus

logger = logging.getLogger(__name__)

# Node names (used as keys in the StateGraph)
PARSER = "parser"
FSM_EXTRACTOR = "fsm_extractor"
HITL_GATE = "hitl_gate"
EVALUATOR = "evaluator"
SCOREBOARD = "scoreboard"


# =========================================================================
# State conversion helpers
# =========================================================================

def _state_to_dict(state: CompliancePipelineState) -> dict[str, Any]:
    """Return a dict view of *state* with Pydantic sub-models preserved.

    The existing M1-M6 node functions expect ``dict.get()`` access but
    need the actual Pydantic model instances (ObligationClause, HybridFSM,
    LockedFSM) — not serialised dicts.  We construct the dict manually
    rather than calling ``model_dump()`` to avoid losing type information.
    """
    return {
        "run_id": state.run_id,
        "status": state.status,
        "circular_id": state.circular_id,
        "circular_path": state.circular_path,
        "telemetry_events": state.telemetry_events,
        "raw_text": state.raw_text,
        "obligation_clauses": state.obligation_clauses,
        "extracted_fsms": state.extracted_fsms,
        "locked_fsms": state.locked_fsms,
        "approved_by": state.approved_by,
        "approved_at": state.approved_at,
        "hitl_notes": state.hitl_notes,
        "compliance_verdicts": state.compliance_verdicts,
        "scoreboard": state.scoreboard,
        "hash_chain_root": state.hash_chain_root,
        "errors": state.errors,
        "node_timings": state.node_timings,
        "metadata": state.metadata,
    }


def _dict_to_state(state: CompliancePipelineState, updates: dict[str, Any]) -> dict[str, Any]:
    """Return a dict of updates to apply to the state.

    We return the updates as a plain dict — LangGraph will merge them
    into the BaseModel state via its reducer logic.
    """
    return updates


# =========================================================================
# Node implementations (thin wrappers around existing business logic)
# =========================================================================


async def parser_node(state: CompliancePipelineState, llm_client: Any) -> dict[str, Any]:
    """Node 1: PDF Parser — extract obligations from circular PDF."""
    from app.pipeline.nodes.parser import parser_node as _parser_node
    state_dict = _state_to_dict(state)
    result = await _parser_node(state_dict, llm_client)
    return result


async def fsm_extractor_node(state: CompliancePipelineState, llm_client: Any) -> dict[str, Any]:
    """Node 2: FSM Extractor — generate HybridFSMs from obligations."""
    from app.pipeline.nodes.fsm_extractor import fsm_extractor_node as _fsm_node
    state_dict = _state_to_dict(state)
    result = await _fsm_node(state_dict, llm_client)
    return result


def hitl_gate_node(state: CompliancePipelineState) -> dict[str, Any]:
    """HITL Gate: create LockedFSM records and pause for human review."""
    from app.pipeline.nodes.hitl_gate import hitl_gate_node as _hitl_node
    state_dict = _state_to_dict(state)
    return _hitl_node(state_dict)


def evaluator_node(state: CompliancePipelineState) -> dict[str, Any]:
    """Node 3: Assertion Evaluator — deterministic compliance evaluation.

    Reads approved/amended LockedFSMs and telemetry events from state,
    produces compliance verdicts.
    """
    from app.pipeline.nodes.evaluator import evaluate_compliance
    from app.models.locked_fsm import LockStatus

    locked_fsms = state.locked_fsms
    if not locked_fsms:
        logger.warning("Evaluator: no locked_fsms in state — skipping")
        return {}

    # Filter to approved or amended
    active = [lf for lf in locked_fsms if lf.status in (LockStatus.APPROVED, LockStatus.AMENDED)]
    telemetry = state.telemetry_events

    logger.info("Evaluator: evaluating %d approved FSM(s) against %d event(s)", len(active), len(telemetry))

    verdicts = evaluate_compliance(active, telemetry)
    return {"compliance_verdicts": verdicts}


def scoreboard_node(state: CompliancePipelineState) -> dict[str, Any]:
    """Node 4: Scoreboard Generator — aggregate verdicts into a scoreboard."""
    from app.pipeline.nodes.scoreboard import generate_scoreboard

    verdicts = state.compliance_verdicts
    circular_id = state.circular_id
    run_id = state.run_id

    logger.info("Scoreboard: generating from %d verdict(s) for run '%s'", len(verdicts), run_id)

    scoreboard = generate_scoreboard(
        verdicts=verdicts,
        circular_id=circular_id,
        metadata={"run_id": run_id, "pipeline_version": "1.0"},
    )
    return {
        "scoreboard": scoreboard,
        "hash_chain_root": scoreboard.hash_chain.root_hash if scoreboard.hash_chain else None,
    }


# =========================================================================
# Conditional edge: decide after HITL gate
# =========================================================================


def _after_hitl(state: CompliancePipelineState) -> Literal["evaluator", "__end__"]:
    """Route after the HITL gate.

    If all FSMs are resolved (approved or amended), proceed to evaluator.
    If any are rejected, end the pipeline (re-extraction handled via API).
    If still awaiting review, the pipeline is paused externally.
    """
    from app.models.locked_fsm import LockStatus

    locked_fsms = state.locked_fsms

    # If locked_fsms is empty, we're still waiting — pause
    if not locked_fsms:
        return END

    pending = [lf for lf in locked_fsms if lf.status == LockStatus.PENDING_REVIEW]
    rejected = [lf for lf in locked_fsms if lf.status == LockStatus.REJECTED]

    if pending:
        logger.info("HITL: %d FSM(s) still pending review — pausing", len(pending))
        return END

    if rejected:
        logger.warning("HITL: %d FSM(s) rejected — terminating pipeline", len(rejected))
        return END

    logger.info("HITL: all %d FSM(s) resolved — proceeding to evaluator", len(locked_fsms))
    return EVALUATOR


# =========================================================================
# Graph construction
# =========================================================================


def build_pipeline_graph() -> StateGraph:
    """Build and return the compliance pipeline StateGraph.

    Topology:
        parser → fsm_extractor → hitl_gate → (conditional)
            ├── evaluator → scoreboard → END
            └── END (pause or reject)

    The graph is NOT compiled — call .compile() on the returned StateGraph
    with the desired interrupt_before and checkpointer configuration.

    Returns:
        A LangGraph StateGraph ready for compilation.
    """
    graph = StateGraph(CompliancePipelineState)

    # Register nodes
    graph.add_node(PARSER, parser_node)
    graph.add_node(FSM_EXTRACTOR, fsm_extractor_node)
    graph.add_node(HITL_GATE, hitl_gate_node)
    graph.add_node(EVALUATOR, evaluator_node)
    graph.add_node(SCOREBOARD, scoreboard_node)

    # Linear edges
    graph.add_edge(PARSER, FSM_EXTRACTOR)
    graph.add_edge(FSM_EXTRACTOR, HITL_GATE)

    # Conditional edge after HITL
    graph.add_conditional_edges(HITL_GATE, _after_hitl, {
        EVALUATOR: EVALUATOR,
        END: END,
    })

    # Evaluator → Scoreboard → END
    graph.add_edge(EVALUATOR, SCOREBOARD)
    graph.add_edge(SCOREBOARD, END)

    # Entry point
    graph.set_entry_point(PARSER)

    logger.info("Pipeline graph built: parser → fsm_extractor → hitl_gate → [conditional] → evaluator → scoreboard")
    return graph
