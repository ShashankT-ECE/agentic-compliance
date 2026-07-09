"""
LLM client abstraction and DeepSeek implementation.

Provides a swappable LLM backend for pipeline nodes that require
LLM assistance (Nodes 1 and 2). The abstraction uses a simple
protocol so backends can be swapped without changing node logic.

M1 implements the DeepSeek backend (OpenAI-compatible API).
Future milestones can add other backends (OpenAI, Anthropic, etc.).
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Client abstraction
# ---------------------------------------------------------------------------


class LLMClient(ABC):
    """Abstract base for LLM backends.

    Each pipeline node that needs LLM assistance receives an LLMClient
    instance. The abstraction makes the backend swappable without changing
    node logic.
    """

    @abstractmethod
    async def generate(self, system_prompt: str, user_message: str, *, temperature: float = 0.1) -> str:
        """Send a prompt to the LLM and return the raw text response.

        Args:
            system_prompt: The system-level instruction (role, format, rules).
            user_message: The user-level input (circular text to parse).
            temperature: Sampling temperature (low = deterministic, default 0.1).

        Returns:
            Raw text response from the LLM.

        Raises:
            LLMClientError: On API failure, timeout, or unexpected response.
        """
        ...


class LLMClientError(Exception):
    """Raised when the LLM backend fails to return a valid response."""

    def __init__(self, message: str, *, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# DeepSeek implementation
# ---------------------------------------------------------------------------


class DeepSeekClient(LLMClient):
    """LLM client for the DeepSeek API (OpenAI-compatible endpoint).

    Environment variables:
        DEEPSEEK_API_KEY: API key (required).
        DEEPSEEK_BASE_URL: Base URL (default: https://api.deepseek.com/v1).
        DEEPSEEK_MODEL: Model name (default: deepseek-chat).
        DEEPSEEK_TIMEOUT: Request timeout in seconds (default: 300).

    Usage:
        client = DeepSeekClient()
        response = await client.generate(system_prompt, user_text)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        env_timeout = os.getenv("DEEPSEEK_TIMEOUT")
        self.timeout = float(env_timeout) if env_timeout else timeout

        if not self.api_key:
            logger.warning(
                "DEEPSEEK_API_KEY not set — DeepSeekClient will fail at runtime. "
                "Set the environment variable or pass api_key explicitly."
            )

    async def generate(self, system_prompt: str, user_message: str, *, temperature: float = 0.1) -> str:
        """Call the DeepSeek chat completions endpoint."""
        url = f"{self.base_url}/chat/completions"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": 65536,
        }

        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info("Calling DeepSeek API: model=%s, prompt_len=%d", self.model, len(user_message))

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            content: str = data["choices"][0]["message"]["content"]
            logger.info("DeepSeek response received: %d chars", len(content))
            return content

        except httpx.TimeoutException:
            logger.error("DeepSeek API timed out after %.0fs", self.timeout)
            raise LLMClientError(
                f"DeepSeek API timed out after {self.timeout}s",
                detail="Consider increasing timeout or checking network connectivity.",
            ) from None

        except httpx.HTTPStatusError as exc:
            logger.error("DeepSeek API returned HTTP %d: %s", exc.response.status_code, exc.response.text[:500])
            raise LLMClientError(
                f"DeepSeek API error (HTTP {exc.response.status_code})",
                status_code=exc.response.status_code,
                detail=exc.response.text[:1000],
            ) from exc

        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse DeepSeek response: %s", exc)
            raise LLMClientError(
                "Unexpected response format from DeepSeek API",
                detail=str(exc),
            ) from exc


# ---------------------------------------------------------------------------
# Mock client for testing
# ---------------------------------------------------------------------------


class MockLLMClient(LLMClient):
    """Mock LLM client for unit testing.

    Returns a predetermined response without making API calls.
    """

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, system_prompt: str, user_message: str, *, temperature: float = 0.1) -> str:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_message": user_message,
            "temperature": temperature,
        })
        logger.debug("MockLLMClient returning canned response (%d chars)", len(self.response))
        return self.response
