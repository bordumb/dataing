"""Classify LLM errors by what fixes them (docs/specs/0001_issue_chat.md §7.12).

The investigation and the chat agent reach Anthropic through pydantic-ai, which maps
the SDK's errors to ModelHTTPError and ModelAPIError; the key check calls the SDK
directly. classify_llm_error follows an exception's cause chain to whichever of those
it finds and says whether a retry can help and what the person should change.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UserError

RESTART = "restart the API and the worker"


@dataclass(frozen=True)
class LLMFailure:
    """Why an LLM call failed, and whether trying again can help."""

    code: str
    message: str
    retryable: bool
    status_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the code and message, as error details and outcome payloads carry them."""
        return {"code": self.code, "message": self.message}


def classify_llm_error(error: BaseException, *, model: str | None = None) -> LLMFailure | None:
    """Return why an LLM call failed, or None when the error didn't come from the API.

    Args:
        error: The exception raised by the call, however deeply it wraps the cause.
        model: The model called, for messages when the error doesn't name it.
    """
    for cause in _causes(error):
        if isinstance(cause, ModelHTTPError):
            return _from_status(cause.status_code, cause.model_name or model, cause.body)
        if isinstance(cause, anthropic.APIStatusError):
            return _from_status(cause.status_code, model, cause.body)
        if isinstance(cause, anthropic.APIConnectionError):
            return _unreachable(cause.message)
        if isinstance(cause, ModelAPIError):
            return _unreachable(cause.message)
        if isinstance(cause, UserError) and "ANTHROPIC_API_KEY" in str(cause):
            return LLMFailure(
                code="missing_key",
                message=f"ANTHROPIC_API_KEY isn't set. Set it and {RESTART}.",
                retryable=False,
            )
    return None


def _causes(error: BaseException) -> Iterator[BaseException]:
    """Yield the error and each exception it was raised from, outermost first."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _from_status(status: int, model: str | None, body: object) -> LLMFailure:
    """Map an HTTP status from the API to a failure."""
    named = model or "the configured model"
    if status == 401:
        return _rejected(
            "invalid_key",
            f"Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and {RESTART}.",
            status,
        )
    if status == 403:
        return _rejected("forbidden", f"The API key isn't allowed to use {named} (403).", status)
    if status == 404:
        return _rejected(
            "unknown_model",
            f"Anthropic doesn't know the model {named} (404). Check LLM_MODEL and "
            "CHAT_AGENT_MODEL.",
            status,
        )
    if status == 429:
        return _retryable("rate_limited", "Anthropic rate-limited the request (429).", status)
    if status == 529:
        return _retryable("overloaded", "Anthropic is overloaded (529).", status)
    if status >= 500 or status in (408, 409):
        return _retryable("server_error", f"Anthropic returned an error ({status}).", status)
    detail = _api_message(body)
    suffix = f": {detail}" if detail else ""
    return _rejected("bad_request", f"Anthropic rejected the request ({status}){suffix}", status)


def _api_message(body: object) -> str | None:
    """Return the API's own error message from a response body, if it has one."""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message: str = error["message"]
            return message
    return None


def _rejected(code: str, message: str, status: int) -> LLMFailure:
    return LLMFailure(code=code, message=message, retryable=False, status_code=status)


def _retryable(code: str, message: str, status: int) -> LLMFailure:
    return LLMFailure(code=code, message=message, retryable=True, status_code=status)


def _unreachable(detail: str) -> LLMFailure:
    return LLMFailure(
        code="unreachable", message=f"Couldn't reach Anthropic: {detail}", retryable=True
    )
