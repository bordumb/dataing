"""Execute query activity for investigation workflow.

Extracts business logic from ExecuteQueryStep into a Temporal activity factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from temporalio import activity


class DatabaseProtocol(Protocol):
    """Protocol for database adapter used by execute_query activity."""

    async def execute_query(self, sql: str) -> dict[str, Any]:
        """Execute SQL query and return results."""
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


@dataclass
class ExecuteQueryResult:
    """Result from execute_query activity."""

    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    hypothesis_id: str
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
            result = await database.execute_query(input.query)
            # Convert QueryResult to dict if it's a Pydantic model
            if hasattr(result, "model_dump"):
                result_dict: dict[str, Any] = result.model_dump()
            else:
                result_dict = result
        except Exception as e:
            return ExecuteQueryResult(
                rows=[],
                columns=[],
                row_count=0,
                hypothesis_id=input.hypothesis_id,
                error=f"Query execution failed: {e}",
            )

        return ExecuteQueryResult(
            rows=result_dict.get("rows", []),
            columns=result_dict.get("columns", []),
            row_count=result_dict.get("row_count", len(result_dict.get("rows", []))),
            hypothesis_id=input.hypothesis_id,
        )

    return execute_query


# Standalone activity for POC/testing (returns mock result)
@activity.defn
async def execute_query(
    investigation_id: str,
    query: str,
    hypothesis_id: str,
) -> dict[str, Any]:
    """POC execute_query activity with mock result.

    Used for testing without real dependencies. Production code should use
    make_execute_query_activity() factory instead.
    """
    return {
        "rows": [{"count": 42}],
        "columns": ["count"],
        "row_count": 1,
        "hypothesis_id": hypothesis_id,
    }
