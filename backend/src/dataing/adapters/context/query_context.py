"""Query Context - Executes queries and formats results.

This module handles query execution against data sources,
with proper error handling, timeouts, and result formatting
for LLM interpretation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from dataing.core.domain_types import QueryResult

if TYPE_CHECKING:
    from dataing.core.interfaces import DatabaseAdapter

logger = structlog.get_logger()


class QueryExecutionError(Exception):
    """Raised when query execution fails."""

    def __init__(self, message: str, query: str, original_error: Exception | None = None):
        """Initialize QueryExecutionError.

        Args:
            message: Error description.
            query: The query that failed.
            original_error: The underlying exception if any.
        """
        super().__init__(message)
        self.query = query
        self.original_error = original_error


class QueryContext:
    """Executes queries and formats results for LLM.

    This class is responsible for:
    1. Executing SQL queries with timeout handling
    2. Formatting results for LLM interpretation
    3. Handling and reporting query errors

    Attributes:
        default_timeout: Default query timeout in seconds.
        max_result_rows: Maximum rows to include in results.
    """

    def __init__(
        self,
        default_timeout: int = 30,
        max_result_rows: int = 100,
    ) -> None:
        """Initialize the query context.

        Args:
            default_timeout: Default timeout in seconds.
            max_result_rows: Maximum rows to return.
        """
        self.default_timeout = default_timeout
        self.max_result_rows = max_result_rows

    async def execute(
        self,
        adapter: DatabaseAdapter,
        sql: str,
        timeout: int | None = None,
    ) -> QueryResult:
        """Execute a SQL query with timeout.

        Args:
            adapter: Connected database adapter.
            sql: SQL query to execute.
            timeout: Optional timeout override.

        Returns:
            QueryResult with columns, rows, and metadata.

        Raises:
            QueryExecutionError: If query fails or times out.
        """
        timeout = timeout or self.default_timeout

        logger.debug("executing_query", sql_preview=sql[:100], timeout=timeout)

        try:
            result = await adapter.execute_query(sql, timeout_seconds=timeout)

            logger.info(
                "query_succeeded",
                row_count=result.row_count,
                columns=len(result.columns),
            )

            return result

        except TimeoutError as e:
            logger.warning("query_timeout", sql_preview=sql[:100], timeout=timeout)
            raise QueryExecutionError(
                f"Query timed out after {timeout} seconds",
                query=sql,
                original_error=e,
            ) from e

        except Exception as e:
            logger.error("query_failed", sql_preview=sql[:100], error=str(e))
            raise QueryExecutionError(
                f"Query execution failed: {e}",
                query=sql,
                original_error=e,
            ) from e

    def format_result(
        self,
        result: QueryResult,
        max_rows: int | None = None,
    ) -> str:
        """Format query result for LLM interpretation.

        Args:
            result: QueryResult to format.
            max_rows: Maximum rows to include.

        Returns:
            Human-readable result summary.
        """
        max_rows = max_rows or self.max_result_rows

        if result.row_count == 0:
            return "No rows returned"

        lines = [
            f"Columns: {', '.join(result.columns)}",
            f"Total rows: {result.row_count}",
            "",
            "Sample rows:",
        ]

        for row in result.rows[:max_rows]:
            row_str = ", ".join(f"{k}={v}" for k, v in row.items())
            lines.append(f"  {row_str}")

        if result.row_count > max_rows:
            lines.append(f"  ... and {result.row_count - max_rows} more rows")

        return "\n".join(lines)

    def format_as_table(
        self,
        result: QueryResult,
        max_rows: int | None = None,
    ) -> str:
        """Format query result as markdown table.

        Args:
            result: QueryResult to format.
            max_rows: Maximum rows to include.

        Returns:
            Markdown table string.
        """
        max_rows = max_rows or self.max_result_rows

        if result.row_count == 0:
            return "No rows returned"

        lines = []

        # Header
        lines.append("| " + " | ".join(result.columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(result.columns)) + " |")

        # Rows
        for row in result.rows[:max_rows]:
            values = [str(row.get(col, "")) for col in result.columns]
            lines.append("| " + " | ".join(values) + " |")

        if result.row_count > max_rows:
            lines.append(f"\n*({result.row_count - max_rows} more rows not shown)*")

        return "\n".join(lines)

    def summarize_result(self, result: QueryResult) -> dict[str, Any]:
        """Create a summary dictionary of query results.

        Args:
            result: QueryResult to summarize.

        Returns:
            Dictionary with summary statistics.
        """
        return {
            "row_count": result.row_count,
            "column_count": len(result.columns),
            "columns": list(result.columns),
            "has_data": result.row_count > 0,
            "sample_size": min(result.row_count, 5),
        }

    async def execute_multiple(
        self,
        adapter: DatabaseAdapter,
        queries: list[str],
        timeout: int | None = None,
    ) -> list[QueryResult | QueryExecutionError]:
        """Execute multiple queries, collecting all results.

        Args:
            adapter: Connected database adapter.
            queries: List of SQL queries.
            timeout: Optional timeout per query.

        Returns:
            List of QueryResult or QueryExecutionError for each query.
        """
        results = []

        for sql in queries:
            try:
                result = await self.execute(adapter, sql, timeout)
                results.append(result)
            except QueryExecutionError as e:
                results.append(e)

        return results
