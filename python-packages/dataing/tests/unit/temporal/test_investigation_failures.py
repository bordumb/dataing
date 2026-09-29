"""A run that can't reach the model fails with the reason (docs/specs/0001_issue_chat.md §7.12).

Runs execute on Temporal's test server with fake activities. The fakes raise the
errors the real LLM activities raise: LLMRejected, which fails the run at once, and
LLMUnavailable, which the retry policy tries again before the run fails.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from fixtures.investigation_env import INVESTIGATION_TASK_QUEUE, FakeInvestigation
from fixtures.llm_errors import anthropic_error
from fixtures.record_investigation_histories import investigation_input
from temporalio.client import WorkflowFailureError, WorkflowHandle
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from dataing.agents.errors import classify_llm_error
from dataing.temporal.errors import llm_activity_error
from dataing.temporal.sandbox import workflow_runner
from dataing.temporal.workflows import (
    EvaluateHypothesisWorkflow,
    InvestigationWorkflow,
)

INVALID_KEY = (
    "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and "
    "restart the API and the worker."
)


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Return a time-skipping Temporal test environment."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


def rejected() -> ApplicationError:
    """Return the error an LLM activity raises when Anthropic rejects the key."""
    failure = classify_llm_error(anthropic_error(401))
    assert failure is not None
    return llm_activity_error(failure)


def overloaded() -> ApplicationError:
    """Return the error an LLM activity raises when Anthropic is overloaded."""
    failure = classify_llm_error(anthropic_error(529))
    assert failure is not None
    return llm_activity_error(failure)


async def run(
    env: WorkflowEnvironment,
    fake: FakeInvestigation,
    during: Callable[[WorkflowHandle[Any, Any]], Awaitable[None]] | None = None,
) -> Any:
    """Run an investigation and return its result, or the failure it ended with."""
    workflow_id = f"fail-{id(fake)}"
    async with Worker(
        env.client,
        workflow_runner=workflow_runner(),
        task_queue=INVESTIGATION_TASK_QUEUE,
        workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow],
        activities=fake.activities(),
    ):
        handle = await env.client.start_workflow(
            InvestigationWorkflow.run,
            investigation_input(workflow_id),
            id=workflow_id,
            task_queue=INVESTIGATION_TASK_QUEUE,
        )
        try:
            if during is not None:
                with env.auto_time_skipping_disabled():
                    await during(handle)
            return await handle.result()
        except WorkflowFailureError as e:
            return e
        finally:
            fake.released.set()


def failure_of(outcome: Any) -> dict[str, Any]:
    """Return the code, message and step a failed run ended with."""
    assert isinstance(outcome, WorkflowFailureError), f"the run didn't fail: {outcome}"
    cause = outcome.cause
    assert isinstance(cause, ApplicationError)
    assert cause.type == "InvestigationFailed"
    assert cause.non_retryable
    (details,) = cause.details
    assert details["message"] == cause.message
    return dict(details)


def published_failure(fake: FakeInvestigation) -> dict[str, Any]:
    """Return the failure the run published for the app and the issue thread."""
    (published,) = fake.inputs("publish_investigation_outcome")
    failure: dict[str, Any] = published["failure"]
    return failure


async def until(condition: Callable[[], bool]) -> None:
    """Wait (in real time) until a condition over the fake's calls holds."""
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition never held")


async def test_a_rejected_key_fails_the_run_with_what_to_fix(env: WorkflowEnvironment) -> None:
    """A 401 at hypothesis generation ends the run at once: no retry, no synthesis."""
    fake = FakeInvestigation(failures={"generate_hypotheses": [rejected()]})

    outcome = await run(env, fake)

    expected = {"code": "invalid_key", "message": INVALID_KEY, "step": "generate_hypotheses"}
    assert failure_of(outcome) == expected
    assert published_failure(fake) == expected
    assert len(fake.inputs("generate_hypotheses")) == 1
    assert "synthesize" not in fake.names()


async def test_an_overloaded_api_is_retried_before_the_run_moves_on(
    env: WorkflowEnvironment,
) -> None:
    """Overload is transient: the activity is retried and the run completes."""
    fake = FakeInvestigation(failures={"generate_hypotheses": [overloaded(), overloaded()]})

    result = await run(env, fake)

    assert result.status == "completed"
    assert len(fake.inputs("generate_hypotheses")) == 3


async def test_an_api_that_stays_overloaded_fails_the_run(env: WorkflowEnvironment) -> None:
    """After the retry policy's four attempts, the run fails and says to try later."""
    fake = FakeInvestigation(failures={"synthesize": [overloaded() for _ in range(4)]})

    outcome = await run(env, fake)

    failure = failure_of(outcome)
    assert (failure["code"], failure["step"]) == ("overloaded", "synthesize")
    assert failure["message"] == (
        "Anthropic is overloaded (529). It kept failing after 4 attempts; try again later."
    )
    assert len(fake.inputs("synthesize")) == 4


async def test_a_subagent_llm_error_stops_the_others_and_fails_the_run(
    env: WorkflowEnvironment,
) -> None:
    """The key is broken for every subagent, so one LLM error ends the whole run."""
    fake = FakeInvestigation(hold={"h3"}, failures={"interpret_evidence:h2": [rejected()]})

    outcome = await run(env, fake)

    failure = failure_of(outcome)
    assert (failure["code"], failure["step"]) == ("invalid_key", "interpret_evidence")
    assert "synthesize" not in fake.names()
    (published,) = fake.inputs("publish_investigation_outcome")
    statuses = {h["id"]: h["status"] for h in published["hypotheses"]}
    # h3 was still held, so the run ended without waiting for it
    assert (statuses["h2"], statuses["h3"]) == ("untested", "untested")


async def test_a_run_where_no_hypothesis_could_be_tested_fails(
    env: WorkflowEnvironment,
) -> None:
    """With every query failing there is nothing to conclude from, so the run fails."""
    fake = FakeInvestigation(
        query_errors={
            "h1": 'Query execution failed: relation "orders" does not exist',
            "h2": 'Query execution failed: relation "orders" does not exist',
            "h3": 'Query execution failed: relation "orders" does not exist',
        }
    )

    outcome = await run(env, fake)

    failure = failure_of(outcome)
    assert (failure["code"], failure["step"]) == ("no_evidence", "evaluate_hypotheses")
    assert failure["message"] == (
        "No hypothesis could be tested. The first error: "
        'Query execution failed: relation "orders" does not exist'
    )
    assert "synthesize" not in fake.names()


async def test_a_run_without_hypotheses_fails(env: WorkflowEnvironment) -> None:
    """A model that proposes nothing leaves nothing to test."""
    fake = FakeInvestigation(hypotheses=[])

    outcome = await run(env, fake)

    failure = failure_of(outcome)
    assert (failure["code"], failure["step"]) == ("no_hypotheses", "generate_hypotheses")
    assert failure["message"] == "The model proposed no hypotheses to test."


async def test_a_counter_analysis_failure_keeps_the_conclusion(
    env: WorkflowEnvironment,
) -> None:
    """Counter-analysis only checks a conclusion; losing it doesn't lose the conclusion."""
    fake = FakeInvestigation(confidence=0.5, failures={"counter_analyze": [rejected()]})

    result = await run(env, fake)

    assert result.status == "completed"
    assert result.synthesis["root_cause"] == "app_v2 writes COMPLETE instead of completed"
    (published,) = fake.inputs("publish_investigation_outcome")
    assert "failure" not in published
    assert published["counter_analysis"] == {
        "error": {"code": "invalid_key", "message": INVALID_KEY}
    }


async def test_stopping_before_any_evidence_still_concludes(env: WorkflowEnvironment) -> None:
    """Hypotheses a person stopped don't count as failures: the run concludes."""
    fake = FakeInvestigation(hold={"h1", "h2", "h3"})

    async def stop(handle: WorkflowHandle[Any, Any]) -> None:
        await until(lambda: len(fake.inputs("generate_query")) == 3)
        await handle.signal(
            InvestigationWorkflow.steer,
            {"steer_id": "s1", "kind": "stop_and_synthesize", "actor_user_id": "user-1"},
        )

    result = await run(env, fake, during=stop)

    assert result.status == "completed"
    assert len(fake.inputs("synthesize")) == 1
