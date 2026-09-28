"""A finished investigation publishes its outcome (spec 0001 §7.7, §7.10)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fixtures.investigation_env import INVESTIGATION_TASK_QUEUE, FakeInvestigation
from fixtures.record_investigation_histories import investigation_input
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from dataing.temporal.workflows import EvaluateHypothesisWorkflow, InvestigationWorkflow


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Return a time-skipping Temporal test environment."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


async def test_completed_run_publishes_its_outcome_once(env: WorkflowEnvironment) -> None:
    """The outcome carries the synthesis and a status for every hypothesis."""
    fake = FakeInvestigation()
    async with Worker(
        env.client,
        task_queue=INVESTIGATION_TASK_QUEUE,
        workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow],
        activities=fake.activities(),
    ):
        handle = await env.client.start_workflow(
            InvestigationWorkflow.run,
            investigation_input("inv-outcome"),
            id="inv-outcome",
            task_queue=INVESTIGATION_TASK_QUEUE,
        )
        await handle.result()

    (published,) = fake.inputs("publish_investigation_outcome")
    assert published["investigation_id"] == "inv-outcome"
    assert published["issue_id"] == investigation_input("x").alert_data["issue_id"]
    assert published["synthesis"]["root_cause"].startswith("app_v2 writes")
    statuses = {h["id"]: h["status"] for h in published["hypotheses"]}
    assert statuses == {"h1": "supported", "h2": "refuted", "h3": "refuted"}


async def test_cancelled_run_publishes_nothing(env: WorkflowEnvironment) -> None:
    """A cancelled run has no outcome to publish."""
    fake = FakeInvestigation(hold={"h1"})
    async with Worker(
        env.client,
        task_queue=INVESTIGATION_TASK_QUEUE,
        workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow],
        activities=fake.activities(),
    ):
        with env.auto_time_skipping_disabled():
            handle = await env.client.start_workflow(
                InvestigationWorkflow.run,
                investigation_input("inv-cancel"),
                id="inv-cancel",
                task_queue=INVESTIGATION_TASK_QUEUE,
            )
            while "generate_query" not in fake.names():
                await env.sleep(0.05)
            await handle.signal(InvestigationWorkflow.cancel_investigation)
            fake.released.set()
            await handle.result()

    assert fake.inputs("publish_investigation_outcome") == []
