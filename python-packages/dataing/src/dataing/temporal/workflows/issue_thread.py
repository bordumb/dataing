"""Workflow that answers agent requests in one issue thread, one at a time.

docs/specs/0001_issue_chat.md §7.4. One workflow per thread (id
``issue-thread-<thread_id>``) is started or signalled with signal-with-start for
every request, so two people asking at once are answered in order.

- ``enqueue`` adds a request (ignored if its message was already queued or run).
- ``cancel_request`` drops a queued request, or cancels the running turn.
- The workflow completes after ``idle_minutes`` with nothing queued; the next
  request starts it again.
- After ``turns_per_run`` turns it continues as new, carrying the queue.

Activity results are read as plain dicts: typed results fail in the sandbox.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

TURN_TIMEOUT = timedelta(minutes=5)
TURN_HEARTBEAT_TIMEOUT = timedelta(seconds=30)
TURN_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=5), maximum_attempts=2
)


def thread_workflow_id(thread_id: str) -> str:
    """Return the workflow id for a thread."""
    return f"issue-thread-{thread_id}"


@dataclass
class IssueThreadInput:
    """Workflow input; continue-as-new passes the undrained queue along."""

    thread_id: str
    pending: list[dict[str, Any]] = field(default_factory=list)
    seen: list[str] = field(default_factory=list)
    turns_per_run: int = 50
    idle_minutes: int = 30


@workflow.defn
class IssueThreadWorkflow:
    """Runs agent turns for one thread in the order they were requested."""

    def __init__(self) -> None:
        """Initialize workflow state."""
        self._queue: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        self._current: str | None = None
        self._current_turn: Any = None

    @workflow.signal
    def enqueue(self, request: dict[str, Any]) -> None:
        """Queue a request. A message already queued or answered is ignored."""
        message_id = str(request["message_id"])
        if message_id in self._seen:
            return
        self._seen.add(message_id)
        self._queue.append(request)

    @workflow.signal
    def cancel_request(self, message_id: str) -> None:
        """Drop a queued request, or cancel it if it is the one running."""
        self._queue = [r for r in self._queue if str(r["message_id"]) != message_id]
        if self._current == message_id and self._current_turn is not None:
            self._current_turn.cancel()

    @workflow.query
    def queue_state(self) -> dict[str, Any]:
        """Return the running request and the queued ones, in order."""
        return {"current": self._current, "queued": [str(r["message_id"]) for r in self._queue]}

    @workflow.run
    async def run(self, input: IssueThreadInput) -> None:
        """Answer requests until the thread goes quiet."""
        for request in input.pending:
            self._seen.add(str(request["message_id"]))
        self._queue = list(input.pending) + self._queue
        self._seen.update(input.seen)
        turns = 0

        while True:
            try:
                await workflow.wait_condition(
                    lambda: bool(self._queue), timeout=timedelta(minutes=input.idle_minutes)
                )
            except TimeoutError:
                await workflow.wait_condition(workflow.all_handlers_finished)
                if not self._queue:
                    return

            request = self._queue.pop(0)
            await self._run_turn(request)
            turns += 1

            if turns >= input.turns_per_run or workflow.info().is_continue_as_new_suggested():
                await workflow.wait_condition(workflow.all_handlers_finished)
                workflow.continue_as_new(
                    IssueThreadInput(
                        thread_id=input.thread_id,
                        pending=self._queue,
                        seen=sorted(self._seen)[-500:],
                        turns_per_run=input.turns_per_run,
                        idle_minutes=input.idle_minutes,
                    )
                )

    async def _run_turn(self, request: dict[str, Any]) -> None:
        """Run one turn; mark its reply failed if every attempt fails."""
        self._current = str(request["message_id"])
        self._current_turn = workflow.start_activity(
            "run_agent_turn",
            request,
            start_to_close_timeout=TURN_TIMEOUT,
            heartbeat_timeout=TURN_HEARTBEAT_TIMEOUT,
            retry_policy=TURN_RETRY,
        )
        try:
            await self._current_turn
        except asyncio.CancelledError:
            # Cancelled by cancel_request; the activity marks its reply cancelled
            workflow.logger.info(f"Turn cancelled: {self._current}")
        except ActivityError as e:
            workflow.logger.warning(f"Turn failed: {self._current}: {e}")
            await workflow.execute_activity(
                "mark_turn_failed",
                {**request, "error": str(e.cause or e)},
                start_to_close_timeout=timedelta(seconds=30),
            )
        finally:
            self._current = None
            self._current_turn = None
