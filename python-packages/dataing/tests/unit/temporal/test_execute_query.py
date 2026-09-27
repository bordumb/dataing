"""Unit tests for the execute_query activity."""

from __future__ import annotations

from datetime import date

from dataing.adapters.datasource.errors import QuerySyntaxError
from dataing.adapters.datasource.types import QueryResult
from dataing.temporal.activities import (
    ExecuteQueryInput,
    ExecuteQueryResult,
    make_execute_query_activity,
)

QUERY_INPUT = ExecuteQueryInput(
    investigation_id="inv-1",
    query="SELECT day, amount FROM orders",
    hypothesis_id="h-1",
    datasource_id="ds-1",
)


class FakeDatabase:
    """DatabaseProtocol stub that returns a canned result or raises a canned error."""

    def __init__(self, result: QueryResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def execute_query(self, sql: str, datasource_id: str | None = None) -> QueryResult:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


async def test_failed_query_returns_error_result() -> None:
    """A database error becomes an explicit error, not an empty success."""
    database = FakeDatabase(error=QuerySyntaxError('column "amount" does not exist'))
    execute_query = make_execute_query_activity(database=database)

    result = await execute_query(QUERY_INPUT)

    assert result == ExecuteQueryResult(
        rows=[],
        columns=[],
        row_count=0,
        hypothesis_id="h-1",
        error='Query execution failed: column "amount" does not exist',
    )


async def test_unserializable_result_returns_error_result() -> None:
    """A result that can't be made JSON-safe is reported, not raised into retries."""

    class DriverValue:
        """A driver-specific value with no JSON representation."""

    database = FakeDatabase(
        result=QueryResult(
            columns=[{"name": "span", "data_type": "unknown"}],
            rows=[{"span": DriverValue()}],
            row_count=1,
        )
    )
    execute_query = make_execute_query_activity(database=database)

    result = await execute_query(QUERY_INPUT)

    assert result.error is not None
    assert result.error.startswith("Query execution failed:")
    assert result.rows == []
    assert result.row_count == 0


async def test_successful_query_carries_full_result() -> None:
    """All QueryResult fields are carried over, with rows made JSON-safe."""
    database = FakeDatabase(
        result=QueryResult(
            columns=[{"name": "day", "data_type": "date"}],
            rows=[{"day": date(2024, 1, 15), "amount": None}],
            row_count=1,
            truncated=True,
            execution_time_ms=42,
        )
    )
    execute_query = make_execute_query_activity(database=database)

    result = await execute_query(QUERY_INPUT)

    assert result == ExecuteQueryResult(
        rows=[{"day": "2024-01-15", "amount": None}],
        columns=[{"name": "day", "data_type": "date"}],
        row_count=1,
        hypothesis_id="h-1",
        truncated=True,
        execution_time_ms=42,
    )
