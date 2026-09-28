"""The API checks the Anthropic key and models at startup (docs/specs/0001_issue_chat.md §7.12).

The Anthropic client is faked: each model id either answers or raises the error
the real SDK raises for it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import anthropic
import httpx2
import pytest

from dataing.services.llm_status import LLMStatusChecker

REQUEST = httpx2.Request("GET", "https://api.anthropic.com/v1/models/x")
INVESTIGATION_MODEL = "claude-sonnet-4-20250514"
CHAT_MODEL = "claude-opus-5-5"


def _status_error(status: int) -> anthropic.APIStatusError:
    response = httpx2.Response(status, request=REQUEST, json={})
    classes: dict[int, type[anthropic.APIStatusError]] = {
        401: anthropic.AuthenticationError,
        403: anthropic.PermissionDeniedError,
        404: anthropic.NotFoundError,
    }
    return classes[status](f"Error code: {status}", response=response, body=None)


class FakeAnthropic:
    """Answers models.retrieve, raising the scripted error for a model id."""

    def __init__(self, errors: dict[str, Exception]) -> None:
        self.errors = errors
        self.retrieved: list[str] = []
        self.models = self

    async def retrieve(self, model_id: str, **_: Any) -> dict[str, str]:
        self.retrieved.append(model_id)
        if model_id in self.errors:
            raise self.errors[model_id]
        return {"id": model_id}


class Clock:
    """A clock tests can move."""

    def __init__(self) -> None:
        self.now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _checker(
    client: FakeAnthropic, *, api_key: str = "sk-test", clock: Clock | None = None
) -> LLMStatusChecker:
    return LLMStatusChecker(
        api_key=api_key,
        models=[INVESTIGATION_MODEL, CHAT_MODEL, INVESTIGATION_MODEL],
        client_factory=lambda key: client,
        clock=clock or Clock(),
    )


def test_the_status_is_checking_until_the_first_check() -> None:
    """Before the background check finishes there is nothing to report."""
    status = _checker(FakeAnthropic({})).status

    assert (status.state, status.checked_at) == ("checking", None)
    assert status.models == [INVESTIGATION_MODEL, CHAT_MODEL]


async def test_a_working_key_is_ok_for_every_model() -> None:
    """Each configured model is retrieved once."""
    client = FakeAnthropic({})

    status = await _checker(client).check()

    assert status.state == "ok"
    assert client.retrieved == [INVESTIGATION_MODEL, CHAT_MODEL]
    assert status.checked_at is not None


async def test_an_empty_key_is_reported_without_a_request() -> None:
    """With no key there is nothing to ask Anthropic."""

    def no_client(key: str) -> FakeAnthropic:
        raise AssertionError("no request without a key")

    checker = LLMStatusChecker(
        api_key="", models=[INVESTIGATION_MODEL], client_factory=no_client, clock=Clock()
    )

    status = await checker.check()

    assert status.state == "missing_key"
    assert status.message == (
        "ANTHROPIC_API_KEY isn't set. Set it and restart the API and the worker."
    )


async def test_a_rejected_key_says_what_to_fix() -> None:
    """A 401 stops the check: every model would fail the same way."""
    client = FakeAnthropic({INVESTIGATION_MODEL: _status_error(401)})

    status = await _checker(client).check()

    assert status.state == "invalid_key"
    assert status.message == (
        "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and "
        "restart the API and the worker."
    )
    assert client.retrieved == [INVESTIGATION_MODEL]


@pytest.mark.parametrize(
    ("status_code", "state", "message"),
    [
        (
            404,
            "unknown_model",
            f"Anthropic doesn't know the model {CHAT_MODEL} (404). "
            "Check LLM_MODEL and CHAT_AGENT_MODEL.",
        ),
        (403, "forbidden", f"The API key isn't allowed to use {CHAT_MODEL} (403)."),
    ],
)
async def test_a_model_the_key_cannot_use_is_named(
    status_code: int, state: str, message: str
) -> None:
    """The message names the model that failed."""
    client = FakeAnthropic({CHAT_MODEL: _status_error(status_code)})

    status = await _checker(client).check()

    assert (status.state, status.message) == (state, message)


async def test_an_unreachable_api_is_checked_again_after_a_minute() -> None:
    """A network problem may pass, so a stale unreachable result is checked again on read."""
    clock = Clock()
    client = FakeAnthropic({INVESTIGATION_MODEL: anthropic.APIConnectionError(request=REQUEST)})
    checker = _checker(client, clock=clock)
    assert (await checker.check()).state == "unreachable"

    client.errors.clear()
    clock.now += timedelta(seconds=30)
    assert (await checker.current()).state == "unreachable"
    clock.now += timedelta(seconds=31)
    assert (await checker.current()).state == "ok"


async def test_a_rejected_key_is_not_checked_again() -> None:
    """The key comes from the environment: only a restart can change it."""
    clock = Clock()
    client = FakeAnthropic({INVESTIGATION_MODEL: _status_error(401)})
    checker = _checker(client, clock=clock)
    await checker.check()

    clock.now += timedelta(hours=1)
    await checker.current()

    assert client.retrieved == [INVESTIGATION_MODEL]


async def test_a_started_check_runs_in_the_background() -> None:
    """start() never blocks the caller; close() stops a check still running."""
    client = FakeAnthropic({})
    checker = _checker(client)

    checker.start()
    await checker.wait()
    await checker.aclose()

    assert checker.status.state == "ok"
