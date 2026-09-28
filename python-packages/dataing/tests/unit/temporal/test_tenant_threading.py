"""tenant_id must reach every activity that touches a tenant's datasource."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dataing.temporal.activities import (
    ExecuteQueryInput,
    GatherContextInput,
    make_execute_query_activity,
    make_gather_context_activity,
)
from dataing.temporal.workflows.evaluate_hypothesis import (
    EvaluateHypothesisInput,
    EvaluateHypothesisResult,
    EvaluateHypothesisWorkflow,
)
from dataing.temporal.workflows.investigation import InvestigationInput, InvestigationWorkflow

TENANT_ID = "7d9f3c1e-0000-0000-0000-00000000000a"
DATASOURCE_ID = "7d9f3c1e-0000-0000-0000-00000000000b"
ALERT: dict[str, Any] = {
    "dataset_ids": ["analytics.orders"],
    "metric_spec": {
        "metric_type": "column",
        "expression": "user_id",
        "display_name": "NULL rate",
        "columns_referenced": ["user_id"],
    },
    "anomaly_type": "null_rate",
    "expected_value": 0.01,
    "actual_value": 0.15,
    "deviation_pct": 1400.0,
    "anomaly_date": "2026-01-10",
    "severity": "high",
}


class FakeWorkflowApi:
    """Stands in for ``temporalio.workflow`` inside workflow code under test."""

    def __init__(self, activity_results: dict[str, dict[str, Any]], child_result: Any) -> None:
        """Initialize with canned activity and child workflow results."""
        self.activity_inputs: dict[str, list[Any]] = defaultdict(list)
        self.child_inputs: list[Any] = []
        self.logger = MagicMock()
        self._activity_results = activity_results
        self._child_result = child_result

    async def execute_activity(self, name: str, arg: Any, **_: Any) -> dict[str, Any]:
        """Record the activity input and return its canned result."""
        self.activity_inputs[name].append(arg)
        return self._activity_results.get(name, {})

    async def start_child_workflow(self, _run: Any, arg: Any, **__: Any) -> asyncio.Future[Any]:
        """Record the child input and return an already-finished handle."""
        self.child_inputs.append(arg)
        handle: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        handle.set_result(self._child_result)
        return handle

    def info(self) -> Any:
        """Return minimal workflow info."""
        return MagicMock(workflow_id="investigation-1")

    def patched(self, _patch_id: str) -> bool:
        """Behave like a new run: every patch applies."""
        return True

    async def wait_condition(self, condition: Any, **_: Any) -> None:
        """Wait until a condition holds, yielding to the event loop between checks."""
        while not condition():
            await asyncio.sleep(0)


async def test_gather_context_resolves_adapter_for_input_tenant() -> None:
    """gather_context asks for the adapter of the investigation's tenant."""
    get_adapter = AsyncMock(side_effect=ValueError("not found"))
    gather_context = make_gather_context_activity(
        context_engine=MagicMock(), get_adapter=get_adapter
    )

    result = await gather_context(
        GatherContextInput(
            investigation_id="investigation-1",
            tenant_id=TENANT_ID,
            datasource_id=DATASOURCE_ID,
            alert=ALERT,
        )
    )

    get_adapter.assert_awaited_once_with(tenant_id=TENANT_ID, datasource_id=DATASOURCE_ID)
    assert result.error == "Failed to get adapter: not found"


async def test_execute_query_resolves_adapter_for_input_tenant() -> None:
    """execute_query asks for the adapter of the investigation's tenant."""
    get_adapter = AsyncMock(side_effect=ValueError("not found"))
    execute_query = make_execute_query_activity(get_adapter=get_adapter)

    result = await execute_query(
        ExecuteQueryInput(
            investigation_id="investigation-1",
            query="SELECT 1",
            hypothesis_id="h1",
            tenant_id=TENANT_ID,
            datasource_id=DATASOURCE_ID,
        )
    )

    get_adapter.assert_awaited_once_with(tenant_id=TENANT_ID, datasource_id=DATASOURCE_ID)
    assert result.error == "Query execution failed: not found"


async def test_investigation_workflow_threads_tenant_to_datasource_work() -> None:
    """The workflow hands its tenant to gather_context and every hypothesis child."""
    fake = FakeWorkflowApi(
        activity_results={
            "gather_context": {"schema_info": {"target_table": {"name": "orders"}}},
            "generate_hypotheses": {"hypotheses": [{"id": "h1"}, {"id": "h2"}]},
            "synthesize": {"root_cause": "ETL job failed", "confidence": 0.95},
        },
        child_result=EvaluateHypothesisResult(
            hypothesis_index=0, hypothesis_id="h1", evidence=[], queries_executed=1
        ),
    )

    with patch("dataing.temporal.workflows.investigation.workflow", fake):
        await InvestigationWorkflow().run(
            InvestigationInput(
                investigation_id="investigation-1",
                tenant_id=TENANT_ID,
                datasource_id=DATASOURCE_ID,
                alert_data=ALERT,
            )
        )

    (gather_input,) = fake.activity_inputs["gather_context"]
    assert (gather_input.tenant_id, gather_input.datasource_id) == (TENANT_ID, DATASOURCE_ID)
    assert [(c.tenant_id, c.datasource_id) for c in fake.child_inputs] == [
        (TENANT_ID, DATASOURCE_ID),
        (TENANT_ID, DATASOURCE_ID),
    ]


async def test_evaluate_hypothesis_workflow_threads_tenant_to_execute_query() -> None:
    """Each hypothesis query runs against the investigation's tenant."""
    fake = FakeWorkflowApi(
        activity_results={"generate_query": {"query": "SELECT 1"}},
        child_result=None,
    )

    with patch("dataing.temporal.workflows.evaluate_hypothesis.workflow", fake):
        await EvaluateHypothesisWorkflow().run(
            EvaluateHypothesisInput(
                investigation_id="investigation-1",
                hypothesis_index=0,
                hypothesis={"id": "h1"},
                schema_info={},
                alert_summary="null spike",
                tenant_id=TENANT_ID,
                datasource_id=DATASOURCE_ID,
            )
        )

    (execute_input,) = fake.activity_inputs["execute_query"]
    assert (execute_input.tenant_id, execute_input.datasource_id) == (TENANT_ID, DATASOURCE_ID)
