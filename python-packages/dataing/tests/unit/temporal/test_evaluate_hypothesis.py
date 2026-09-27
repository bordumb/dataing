"""Unit tests for EvaluateHypothesisWorkflow query and interpretation error propagation.

These run the real chain (AdapterDatabase -> execute_query activity -> workflow ->
interpret_evidence activity) in-process via fixtures.temporal.
"""

from __future__ import annotations

import pytest
from fixtures.temporal import FakeAgent, FakeDatasource, InProcessTemporal, sql_for

from dataing.adapters.datasource.errors import QuerySyntaxError
from dataing.adapters.datasource.types import QueryResult
from dataing.entrypoints.temporal_worker import AdapterDatabase
from dataing.temporal.activities import (
    make_execute_query_activity,
    make_generate_query_activity,
    make_interpret_evidence_activity,
)
from dataing.temporal.workflows.evaluate_hypothesis import (
    EvaluateHypothesisInput,
    EvaluateHypothesisResult,
    EvaluateHypothesisWorkflow,
)

SQL = sql_for("h-1")


async def _evaluate(
    monkeypatch: pytest.MonkeyPatch, datasource: FakeDatasource, agent: FakeAgent
) -> EvaluateHypothesisResult:
    async def get_adapter(datasource_id: str) -> FakeDatasource:
        return datasource

    InProcessTemporal(
        make_generate_query_activity(adapter=agent),
        make_execute_query_activity(database=AdapterDatabase(get_adapter)),
        make_interpret_evidence_activity(adapter=agent),
    ).install(monkeypatch)

    return await EvaluateHypothesisWorkflow().run(
        EvaluateHypothesisInput(
            investigation_id="inv-1",
            hypothesis_index=0,
            hypothesis={"id": "h-1", "title": "Upstream ETL wrote NULL amounts"},
            schema_info={},
            alert_summary="orders.amount null rate spiked to 40%",
            datasource_id="ds-1",
        )
    )


async def test_failed_query_is_reported_as_failure_not_interpreted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A query error fails the evaluation instead of reaching interpretation as 0 rows."""
    datasource = FakeDatasource({SQL: QuerySyntaxError('column "amount" does not exist')})
    agent = FakeAgent()

    result = await _evaluate(monkeypatch, datasource, agent)

    assert agent.interpreted == []
    assert result.error == 'Query execution failed: column "amount" does not exist'
    assert result.evidence == []
    assert result.queries_executed == 1


async def test_query_result_metadata_reaches_interpretation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Truncation and timing reported by the datasource are passed to interpretation."""
    datasource = FakeDatasource(
        {
            SQL: QueryResult(
                columns=[{"name": "order_id", "data_type": "integer"}],
                rows=[{"order_id": 7, "amount": None}],
                row_count=1,
                truncated=True,
                execution_time_ms=42,
            )
        }
    )
    agent = FakeAgent()

    result = await _evaluate(monkeypatch, datasource, agent)

    assert agent.interpreted == [
        {
            "query": SQL,
            "columns": [{"name": "order_id", "data_type": "integer"}],
            "rows": [{"order_id": 7, "amount": None}],
            "row_count": 1,
            "truncated": True,
            "execution_time_ms": 42,
        }
    ]
    assert result.error is None
    assert result.evidence[0]["row_count"] == 1
    assert result.evidence[0]["supports_hypothesis"] is True


async def test_failed_interpretation_is_reported_as_failure_not_refutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interpretation error fails the evaluation instead of passing as refuted evidence."""
    datasource = FakeDatasource(
        {
            SQL: QueryResult(
                columns=[{"name": "order_id", "data_type": "integer"}],
                rows=[{"order_id": 7, "amount": None}],
                row_count=1,
            )
        }
    )
    agent = FakeAgent(interpretation_errors={"h-1": RuntimeError("LLM request timed out")})

    result = await _evaluate(monkeypatch, datasource, agent)

    assert len(agent.interpreted) == 1
    assert result.error == "Evidence interpretation failed: LLM request timed out"
    assert result.evidence == []
    assert result.queries_executed == 1
