"""
Pipeline node — FSM Extractor (Node 2).

Transforms parsed obligation clauses (from Node 1) into hybrid finite state
machines (HybridFSM) using LLM assistance. Each FSM models one compliance
obligation as a state machine with embedded timeline conditions.

Architecture:
  1. Receive List[ObligationClause] from Node 1
  2. For each clause, call LLM with a structured FSM generation prompt
  3. Parse and validate LLM response into List[HybridFSM]
  4. Validate every FSM through the existing Pydantic model
  5. Persist extracted FSMs to data/extracted/ as JSON

LLM boundary: The extractor calls an LLM to generate state machine
representations from obligation text. The HybridFSM model (states,
transitions, timeline rules) is defined in M0 and enforced via Pydantic
validation — the LLM proposes, Pydantic disposes.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.fsm import FSMState, FSMTransition, HybridFSM, TimelineRule
from app.models.obligation import ObligationClause
from app.pipeline.nodes.parser import _extract_json_from_response
from app.utils.llm_client import LLMClient, LLMClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPT_DIR / "fsm_extractor_prompt.md"

_EXTRACTED_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "extracted"

# Minimum expected transitions for a well-formed FSM (event-driven + deadline)
_MIN_TRANSITIONS = 3


# ---------------------------------------------------------------------------
# Prompt management
# ---------------------------------------------------------------------------


def load_fsm_prompt_template(prompt_path: str | Path | None = None) -> str:
    """Load the FSM extractor prompt template from disk.

    Args:
        prompt_path: Path to the prompt markdown file. Defaults to
                     ``backend/app/prompts/fsm_extractor_prompt.md``.

    Returns:
        The prompt template as a string.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = Path(prompt_path) if prompt_path else _DEFAULT_PROMPT_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"FSM extractor prompt template not found: {path}\n"
            f"Ensure the prompt file exists at the expected location."
        )

    template = path.read_text(encoding="utf-8")
    logger.debug("Loaded FSM prompt template from %s (%d chars)", path, len(template))
    return template


# ---------------------------------------------------------------------------
# FSM dict parsing and validation
# ---------------------------------------------------------------------------


def _validate_fsm_states(fsm_dict: dict[str, Any]) -> None:
    """Validate that all 5 canonical states are present in the FSM dict.

    The LLM must include all five canonical states.  This function checks
    before Pydantic validation so we can give a clear error message.

    Args:
        fsm_dict: Raw FSM dict from LLM response (mutated in place).

    Raises:
        ValueError: If any canonical state is missing.
    """
    if "states" not in fsm_dict or not isinstance(fsm_dict["states"], list):
        raise ValueError("FSM dict missing 'states' array")

    state_names: set[str] = set()
    for s in fsm_dict["states"]:
        if isinstance(s, dict) and "name" in s:
            state_names.add(s["name"])

    from app.models.fsm import CANONICAL_STATES

    missing = CANONICAL_STATES - state_names
    if missing:
        raise ValueError(
            f"FSM for '{fsm_dict.get('obligation_ref', 'UNKNOWN')}' "
            f"is missing canonical states: {sorted(missing)}. "
            f"Found: {sorted(state_names)}. "
            f"All 5 states (PENDING, DUE, COMPLIANT, LATE, NON_COMPLIANT) are required."
        )


def _parse_fsm_dict(data: dict[str, Any], circular_ref: str) -> HybridFSM:
    """Parse and validate a single FSM dict into a HybridFSM.

    Performs pre-Pydantic checks (canonical states, min transitions) and
    then validates through the HybridFSM model.

    Args:
        data: Raw dict from LLM response.
        circular_ref: Circular reference (used if missing from LLM output).

    Returns:
        Validated HybridFSM instance.

    Raises:
        ValueError: If the FSM data fails pre-validation or Pydantic validation.
    """
    # Ensure circular_ref is present
    if "circular_ref" not in data or not data["circular_ref"]:
        data["circular_ref"] = circular_ref

    # Pre-validate canonical states
    _validate_fsm_states(data)

    # Ensure initial_state is PENDING
    if data.get("initial_state") != "PENDING":
        logger.warning(
            "FSM '%s' has initial_state='%s'; expected 'PENDING'. Overriding.",
            data.get("obligation_ref", "UNKNOWN"),
            data.get("initial_state"),
        )
        data["initial_state"] = "PENDING"

    # Validate transitions count
    transitions = data.get("transitions", [])
    if isinstance(transitions, list) and len(transitions) < _MIN_TRANSITIONS:
        raise ValueError(
            f"FSM for '{data.get('obligation_ref', 'UNKNOWN')}' "
            f"has only {len(transitions)} transition(s); minimum {_MIN_TRANSITIONS} required."
        )

    # Validate timeline_rules count
    timeline_rules = data.get("timeline_rules", [])
    if isinstance(timeline_rules, list) and len(timeline_rules) < 1:
        raise ValueError(
            f"FSM for '{data.get('obligation_ref', 'UNKNOWN')}' "
            f"has no timeline_rules; at least 1 required."
        )

    # Parse nested objects through Pydantic
    if "states" in data and isinstance(data["states"], list):
        data["states"] = [FSMState.model_validate(s) for s in data["states"]]

    if "transitions" in data and isinstance(data["transitions"], list):
        data["transitions"] = [FSMTransition.model_validate(t) for t in data["transitions"]]

    if "timeline_rules" in data and isinstance(data["timeline_rules"], list):
        data["timeline_rules"] = [TimelineRule.model_validate(r) for r in data["timeline_rules"]]

    # Final validation through the full HybridFSM model
    return HybridFSM.model_validate(data)


# ---------------------------------------------------------------------------
# Main extractor function
# ---------------------------------------------------------------------------


async def extract_fsms(
    clauses: list[ObligationClause],
    circular_ref: str,
    llm_client: LLMClient,
    *,
    prompt_path: str | Path | None = None,
) -> list[HybridFSM]:
    """Extract HybridFSMs from a list of obligation clauses.

    This is the primary entry point for Node 2 (FSM Extractor). It sends
    each obligation clause to the LLM with a structured FSM generation prompt,
    parses the JSON response, and validates every FSM through the Pydantic model.

    Args:
        clauses: Parsed obligation clauses from Node 1 (M1).
        circular_ref: SEBI circular reference number.
        llm_client: LLM backend instance (e.g., DeepSeekClient or MockLLMClient).
        prompt_path: Optional override for the FSM prompt template path.

    Returns:
        List of validated HybridFSM instances, one per input clause.

    Raises:
        ValueError: If clauses list is empty, LLM response cannot be parsed,
                    or no valid FSMs are extracted.
        LLMClientError: If the LLM API call fails.
        FileNotFoundError: If the prompt template is missing.
    """
    if not clauses:
        raise ValueError("clauses list is empty — cannot extract FSMs from empty input")

    logger.info(
        "Extracting FSMs for circular '%s': %d clause(s)",
        circular_ref,
        len(clauses),
    )

    # 1. Load the FSM prompt template
    system_prompt = load_fsm_prompt_template(prompt_path)

    # 2. Build the user message with all clauses as JSON
    clauses_json = json.dumps(
        [c.model_dump(mode="json") for c in clauses],
        indent=2,
        default=str,
    )
    user_message = (
        f"CIRCULAR REFERENCE: {circular_ref}\n\n"
        f"OBLIGATION CLAUSES:\n\n{clauses_json}"
    )

    # 3. Call the LLM
    try:
        raw_response = await llm_client.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.1,
        )
    except LLMClientError:
        logger.exception("LLM call failed during FSM extraction for '%s'", circular_ref)
        raise

    # 4. Extract JSON from the LLM response
    try:
        fsm_dicts = _extract_json_from_response(raw_response)
    except ValueError:
        logger.exception("Failed to parse LLM response for FSM extraction '%s'", circular_ref)
        raise

    if not fsm_dicts:
        raise ValueError(
            f"No FSMs extracted from LLM response for circular '{circular_ref}'. "
            "The LLM returned an empty array."
        )

    # 5. Validate each FSM through Pydantic
    fsms: list[HybridFSM] = []
    parse_errors: list[str] = []

    for i, fsm_dict in enumerate(fsm_dicts):
        try:
            fsm = _parse_fsm_dict(fsm_dict, circular_ref)
            fsms.append(fsm)
            logger.debug(
                "FSM %d/%d validated: id=%s, states=%d, transitions=%d, timeline_rules=%d",
                i + 1,
                len(fsm_dicts),
                fsm.fsm_id,
                len(fsm.states),
                len(fsm.transitions),
                len(fsm.timeline_rules),
            )
        except Exception as exc:
            error_msg = f"FSM {i}: {exc}"
            parse_errors.append(error_msg)
            logger.warning("Failed to parse FSM %d: %s", i, exc)

    # 6. Report results
    if parse_errors:
        logger.warning(
            "%d/%d FSMs failed validation for circular '%s'",
            len(parse_errors),
            len(fsm_dicts),
            circular_ref,
        )

    if not fsms:
        raise ValueError(
            f"All {len(fsm_dicts)} extracted FSMs failed validation "
            f"for circular '{circular_ref}'. Errors: {'; '.join(parse_errors[:5])}"
        )

    logger.info(
        "Extracted %d valid FSMs from circular '%s' (%d rejected)",
        len(fsms),
        circular_ref,
        len(parse_errors),
    )

    return fsms


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_fsms(fsms: list[HybridFSM], circular_ref: str, output_dir: str | Path | None = None) -> Path:
    """Persist extracted FSMs to disk as JSON.

    Each FSM is written to an individual JSON file under
    ``data/extracted/{circular_ref_slug}/``.  An index file listing all
    FSM IDs is also written.

    Args:
        fsms: Validated HybridFSM instances to persist.
        circular_ref: SEBI circular reference (used for directory naming).
        output_dir: Optional override for the output root directory.
                    Defaults to ``backend/data/extracted/``.

    Returns:
        Path to the directory where FSMs were written.

    Raises:
        OSError: If the output directory cannot be created or written to.
    """
    base_dir = Path(output_dir) if output_dir else _EXTRACTED_DATA_DIR

    # Derive a safe directory slug from the circular reference
    ref_slug = re.sub(r"[^A-Za-z0-9\-_]", "_", circular_ref).strip("_")[:64]
    fsm_dir = base_dir / ref_slug
    fsm_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Persisting %d FSM(s) to %s", len(fsms), fsm_dir)

    # Write individual FSM files
    written_ids: list[str] = []
    for fsm in fsms:
        filename = f"{fsm.fsm_id}.json"
        filepath = fsm_dir / filename
        filepath.write_text(
            fsm.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
        written_ids.append(fsm.fsm_id)
        logger.debug("Wrote FSM: %s", filepath)

    # Write index file
    index_path = fsm_dir / "_index.json"
    index_data = {
        "circular_ref": circular_ref,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "fsm_count": len(fsms),
        "fsm_ids": written_ids,
    }
    index_path.write_text(
        json.dumps(index_data, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("FSM index written: %s (%d entries)", index_path, len(written_ids))

    return fsm_dir


# ---------------------------------------------------------------------------
# Pipeline node entry point (for LangGraph integration in M7)
# ---------------------------------------------------------------------------


async def fsm_extractor_node(state: dict[str, Any], llm_client: LLMClient) -> dict[str, Any]:
    """LangGraph node function for the FSM Extractor.

    Reads ``obligation_clauses`` and ``circular_id`` from pipeline state,
    extracts FSMs via LLM, persists them to disk, and writes the result
    to ``extracted_fsms`` in the state.

    Args:
        state: Pipeline state dict (CompliancePipelineState-compatible).
        llm_client: LLM backend instance.

    Returns:
        Updated state dict with ``extracted_fsms`` populated.
    """
    clauses: list[ObligationClause] = state.get("obligation_clauses", [])
    circular_id: str = state.get("circular_id", "UNKNOWN")

    if not clauses:
        raise ValueError("Pipeline state has no 'obligation_clauses' — cannot extract FSMs")

    logger.info("FSM extractor node: processing %d clause(s) for '%s'", len(clauses), circular_id)

    fsms = await extract_fsms(
        clauses=clauses,
        circular_ref=circular_id,
        llm_client=llm_client,
    )

    # Persist to disk
    persist_fsms(fsms, circular_ref=circular_id)

    state["extracted_fsms"] = fsms
    logger.info("FSM extractor node complete: %d FSM(s) extracted and persisted", len(fsms))

    return state
