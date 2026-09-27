"""Unit tests for the Temporal worker's AdapterDatabase."""

from __future__ import annotations

import pytest

from dataing.adapters.datasource.errors import QuerySyntaxError
from dataing.adapters.datasource.types import QueryResult
from dataing.entrypoints.temporal_worker import AdapterDatabase


class FakeDatasource:
    """Datasource adapter that returns a canned result or raises a canned error."""

    def __init__(self, result: QueryResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.executed: list[str] = []

    async def execute_query(self, sql: str) -> QueryResult:
        self.executed.append(sql)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _database_for(datasource: FakeDatasource) -> AdapterDatabase:
    async def get_adapter(datasource_id: str) -> FakeDatasource:
        assert datasource_id == "ds-1"
        return datasource

    return AdapterDatabase(get_adapter)


async def test_query_error_propagates() -> None:
    """Adapter errors are raised, never converted into an empty result."""
    datasource = FakeDatasource(error=QuerySyntaxError('column "amount" does not exist'))

    with pytest.raises(QuerySyntaxError, match='column "amount" does not exist'):
        await _database_for(datasource).execute_query("SELECT amount FROM orders", "ds-1")


async def test_returns_adapter_query_result() -> None:
    """The adapter's QueryResult is returned whole, including truncation and timing."""
    query_result = QueryResult(
        columns=[{"name": "amount", "data_type": "decimal"}],
        rows=[{"amount": None}],
        row_count=1,
        truncated=True,
        execution_time_ms=42,
    )
    datasource = FakeDatasource(result=query_result)

    result = await _database_for(datasource).execute_query("SELECT amount FROM orders", "ds-1")

    assert result == query_result
    assert datasource.executed == ["SELECT amount FROM orders"]


async def test_requires_datasource_id() -> None:
    """A query without a datasource is an error, not an empty result."""
    datasource = FakeDatasource()

    with pytest.raises(RuntimeError, match="No datasource_id"):
        await _database_for(datasource).execute_query("SELECT 1", None)

    assert datasource.executed == []
