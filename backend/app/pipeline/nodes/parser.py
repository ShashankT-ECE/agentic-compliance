"""
Pipeline node — Circular Parser (Node 1).

Ingests SEBI circular PDFs (via pdf_ingest) or raw text slices and extracts
structured obligation clauses using LLM assistance. This is the entry point
of the compliance pipeline.

Architecture:
  1. Raw text is extracted from PDF (pdf_ingest.extract_text)
  2. Text is fed to an LLM with a structured prompt (prompts/parser_prompt.md)
  3. LLM response is parsed and validated into List[ObligationClause]
  4. Validated clauses are returned for downstream FSM extraction (Node 2)

LLM boundary: The parser calls an LLM to extract structured clauses from
unstructured regulatory text. The abstraction (LLMClient) makes the backend
swappable (DeepSeek, OpenAI, etc.).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.models.obligation import ObligationClause, ObligationType, TimelineParams
from app.utils.llm_client import LLMClient, LLMClientError
from app.utils.pdf_ingest import PdfIngestError, extract_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt management
# ---------------------------------------------------------------------------

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPT_DIR / "parser_prompt.md"


def load_prompt_template(prompt_path: str | Path | None = None) -> str:
    """Load the parser prompt template from disk.

    Args:
        prompt_path: Path to the prompt markdown file. Defaults to
                     ``backend/app/prompts/parser_prompt.md``.

    Returns:
        The prompt template as a string.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = Path(prompt_path) if prompt_path else _DEFAULT_PROMPT_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Parser prompt template not found: {path}\n"
            f"Ensure the prompt file exists at the expected location."
        )

    template = path.read_text(encoding="utf-8")
    logger.debug("Loaded prompt template from %s (%d chars)", path, len(template))
    return template


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------


def _extract_json_from_response(raw_response: str) -> list[dict[str, Any]]:
    """Extract a JSON array from the LLM's raw text response.

    Handles common LLM output patterns:
      - Pure JSON: ``[{...}, {...}]``
      - Markdown-fenced:  ```json [...] ```
      - With leading/trailing text.

    Args:
        raw_response: Raw text returned by the LLM.

    Returns:
        Parsed list of clause dicts.

    Raises:
        ValueError: If no valid JSON array can be extracted.
    """
    # Attempt 1: Try parsing raw response directly
    stripped = raw_response.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            data = json.loads(stripped)
            if isinstance(data, list):
                logger.debug("Parsed JSON directly from LLM response")
                return data
        except json.JSONDecodeError:
            pass

    # Attempt 2: Extract from markdown JSON fence
    fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    matches = re.findall(fence_pattern, raw_response, re.DOTALL)
    for match in matches:
        candidate = match.strip()
        if candidate.startswith("["):
            try:
                data = json.loads(candidate)
                if isinstance(data, list):
                    logger.debug("Parsed JSON from markdown fence")
                    return data
            except json.JSONDecodeError:
                continue

    # Attempt 3: Find the outermost JSON array
    array_pattern = r"\[.*\]"
    array_matches = re.findall(array_pattern, raw_response, re.DOTALL)
    for candidate in array_matches:
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                logger.debug("Parsed JSON from extracted array")
                return data
        except json.JSONDecodeError:
            continue

    logger.error("Failed to extract JSON array from LLM response (%d chars)", len(raw_response))
    raise ValueError(
        "Could not extract a valid JSON array from the LLM response. "
        "The response did not contain a parseable JSON array of clause objects. "
        f"Response preview: {raw_response[:300]}..."
    )


def _parse_clause_dict(data: dict[str, Any], circular_ref: str) -> ObligationClause:
    """Parse and validate a single clause dict into an ObligationClause.

    Args:
        data: Raw dict from LLM response.
        circular_ref: Circular reference string (used if missing from LLM output).

    Returns:
        Validated ObligationClause instance.

    Raises:
        ValueError: If the clause data fails Pydantic validation.
    """
    # Ensure circular_ref is present
    if "circular_ref" not in data or not data["circular_ref"]:
        data["circular_ref"] = circular_ref

    # Normalize obligation_type to enum value
    if "obligation_type" in data:
        raw_type = str(data["obligation_type"]).lower().strip()
        type_map = {
            "timeline": ObligationType.TIMELINE,
            "threshold": ObligationType.THRESHOLD,
            "procedure": ObligationType.PROCEDURE,
        }
        if raw_type in type_map:
            data["obligation_type"] = type_map[raw_type]

    # Parse nested timeline_params if present
    if "timeline_params" in data and isinstance(data["timeline_params"], dict):
        tp = data["timeline_params"]
        data["timeline_params"] = TimelineParams(
            offset=int(tp.get("offset", 0)),
            grace_period=int(tp.get("grace_period", 0)),
            unit=str(tp.get("unit", "days")),
        )

    # Validate through Pydantic
    return ObligationClause.model_validate(data)


# ---------------------------------------------------------------------------
# Main parser function
# ---------------------------------------------------------------------------


async def parse_circular(
    raw_text: str,
    circular_ref: str,
    llm_client: LLMClient,
    *,
    prompt_path: str | Path | None = None,
) -> list[ObligationClause]:
    """Parse raw circular text into structured obligation clauses.

    This is the primary entry point for Node 1 (PDF Parser). It sends the
    circular text to the LLM with a structured prompt, parses the JSON
    response, and validates every clause through the Pydantic model.

    Args:
        raw_text: Full text extracted from the SEBI circular PDF.
        circular_ref: SEBI circular reference number (e.g.,
                      'SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2024/001').
        llm_client: LLM backend instance (e.g., DeepSeekClient or MockLLMClient).
        prompt_path: Optional override for the prompt template path.

    Returns:
        List of validated ObligationClause instances.

    Raises:
        ValueError: If raw_text is empty, LLM response cannot be parsed,
                    or no valid clauses are extracted.
        LLMClientError: If the LLM API call fails.
        FileNotFoundError: If the prompt template is missing.
    """
    if not raw_text.strip():
        raise ValueError("raw_text is empty — cannot parse obligations from empty input")

    logger.info(
        "Parsing circular '%s': text_len=%d chars",
        circular_ref,
        len(raw_text),
    )

    # 1. Load the prompt template
    system_prompt = load_prompt_template(prompt_path)

    # 2. Build the user message with the circular text
    user_message = f"CIRCULAR REFERENCE: {circular_ref}\n\nCIRCULAR TEXT:\n\n{raw_text}"

    # 3. Call the LLM
    try:
        raw_response = await llm_client.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.1,  # Low temperature for deterministic extraction
        )
    except LLMClientError:
        logger.exception("LLM call failed for circular '%s'", circular_ref)
        raise

    # 4. Extract JSON array from the LLM response
    try:
        clause_dicts = _extract_json_from_response(raw_response)
    except ValueError:
        logger.exception("Failed to parse LLM response for circular '%s'", circular_ref)
        raise

    if not clause_dicts:
        raise ValueError(
            f"No obligation clauses extracted from circular '{circular_ref}'. "
            "The LLM returned an empty array — the circular text may not contain "
            "recognizable obligations, or the prompt may need tuning."
        )

    # 5. Validate each clause through Pydantic
    clauses: list[ObligationClause] = []
    parse_errors: list[str] = []

    for i, clause_dict in enumerate(clause_dicts):
        try:
            clause = _parse_clause_dict(clause_dict, circular_ref)
            clauses.append(clause)
            logger.debug(
                "Clause %d/%d validated: id=%s, type=%s",
                i + 1,
                len(clause_dicts),
                clause.clause_id,
                clause.obligation_type.value,
            )
        except Exception as exc:
            error_msg = f"Clause {i}: {exc}"
            parse_errors.append(error_msg)
            logger.warning("Failed to parse clause %d: %s", i, exc)

    # 6. Report results
    if parse_errors:
        logger.warning(
            "%d/%d clauses failed validation for circular '%s'",
            len(parse_errors),
            len(clause_dicts),
            circular_ref,
        )

    if not clauses:
        raise ValueError(
            f"All {len(clause_dicts)} extracted clauses failed Pydantic validation "
            f"for circular '{circular_ref}'. Errors: {'; '.join(parse_errors[:5])}"
        )

    logger.info(
        "Parsed %d valid obligation clauses from circular '%s' (%d rejected)",
        len(clauses),
        circular_ref,
        len(parse_errors),
    )

    return clauses


# ---------------------------------------------------------------------------
# Pipeline node entry point (for LangGraph integration in M7)
# ---------------------------------------------------------------------------


async def parser_node(state: dict[str, Any], llm_client: LLMClient) -> dict[str, Any]:
    """LangGraph node function for the PDF Parser.

    Reads ``circular_path`` and ``circular_id`` from pipeline state,
    extracts text via pdf_ingest, parses obligations via LLM, and writes
    the result to ``obligation_clauses`` in the state.

    Args:
        state: Pipeline state dict (CompliancePipelineState-compatible).
        llm_client: LLM backend instance.

    Returns:
        Updated state dict with ``raw_text`` and ``obligation_clauses`` populated.
    """
    circular_path = state.get("circular_path")
    circular_id = state.get("circular_id", "UNKNOWN")

    if not circular_path:
        raise ValueError("Pipeline state missing 'circular_path' — cannot parse PDF")

    logger.info("Parser node: extracting text from %s", circular_path)

    try:
        raw_text = extract_text(circular_path)
    except PdfIngestError as exc:
        logger.exception("PDF extraction failed: %s", exc)
        raise

    state["raw_text"] = raw_text

    clauses = await parse_circular(
        raw_text=raw_text,
        circular_ref=circular_id,
        llm_client=llm_client,
    )

    state["obligation_clauses"] = clauses
    logger.info("Parser node complete: %d clauses extracted", len(clauses))

    return state
