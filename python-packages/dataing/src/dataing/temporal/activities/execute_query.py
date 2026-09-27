"""Execute query activity for investigation workflow.

Every query is validated immediately before it runs, in the SQL dialect declared
by the adapter that runs it. Statement boundaries, comments and quoting differ
between dialects, so validating in any other dialect can let a second statement
through. There is no default dialect: a query whose dialect is unknown is refused.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from temporalio import activity

from dataing.core.exceptions import QueryValidationError
from dataing.core.json_utils import to_json_safe
from dataing.safety.validator import validate_query

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.datasource.types import QueryResult


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol for the data source adapter the execute_query activity runs SQL on."""

    async def execute_query(self, sql: str) -> QueryResult:
        """Execute SQL query and return results.

        Raises:
            Exception: If the query fails. Never return an empty result instead.
        """
        ...


class AdapterGetter(Protocol):
    """Resolves the connected adapter for a datasource owned by a tenant."""

    def __call__(self, *, tenant_id: str, datasource_id: str) -> Awaitable[BaseAdapter]:
        """Return the adapter, raising if the tenant has no such active datasource."""
        ...


@dataclass
class ExecuteQueryInput:
    """Input for execute_query activity."""

    investigation_id: str
    query: str
    hypothesis_id: str
    tenant_id: str
    datasource_id: str


@dataclass
class ExecuteQueryResult:
    """Result from execute_query activity.

    `error` is set when the query failed. Check it before reading rows: a failed
    query has no rows, but it did not return zero rows.
    """

    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    row_count: int
    hypothesis_id: str
    truncated: bool = False
    execution_time_ms: int | None = None
    error: str | None = None


def make_execute_query_activity(
    get_adapter: AdapterGetter,
) -> Any:
    """Factory that creates execute_query activity with injected dependencies.

    Args:
        get_adapter: Async function returning the connected adapter for a tenant's
            datasource.

    Returns:
        The execute_query activity function.
    """

    @activity.defn
    async def execute_query(input: ExecuteQueryInput) -> ExecuteQueryResult:
        """Execute SQL query against the data source.

        This activity:
        1. Resolves the adapter for the tenant's data source
        2. Validates the query in that adapter's SQL dialect
        3. Executes the query on the same adapter
        4. Returns structured query result

        Every failure, including an unsafe query, becomes ExecuteQueryResult.error.
        """

        def failed(error: str) -> ExecuteQueryResult:
            return ExecuteQueryResult(
                rows=[],
                columns=[],
                row_count=0,
                hypothesis_id=input.hypothesis_id,
                error=error,
            )

        try:
            adapter = await get_adapter(
                tenant_id=input.tenant_id, datasource_id=input.datasource_id
            )
            dialect = adapter.capabilities.sql_dialect
        except Exception as e:
            return failed(f"Query execution failed: {e}")

        if not dialect or not isinstance(adapter, DatabaseProtocol):
            return failed(
                f"Unsafe SQL: {type(adapter).__name__} declares no SQL dialect, "
                "so the query cannot be validated"
            )

        try:
            validate_query(input.query, dialect=dialect)
        except QueryValidationError as e:
            return failed(f"Unsafe SQL: {e}")

        try:
            result = await adapter.execute_query(input.query)
            # Convert to JSON-safe types (handles date, datetime, UUID, etc.)
            rows = to_json_safe(result.rows)
            columns = to_json_safe(result.columns)
        except Exception as e:
            return failed(f"Query execution failed: {e}")

        return ExecuteQueryResult(
            rows=rows,
            columns=columns,
            row_count=result.row_count,
            hypothesis_id=input.hypothesis_id,
            truncated=result.truncated,
            execution_time_ms=result.execution_time_ms,
        )

    return execute_query
