"""
API dependency injection helpers (M7).

Provides FastAPI dependencies for:
  - LLM client (swappable: DeepSeek / Mock)
  - Pipeline runner
  - Shared state / run store access
"""

from __future__ import annotations

import logging
from typing import Any

from app.pipeline.runner import PipelineRunner, get_run_state
from app.utils.llm_client import DeepSeekClient, LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons (lazily initialised)
# ---------------------------------------------------------------------------

_llm_client: LLMClient | None = None
_runner: PipelineRunner | None = None


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


def get_llm_client() -> LLMClient:
    """Return the shared LLM client instance.

    Creates a DeepSeekClient on first call.  If DEEPSEEK_API_KEY is not
    set, the client will log a warning but still be returned — Nodes 1/2
    will fail at runtime when they attempt to call the API.

    Override for testing by calling ``set_llm_client()``.
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = DeepSeekClient()
        logger.info("Initialised DeepSeekClient")
    return _llm_client


def set_llm_client(client: LLMClient) -> None:
    """Override the shared LLM client (for testing)."""
    global _llm_client
    _llm_client = client


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


def get_runner() -> PipelineRunner:
    """Return the shared PipelineRunner instance.

    Creates a PipelineRunner on first call, wired to the shared LLM client.
    Override for testing by calling ``set_runner()``.
    """
    global _runner
    if _runner is None:
        _runner = PipelineRunner(llm_client=get_llm_client())
        logger.info("Initialised PipelineRunner")
    return _runner


def set_runner(runner: PipelineRunner) -> None:
    """Override the shared PipelineRunner (for testing)."""
    global _runner
    _runner = runner


# ---------------------------------------------------------------------------
# Run store
# ---------------------------------------------------------------------------


def get_run(run_id: str) -> Any | None:
    """Get a pipeline run's current state by ID.

    Returns the CompliancePipelineState Pydantic model, or None if not found.
    """
    return get_run_state(run_id)
