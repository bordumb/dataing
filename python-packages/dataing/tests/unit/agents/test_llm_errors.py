"""Classifying LLM errors (docs/specs/0001_issue_chat.md §7.12).

Each case builds the exception chain the code really sees: the Anthropic SDK's error,
wrapped by pydantic-ai, wrapped again by AgentClient's LLMError.
"""

from __future__ import annotations

import anthropic
import httpx2
import pytest
from fixtures.llm_errors import MODEL, REQUEST, anthropic_error, api_body
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.providers.anthropic import AnthropicProvider

from dataing.agents.errors import classify_llm_error
from dataing.core.exceptions import LLMError


@pytest.mark.parametrize(
    ("status", "code", "retryable", "message"),
    [
        (
            401,
            "invalid_key",
            False,
            "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and "
            "restart the API and the worker.",
        ),
        (403, "forbidden", False, f"The API key isn't allowed to use {MODEL} (403)."),
        (
            404,
            "unknown_model",
            False,
            f"Anthropic doesn't know the model {MODEL} (404). "
            "Check LLM_MODEL and CHAT_AGENT_MODEL.",
        ),
        (429, "rate_limited", True, "Anthropic rate-limited the request (429)."),
        (529, "overloaded", True, "Anthropic is overloaded (529)."),
        (500, "server_error", True, "Anthropic returned an error (500)."),
        (503, "server_error", True, "Anthropic returned an error (503)."),
    ],
)
def test_status_codes_map_to_a_code_and_what_to_fix(
    status: int, code: str, retryable: bool, message: str
) -> None:
    """Each HTTP status the API returns maps to one code, retryability and message."""
    failure = classify_llm_error(anthropic_error(status))

    assert failure is not None
    assert (failure.code, failure.retryable, failure.message) == (code, retryable, message)
    assert failure.status_code == status


@pytest.mark.parametrize("status", [400, 413, 422])
def test_rejected_requests_carry_the_api_detail(status: int) -> None:
    """A request the API refuses says why, in the API's words, and isn't retried."""
    body = api_body("invalid_request_error", "Your credit balance is too low")

    failure = classify_llm_error(anthropic_error(status, body))

    assert failure is not None
    assert failure.code == "bad_request"
    assert not failure.retryable
    assert failure.message == (
        f"Anthropic rejected the request ({status}): Your credit balance is too low"
    )


def test_connection_errors_are_retryable() -> None:
    """pydantic-ai maps a connection error to ModelAPIError; it is worth retrying."""
    sdk_error = anthropic.APIConnectionError(request=REQUEST)
    model_error = ModelAPIError(model_name=MODEL, message=sdk_error.message)
    model_error.__cause__ = sdk_error

    failure = classify_llm_error(model_error)

    assert failure is not None
    assert (failure.code, failure.retryable) == ("unreachable", True)
    assert failure.message == "Couldn't reach Anthropic: Connection error."


def test_direct_sdk_errors_are_classified_too() -> None:
    """The key check calls the SDK directly, without pydantic-ai in between."""
    response = httpx2.Response(401, request=REQUEST, json=api_body("authentication_error", "x"))
    sdk_error = anthropic.AuthenticationError("Error code: 401", response=response, body=None)

    failure = classify_llm_error(sdk_error)

    assert failure is not None
    assert failure.code == "invalid_key"


def test_sdk_timeouts_are_unreachable() -> None:
    """A timeout is a connection problem: retry it."""
    failure = classify_llm_error(anthropic.APITimeoutError(request=REQUEST))

    assert failure is not None
    assert (failure.code, failure.retryable) == ("unreachable", True)


def test_a_missing_key_is_reported_without_a_request() -> None:
    """pydantic-ai refuses to build a provider without a key."""
    with pytest.raises(Exception) as caught:
        AnthropicProvider(api_key="")

    failure = classify_llm_error(caught.value)

    assert failure is not None
    assert (failure.code, failure.retryable) == ("missing_key", False)
    assert failure.message == (
        "ANTHROPIC_API_KEY isn't set. Set it and restart the API and the worker."
    )


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("LLM request timed out"),
        LLMError("Synthesis failed: bad output"),
        UnexpectedModelBehavior("Exceeded maximum retries (3) for output validation"),
    ],
)
def test_other_errors_are_not_llm_api_failures(error: Exception) -> None:
    """Only errors from the API or its client are classified; the rest keep their path."""
    assert classify_llm_error(error) is None


def test_to_dict_carries_code_and_message() -> None:
    """The dict form travels in Temporal error details and outcome payloads."""
    failure = classify_llm_error(anthropic_error(401))

    assert failure is not None
    assert failure.to_dict() == {"code": "invalid_key", "message": failure.message}
