"""LLM errors as the code really sees them, for tests.

A failed Anthropic call reaches dataing as the SDK's error, wrapped by pydantic-ai,
wrapped again by AgentClient's LLMError.
"""

from __future__ import annotations

from typing import Any

import anthropic
import httpx2
from pydantic_ai.exceptions import ModelHTTPError

from dataing.core.exceptions import LLMError

MODEL = "claude-sonnet-4-20250514"
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def api_body(error_type: str, message: str) -> dict[str, Any]:
    """Return an Anthropic error response body."""
    return {"type": "error", "error": {"type": error_type, "message": message}}


def anthropic_error(status: int, body: dict[str, Any] | None = None) -> LLMError:
    """Return the error AgentClient raises when Anthropic answers with this status."""
    sdk_error = anthropic.APIStatusError(
        f"Error code: {status}",
        response=httpx2.Response(status, request=REQUEST, json=body or {}),
        body=body,
    )
    model_error = ModelHTTPError(status_code=status, model_name=MODEL, body=body)
    model_error.__cause__ = sdk_error
    wrapped = LLMError(f"LLM call failed: {model_error}", retryable=False)
    wrapped.__cause__ = model_error
    return wrapped
