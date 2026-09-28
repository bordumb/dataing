"""People steer a running investigation (docs/specs/0001_issue_chat.md §7.8).

Runs execute on Temporal's test server with fake activities; activities named in
FakeInvestigation.hold stay open until released, so a steer can arrive while the
run is in a given phase.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fixtures.investigation_env import INVESTIGATION_TASK_QUEUE, FakeInvestigation
from fixtures.record_investigation_histories import investigation_input
from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from dataing.temporal.workflows import (
    EvaluateHypothesisWorkflow,
    InvestigationInput,
    InvestigationWorkflow,
)


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    """Return a time-skipping Temporal test environment."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


def steer(steer_id: str, kind: str, text: str = "", hypothesis_id: str | None = None) -> dict:
    """Return a steer signal payload as the API sends it."""
    return {
        "steer_id": steer_id,
        "kind": kind,
        "text": text,
        "hypothesis_id": hypothesis_id,
        "actor_user_id": "user-1",
    }


async def until(condition: Callable[[], bool]) -> None:
    """Wait (in real time) until a condition over the fake's calls holds."""
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition never held")


async def until_statuses(handle: WorkflowHandle[Any, Any], expected: dict[str, str]) -> None:
    """Wait until the run reports exactly these hypothesis statuses."""
    for _ in range(500):
        status = await handle.query(InvestigationWorkflow.get_status)
        if {h["id"]: h["status"] for h in status.hypotheses} == expected:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"status never showed {expected}")


def outcomes(fake: FakeInvestigation) -> dict[str, dict[str, Any]]:
    """Return the recorded outcome of each steer, by steer id."""
    return {o["steer_id"]: o for o in fake.inputs("record_steer_outcome")}


def queried_ids(fake: FakeInvestigation) -> list[str]:
    """Return the hypotheses subagents generated queries for."""
    return [p["hypothesis"]["id"] for p in fake.inputs("generate_query")]


async def run_steered(
    env: WorkflowEnvironment,
    fake: FakeInvestigation,
    steer_run: Callable[[WorkflowHandle[Any, Any]], Any],
    run_input: InvestigationInput | None = None,
) -> Any:
    """Run an investigation, steer it while held activities wait, and return its result."""
    workflow_id = f"steer-{len(fake.calls)}-{id(fake)}"
    async with Worker(
        env.client,
        task_queue=INVESTIGATION_TASK_QUEUE,
        workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow],
        activities=fake.activities(),
    ):
        with env.auto_time_skipping_disabled():
            handle = await env.client.start_workflow(
                InvestigationWorkflow.run,
                run_input or investigation_input(workflow_id),
                id=workflow_id,
                task_queue=INVESTIGATION_TASK_QUEUE,
            )
            try:
                await steer_run(handle)
                return await handle.result()
            finally:
                fake.released.set()


async def test_rule_out_cancels_that_subagent_only(env: WorkflowEnvironment) -> None:
    """Ruling out a running hypothesis stops its subagent; the run concludes without it."""
    fake = FakeInvestigation(hold={"h3"})

    async def steer_run(handle: WorkflowHandle[Any, Any]) -> None:
        await until_statuses(handle, {"h1": "supported", "h2": "refuted", "h3": "running"})
        await handle.signal(
            InvestigationWorkflow.steer,
            steer("s1", "rule_out", "Events land within minutes", "h3"),
        )

    result = await run_steered(env, fake, steer_run)

    assert result.status == "completed"
    assert "h3" not in [p["hypothesis"]["id"] for p in fake.inputs("interpret_evidence")]
    (synthesis,) = fake.inputs("synthesize")
    assert synthesis["ruled_out_hypotheses"] == [
        {
            "hypothesis_id": "h3",
            "title": "late-arriving events",
            "reason": "Events land within minutes",
        }
    ]
    assert outcomes(fake)["s1"]["status"] == "applied"
    assert outcomes(fake)["s1"]["outcome"] == "Cancelled h3 'late-arriving events'"
    (published,) = fake.inputs("publish_investigation_outcome")
    assert {h["id"]: h["status"] for h in published["hypotheses"]}["h3"] == "ruled_out"


async def test_add_hypothesis_starts_a_subagent_up_to_the_cap(env: WorkflowEnvironment) -> None:
    """A person's hypothesis is tested too; past max_hypotheses + 3 more are refused."""
    fake = FakeInvestigation(hold={"h1"})
    run_input = dataclasses.replace(investigation_input("steer-add"), max_hypotheses=1)

    async def steer_run(handle: WorkflowHandle[Any, Any]) -> None:
        await until(lambda: "h1" in queried_ids(fake))
        await handle.signal(
            InvestigationWorkflow.steer, steer("s1", "add_hypothesis", "timezone bug in loader")
        )
        await handle.signal(
            InvestigationWorkflow.steer, steer("s2", "add_hypothesis", "duplicate events")
        )
        await until(lambda: len(fake.inputs("record_steer_outcome")) == 2)
        fake.released.set()

    result = await run_steered(env, fake, steer_run, run_input)

    (formulated,) = fake.inputs("formulate_hypothesis")
    assert (formulated["hypothesis_id"], formulated["text"]) == ("h4", "timezone bug in loader")
    assert "h4" in queried_ids(fake)
    assert [h["id"] for h in result.hypotheses] == ["h1", "h2", "h3", "h4"]
    assert outcomes(fake)["s1"]["status"] == "applied"
    assert outcomes(fake)["s1"]["outcome"] == "Started h4 'timezone bug in loader'"
    assert outcomes(fake)["s2"]["status"] == "rejected"
    assert outcomes(fake)["s2"]["outcome"] == "This run already has its limit of 4 hypotheses"


async def test_stop_and_synthesize_concludes_with_the_rest_untested(
    env: WorkflowEnvironment,
) -> None:
    """Stopping cancels the running subagents; their hypotheses reach synthesis untested."""
    fake = FakeInvestigation(hold={"h2", "h3"})

    async def steer_run(handle: WorkflowHandle[Any, Any]) -> None:
        # h1 must have finished, or stopping cancels it too and it also goes untested
        await until_statuses(handle, {"h1": "supported", "h2": "running", "h3": "running"})
        await handle.signal(InvestigationWorkflow.steer, steer("s1", "stop_and_synthesize"))

    result = await run_steered(env, fake, steer_run)

    assert result.status == "completed"
    (synthesis,) = fake.inputs("synthesize")
    untested = {u["hypothesis_id"]: u["error"] for u in synthesis["untested_hypotheses"]}
    assert set(untested) == {"h2", "h3"}
    assert all("stopped" in error for error in untested.values())
    assert outcomes(fake)["s1"]["status"] == "applied"


async def test_steers_during_synthesis_trigger_exactly_one_resynthesis(
    env: WorkflowEnvironment,
) -> None:
    """Context sent while synthesis runs is batched into a single re-synthesis."""
    fake = FakeInvestigation(hold={"synthesize"})

    async def steer_run(handle: WorkflowHandle[Any, Any]) -> None:
        await until(lambda: "synthesize" in fake.names())
        await handle.signal(
            InvestigationWorkflow.steer, steer("s1", "add_context", "app_v2 shipped at 09:00")
        )
        await handle.signal(
            InvestigationWorkflow.steer, steer("s2", "add_context", "only EU orders dropped")
        )
        fake.released.set()

    await run_steered(env, fake, steer_run)

    first, second = fake.inputs("synthesize")
    assert "app_v2 shipped" not in str(first["alert"])
    brief = second["alert"]["metadata"]["brief"]
    assert "Context from the team: app_v2 shipped at 09:00" in brief
    assert "Context from the team: only EU orders dropped" in brief
    assert {o["outcome"] for o in outcomes(fake).values()} == {"Re-synthesizing with it"}


async def test_steer_after_synthesis_is_rejected(env: WorkflowEnvironment) -> None:
    """Once the conclusion is final, a steer points to Continue investigating."""
    fake = FakeInvestigation(hold={"counter_analyze"}, confidence=0.5)

    async def steer_run(handle: WorkflowHandle[Any, Any]) -> None:
        await until(lambda: "counter_analyze" in fake.names())
        await handle.signal(InvestigationWorkflow.steer, steer("s1", "add_context", "too late"))
        fake.released.set()

    await run_steered(env, fake, steer_run)

    assert len(fake.inputs("synthesize")) == 1
    assert outcomes(fake)["s1"]["status"] == "rejected"
    assert outcomes(fake)["s1"]["phase"] == "finished"
    assert outcomes(fake)["s1"]["outcome"] == "Finished: use Continue investigating"


async def test_steers_before_hypotheses_shape_their_generation(env: WorkflowEnvironment) -> None:
    """Early context and exclusions reach generation; an early hypothesis is tested too."""
    fake = FakeInvestigation(hold={"gather_context"})

    async def steer_run(handle: WorkflowHandle[Any, Any]) -> None:
        await until(lambda: "gather_context" in fake.names())
        for payload in (
            steer("s1", "add_context", "app_v2 shipped at 09:00"),
            steer("s2", "rule_out", "late-arriving events"),
            steer("s3", "add_hypothesis", "timezone bug in loader"),
            steer("s4", "stop_and_synthesize"),
        ):
            await handle.signal(InvestigationWorkflow.steer, payload)
        fake.released.set()

    await run_steered(env, fake, steer_run)

    (generation,) = fake.inputs("generate_hypotheses")
    brief = generation["alert"]["metadata"]["brief"]
    assert "Context from the team: app_v2 shipped at 09:00" in brief
    assert "Ruled out by a person: late-arriving events" in brief
    (formulated,) = fake.inputs("formulate_hypothesis")
    assert formulated["hypothesis_id"] == "h4"
    assert "h4" in queried_ids(fake)
    recorded = outcomes(fake)
    assert [recorded[s]["status"] for s in ("s1", "s2", "s3", "s4")] == [
        "applied",
        "applied",
        "applied",
        "rejected",
    ]
    assert recorded["s3"]["phase"] == "evaluation"
