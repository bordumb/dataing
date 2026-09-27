"""In-process Temporal harness for investigation workflow tests.

Workflows and activities run their real code; only Temporal's dispatch is replaced.
Every argument and result is round-tripped through Temporal's default data
converter, so workflows see the same payload shapes a real worker delivers.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import typing
from collections.abc import Awaitable, Callable, Collection
from types import SimpleNamespace
from typing import Any

import pytest
from temporalio import workflow
from temporalio.converter import DataConverter
from temporalio.exceptions import ChildWorkflowError, TerminatedError

from dataing.adapters.datasource.types import AdapterCapabilities, QueryLanguage, QueryResult


def sql_for(hypothesis_id: str) -> str:
    """Return the SQL FakeAgent generates to test a hypothesis.

    It passes execute_query's validation: a single SELECT with a LIMIT.
    """
    return f"SELECT order_id, amount FROM orders LIMIT 100 /* {hypothesis_id} */"


class FakeDatasource:
    """Datasource adapter that answers each query with a canned result or error.

    It declares the postgres dialect, which execute_query validates queries in.
    """

    capabilities = AdapterCapabilities(
        supports_sql=True, query_language=QueryLanguage.SQL, sql_dialect="postgres"
    )

    def __init__(self, answers: dict[str, QueryResult | Exception]) -> None:
        self._answers = answers

    async def execute_query(self, sql: str) -> QueryResult:
        answer = self._answers[sql]
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeAgent:
    """Stands in for TemporalAgentAdapter at the LLM boundary and records calls.

    `interpretation_errors` maps a hypothesis id to the error its interpretation
    raises. Every interpretation is recorded, whether it succeeds or fails.
    """

    def __init__(self, interpretation_errors: dict[str, Exception] | None = None) -> None:
        self.interpreted: list[dict[str, Any]] = []
        self.synthesized: list[dict[str, Any]] = []
        self._interpretation_errors = interpretation_errors or {}

    async def generate_query(self, *, hypothesis: dict[str, Any], **_: Any) -> str:
        return sql_for(hypothesis["id"])

    async def interpret_evidence(
        self, *, hypothesis: dict[str, Any], query_result: dict[str, Any], alert_summary: str
    ) -> dict[str, Any]:
        self.interpreted.append(query_result)
        error = self._interpretation_errors.get(hypothesis["id"])
        if error is not None:
            raise error
        return {
            "supports_hypothesis": True,
            "confidence": 0.9,
            "interpretation": "NULL amounts found",
            "key_findings": ["1 order with NULL amount"],
        }

    async def synthesize_findings_for_temporal(self, **kwargs: Any) -> dict[str, Any]:
        self.synthesized.append(kwargs)
        return {
            "root_cause": "Upstream ETL job wrote NULL amounts after 03:14 UTC",
            "confidence": 0.9,
            "recommendations": ["Re-run the orders ETL job"],
            "supporting_evidence": ["1 order with NULL amount"],
        }


class InProcessTemporal:
    """Replaces Temporal's workflow-side dispatch with in-process execution.

    `terminated` names child workflow IDs to fail the way Temporal reports a child
    terminated from outside. Any other exception raised inside a child is recorded
    in `escaped`: Temporal would retry the activity or workflow task instead of
    failing the child, so tests must assert that nothing escaped.
    """

    def __init__(
        self, *activities: Callable[[Any], Awaitable[Any]], terminated: Collection[str] = ()
    ) -> None:
        # Later activities override earlier ones with the same name.
        self._activities = {fn.__name__: fn for fn in activities}
        self._terminated = set(terminated)
        self._converter = DataConverter.default
        self.escaped: list[BaseException] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Route the workflow APIs used by investigation workflows to this harness."""
        monkeypatch.setattr(workflow, "execute_activity", self.execute_activity)
        monkeypatch.setattr(workflow, "start_child_workflow", self.start_child_workflow)
        monkeypatch.setattr(workflow, "info", lambda: SimpleNamespace(workflow_id="wf-1"))
        monkeypatch.setattr(workflow, "logger", logging.getLogger("workflow"))

    async def execute_activity(self, activity: str, arg: Any, **options: Any) -> Any:
        # Typed decoding (result_type=...) of these dataclasses fails inside Temporal's
        # workflow sandbox, which this harness can't reproduce: refuse it, don't pass it.
        assert options.get("result_type") is None, "result_type needs a sandboxed test"
        result = await self._activities[activity](await self._round_trip(arg, type(arg)))
        return await self._round_trip(result, None)

    async def start_child_workflow(
        self, run: Callable[..., Awaitable[Any]], arg: Any, *, id: str, **_: Any
    ) -> asyncio.Future[Any]:
        if id in self._terminated:
            terminated: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
            terminated.set_exception(_terminated_child_error(id))
            return terminated

        owner = getattr(sys.modules[run.__module__], run.__qualname__.rsplit(".", 1)[0])
        result_type = typing.get_type_hints(run)["return"]

        async def run_child() -> Any:
            try:
                result = await run(owner(), await self._round_trip(arg, type(arg)))
            except Exception as e:
                self.escaped.append(e)
                raise
            return await self._round_trip(result, result_type)

        return asyncio.ensure_future(run_child())

    async def _round_trip(self, value: Any, type_hint: type | None) -> Any:
        payloads = await self._converter.encode([value])
        (decoded,) = await self._converter.decode(payloads, [type_hint] if type_hint else None)
        return decoded


def _terminated_child_error(workflow_id: str) -> ChildWorkflowError:
    """Build the error a parent sees when Temporal terminates its child."""
    error = ChildWorkflowError(
        "Child Workflow execution terminated",
        namespace="default",
        workflow_id=workflow_id,
        run_id="run-1",
        workflow_type="EvaluateHypothesisWorkflow",
        initiated_event_id=1,
        started_event_id=2,
        retry_state=None,
    )
    error.__cause__ = TerminatedError("Terminated")
    return error
