"""IssueThreadWorkflow runs agent turns for one thread, one at a time, in order.

Runs on Temporal's time-skipping test server with fake activities, so signals,
timers and continue-as-new behave as in production.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from dataing.temporal.workflows.issue_thread import (
    IssueThreadInput,
    IssueThreadWorkflow,
    thread_workflow_id,
)

TASK_QUEUE = "issue-thread-tests"


class Turns:
    """Records the turns the fake activity ran; can block or fail a turn."""

    def __init__(self) -> None:
        """Initialize empty."""
        self.ran: list[str] = []
        self.failed: list[str] = []
        self.release = asyncio.Event()
        self.block: set[str] = set()
        self.fail: set[str] = set()

    def activities(self) -> list[Any]:
        """Return fake run_agent_turn and mark_turn_failed activities."""

        @activity.defn(name="run_agent_turn")
        async def run_agent_turn(request: dict[str, Any]) -> dict[str, Any]:
            message_id = request["message_id"]
            if message_id in self.fail:
                raise RuntimeError("model unavailable")
            if message_id in self.block:
                while not self.release.is_set():
                    activity.heartbeat()
                    await asyncio.sleep(0.05)
            self.ran.append(message_id)
            return {"status": "complete"}

        @activity.defn(name="run_brief_draft")
        async def run_brief_draft(request: dict[str, Any]) -> dict[str, Any]:
            self.ran.append(f"brief:{request['message_id']}")
            return {"status": "complete"}

        @activity.defn(name="mark_turn_failed")
        async def mark_turn_failed(request: dict[str, Any]) -> None:
            self.failed.append(request["message_id"])

        return [run_agent_turn, run_brief_draft, mark_turn_failed]


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Return a time-skipping Temporal test environment."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


def _request(message_id: str, thread_id: str, kind: str = "answer") -> dict[str, Any]:
    return {
        "message_id": message_id,
        "kind": kind,
        "thread_id": thread_id,
        "tenant_id": str(uuid.uuid4()),
        "issue_id": str(uuid.uuid4()),
        "requested_by": str(uuid.uuid4()),
    }


async def _enqueue(
    client: Client, thread_id: str, message_id: str, input: IssueThreadInput | None = None
) -> Any:
    return await client.start_workflow(
        IssueThreadWorkflow.run,
        input or IssueThreadInput(thread_id=thread_id),
        id=thread_workflow_id(thread_id),
        task_queue=TASK_QUEUE,
        start_signal="enqueue",
        start_signal_args=[_request(message_id, thread_id)],
    )


async def _wait_for(predicate: Any, timeout: float = 10.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.05)


async def test_turns_run_in_order_and_duplicates_are_ignored(env: WorkflowEnvironment) -> None:
    """Requests run first-in-first-out; a re-sent request runs once."""
    turns = Turns()
    thread_id = str(uuid.uuid4())
    turns.block.add("a")
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueThreadWorkflow],
        activities=turns.activities(),
    ):
        with env.auto_time_skipping_disabled():
            await _enqueue(env.client, thread_id, "a")
            await _enqueue(env.client, thread_id, "b")
            await _enqueue(env.client, thread_id, "b")
            await _enqueue(env.client, thread_id, "c")
            turns.release.set()
            await _wait_for(lambda: len(turns.ran) == 3)

    assert turns.ran == ["a", "b", "c"]


async def test_cancelled_queued_request_is_skipped(env: WorkflowEnvironment) -> None:
    """Cancelling a queued request removes it before it runs."""
    turns = Turns()
    thread_id = str(uuid.uuid4())
    turns.block.add("a")
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueThreadWorkflow],
        activities=turns.activities(),
    ):
        with env.auto_time_skipping_disabled():
            handle = await _enqueue(env.client, thread_id, "a")
            await _enqueue(env.client, thread_id, "b")
            await _enqueue(env.client, thread_id, "c")
            await handle.signal(IssueThreadWorkflow.cancel_request, "b")
            turns.release.set()
            await _wait_for(lambda: len(turns.ran) == 2)

    assert turns.ran == ["a", "c"]


async def test_workflow_ends_after_idling(env: WorkflowEnvironment) -> None:
    """With nothing queued for the idle timeout, the workflow completes."""
    turns = Turns()
    thread_id = str(uuid.uuid4())
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueThreadWorkflow],
        activities=turns.activities(),
    ):
        handle = await _enqueue(env.client, thread_id, "a")
        await handle.result()

    assert turns.ran == ["a"]
    description = await handle.describe()
    assert description.status == WorkflowExecutionStatus.COMPLETED


async def test_continue_as_new_carries_pending_requests(env: WorkflowEnvironment) -> None:
    """After the turn budget, the workflow continues as new with the queue intact."""
    turns = Turns()
    thread_id = str(uuid.uuid4())
    turns.block.add("a")
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueThreadWorkflow],
        activities=turns.activities(),
    ):
        with env.auto_time_skipping_disabled():
            first = await _enqueue(
                env.client,
                thread_id,
                "a",
                IssueThreadInput(thread_id=thread_id, turns_per_run=1),
            )
            await _enqueue(env.client, thread_id, "b")
            await _enqueue(env.client, thread_id, "c")
            turns.release.set()
            await _wait_for(lambda: len(turns.ran) == 3)

        first_run = await env.client.get_workflow_handle(
            first.id, run_id=first.result_run_id
        ).describe()
    assert turns.ran == ["a", "b", "c"]
    assert first_run.status == WorkflowExecutionStatus.CONTINUED_AS_NEW


async def test_failed_turn_is_marked_and_the_queue_moves_on(env: WorkflowEnvironment) -> None:
    """When a turn keeps failing, its reply is marked failed and the next turn runs."""
    turns = Turns()
    thread_id = str(uuid.uuid4())
    turns.fail.add("a")
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueThreadWorkflow],
        activities=turns.activities(),
    ):
        with env.auto_time_skipping_disabled():
            await _enqueue(env.client, thread_id, "a")
            await _enqueue(env.client, thread_id, "b")
            await _wait_for(lambda: turns.ran == ["b"], timeout=30)

    assert turns.failed == ["a"]


async def test_brief_requests_run_the_draft_activity(env: WorkflowEnvironment) -> None:
    """draft_brief requests go to run_brief_draft, in queue order with answers."""
    turns = Turns()
    thread_id = str(uuid.uuid4())
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[IssueThreadWorkflow],
        activities=turns.activities(),
    ):
        with env.auto_time_skipping_disabled():
            await _enqueue(env.client, thread_id, "a")
            await env.client.start_workflow(
                IssueThreadWorkflow.run,
                IssueThreadInput(thread_id=thread_id),
                id=thread_workflow_id(thread_id),
                task_queue=TASK_QUEUE,
                start_signal="enqueue",
                start_signal_args=[_request("b", thread_id, kind="draft_brief")],
            )
            await _wait_for(lambda: len(turns.ran) == 2)

    assert turns.ran == ["a", "brief:b"]


async def test_workflow_id_is_per_thread() -> None:
    """Every thread has its own workflow."""
    assert thread_workflow_id("t1") == "issue-thread-t1"
    assert thread_workflow_id("t1") != thread_workflow_id("t2")
