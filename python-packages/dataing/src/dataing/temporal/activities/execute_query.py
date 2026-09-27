"""Execute query activity for investigation workflow.

Extracts business logic from ExecuteQueryStep into a Temporal activity factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from temporalio import activity

from dataing.core.json_utils import to_json_safe

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import QueryResult


class DatabaseProtocol(Protocol):
    """Protocol for database adapter used by execute_query activity."""

    async def execute_query(self, sql: str, datasource_id: str | None = None) -> QueryResult:
        """Execute SQL query and return results.

        Raises:
            Exception: If the query fails. Never return an empty result instead.
        """
        ...


class SQLValidatorProtocol(Protocol):
    """Protocol for SQL validation."""

    def validate(self, sql: str) -> tuple[bool, str | None]:
        """Validate SQL query for safety.

        Returns:
            Tuple of (is_safe, error_message).
        """
        ...


@dataclass
class ExecuteQueryInput:
    """Input for execute_query activity."""

    investigation_id: str
    query: str
    hypothesis_id: str
    datasource_id: str | None = None


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
    database: DatabaseProtocol,
    sql_validator: SQLValidatorProtocol | None = None,
) -> Any:
    """Factory that creates execute_query activity with injected dependencies.

    Args:
        database: Database adapter for executing queries.
        sql_validator: Optional SQL validator for safety checks.

    Returns:
        The execute_query activity function.
    """

    @activity.defn
    async def execute_query(input: ExecuteQueryInput) -> ExecuteQueryResult:
        """Execute SQL query against the data source.

        This activity:
        1. Validates the query for safety (if validator provided)
        2. Executes the query via database adapter
        3. Returns structured query result
        """
        # Safety check (if validator provided)
        if sql_validator:
            is_safe, error = sql_validator.validate(input.query)
            if not is_safe:
                return ExecuteQueryResult(
                    rows=[],
                    columns=[],
                    row_count=0,
                    hypothesis_id=input.hypothesis_id,
                    error=f"Unsafe SQL: {error}",
                )

        # Execute query
        try:
            result = await database.execute_query(input.query, input.datasource_id)
            # Convert to JSON-safe types (handles date, datetime, UUID, etc.)
            rows = to_json_safe(result.rows)
            columns = to_json_safe(result.columns)
        except Exception as e:
            return ExecuteQueryResult(
                rows=[],
                columns=[],
                row_count=0,
                hypothesis_id=input.hypothesis_id,
                error=f"Query execution failed: {e}",
            )

        return ExecuteQueryResult(
            rows=rows,
            columns=columns,
            row_count=result.row_count,
            hypothesis_id=input.hypothesis_id,
            truncated=result.truncated,
            execution_time_ms=result.execution_time_ms,
        )

    return execute_query
