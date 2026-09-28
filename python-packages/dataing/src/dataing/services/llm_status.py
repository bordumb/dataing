"""Whether the Anthropic key and models work (docs/specs/0001_issue_chat.md §7.12).

At startup the API asks Anthropic for each configured model (GET /v1/models/{id},
which costs no tokens). Every page shows a banner while the answer is a problem, so
a rejected key is visible before anyone starts a run. The check runs in the
background with a short timeout and no retries, so a slow network never delays
startup.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import anthropic
import structlog

from dataing.agents.errors import classify_llm_error

logger = structlog.get_logger()

CHECK_TIMEOUT_SECONDS = 10.0
# Problems that may pass on their own; the others need a new key or model and a restart
TRANSIENT_STATES = frozenset({"unreachable", "rate_limited", "overloaded", "server_error"})
RECHECK_AFTER = timedelta(seconds=60)


@dataclass
class LLMStatus:
    """The result of the last check."""

    state: str
    message: str
    models: list[str]
    checked_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the status as the API returns it."""
        return {
            "state": self.state,
            "message": self.message,
            "models": self.models,
            "checked_at": self.checked_at,
        }


def _anthropic_client(api_key: str) -> Any:
    return anthropic.AsyncAnthropic(api_key=api_key, max_retries=0, timeout=CHECK_TIMEOUT_SECONDS)


class LLMStatusChecker:
    """Checks, once at startup, that the key works for every configured model."""

    def __init__(
        self,
        api_key: str,
        models: Sequence[str],
        client_factory: Callable[[str], Any] = _anthropic_client,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize with the key and the models the API and worker use."""
        self._api_key = api_key
        self._models = list(dict.fromkeys(model for model in models if model))
        self._client_factory = client_factory
        self._clock = clock
        self._task: asyncio.Task[LLMStatus] | None = None
        self._status = LLMStatus(
            state="checking",
            message="Checking the Anthropic API key…",
            models=self._models,
        )

    @property
    def status(self) -> LLMStatus:
        """Return the last result, without checking again."""
        return self._status

    def start(self) -> None:
        """Check in the background."""
        self._task = asyncio.create_task(self.check())

    async def wait(self) -> LLMStatus:
        """Wait for a started check to finish and return its result."""
        if self._task is not None:
            with contextlib.suppress(Exception):
                await self._task
        return self._status

    async def aclose(self) -> None:
        """Stop a check that is still running."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    async def current(self) -> LLMStatus:
        """Return the status, checking again when a transient problem has gone stale."""
        checked_at = self._status.checked_at
        stale = checked_at is None or self._clock() - checked_at >= RECHECK_AFTER
        running = self._task is not None and not self._task.done()
        if self._status.state in TRANSIENT_STATES and stale and not running:
            return await self.check()
        return self._status

    async def check(self) -> LLMStatus:
        """Ask Anthropic for every model; stop at the first problem."""
        if not self._api_key:
            return self._set(
                "missing_key",
                "ANTHROPIC_API_KEY isn't set. Set it and restart the API and the worker.",
            )
        client = self._client_factory(self._api_key)
        for model in self._models:
            try:
                await client.models.retrieve(model)
            except Exception as e:
                failure = classify_llm_error(e, model=model)
                if failure is None:
                    return self._set("unreachable", f"Couldn't check the Anthropic API key: {e}")
                logger.warning("llm_check_failed", state=failure.code, model=model)
                return self._set(failure.code, failure.message)
        return self._set("ok", f"Anthropic accepted the API key for {', '.join(self._models)}.")

    def _set(self, state: str, message: str) -> LLMStatus:
        self._status = LLMStatus(
            state=state, message=message, models=self._models, checked_at=self._clock()
        )
        return self._status
