"""DuckDB implementation of DatabaseAdapter.

Supports two modes:
1. Parquet directory: Auto-registers all .parquet files as views
2. DuckDB file: Opens existing .duckdb database

Always read-only for safety.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from dataing.core.domain_types import QueryResult, SchemaContext, TableSchema

if TYPE_CHECKING:
    pass


class DuckDBAdapter:
    """DuckDB implementation of DatabaseAdapter.

    Uses DuckDB for fast in-memory analytics, particularly useful
    for demo scenarios with parquet files.

    Attributes:
        path: Path to .duckdb file or directory of parquet files.
        read_only: Always True for safety.
    """

    def __init__(self, path: str, read_only: bool = True) -> None:
        """Initialize the DuckDB adapter.

        Args:
            path: Path to .duckdb file or directory containing parquet files.
            read_only: Whether to open in read-only mode (always True for safety).
        """
        self.path = Path(path)
        self.read_only = True  # Always read-only for safety
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._is_parquet_dir = False

    async def connect(self) -> None:
        """Establish DuckDB connection.

        If path is a directory, creates an in-memory database and
        registers all .parquet files as views.

        Should be called during application startup.
        """
        # Run in thread pool since DuckDB operations are synchronous
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._connect_sync)

    def _connect_sync(self) -> None:
        """Synchronous connection logic."""
        if self.path.is_dir():
            # Parquet directory mode - create in-memory database
            self._is_parquet_dir = True
            self._conn = duckdb.connect(":memory:")

            # Register each .parquet file as a table
            for parquet_file in self.path.glob("*.parquet"):
                table_name = parquet_file.stem  # filename without extension
                self._conn.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{parquet_file}')"
                )
        else:
            # DuckDB file mode - open in read-only mode
            self._conn = duckdb.connect(str(self.path), read_only=True)

    async def close(self) -> None:
        """Close DuckDB connection.

        Should be called during application shutdown.
        """
        if self._conn:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._conn.close)
            self._conn = None

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        """Execute a read-only SQL query.

        Args:
            sql: The SQL query to execute.
            timeout_seconds: Maximum time to wait for query completion.

        Returns:
            QueryResult with columns, rows, and row count.

        Raises:
            RuntimeError: If connection not initialized.
            asyncio.TimeoutError: If query exceeds timeout.
        """
        if not self._conn:
            raise RuntimeError("Connection not initialized. Call connect() first.")

        loop = asyncio.get_event_loop()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._execute_query_sync, sql),
                timeout=timeout_seconds,
            )
            return result
        except TimeoutError as err:
            raise TimeoutError(f"Query timed out after {timeout_seconds} seconds") from err

    def _execute_query_sync(self, sql: str) -> QueryResult:
        """Synchronous query execution."""
        if not self._conn:
            raise RuntimeError("Connection not initialized")

        result = self._conn.execute(sql)
        rows = result.fetchall()
        columns = [desc[0] for desc in result.description] if result.description else []

        if not rows:
            return QueryResult(
                columns=tuple(columns),
                rows=(),
                row_count=0,
            )

        # Convert rows to list of dicts
        result_rows = tuple(dict(zip(columns, row, strict=False)) for row in rows)

        return QueryResult(
            columns=tuple(columns),
            rows=result_rows,
            row_count=len(rows),
        )

    async def get_schema(self, table_pattern: str | None = None) -> SchemaContext:
        """Discover available tables and columns.

        Args:
            table_pattern: Optional pattern to filter tables.

        Returns:
            SchemaContext with all discovered tables.

        Raises:
            RuntimeError: If connection not initialized.
        """
        if not self._conn:
            raise RuntimeError("Connection not initialized. Call connect() first.")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_schema_sync, table_pattern)

    def _get_schema_sync(self, table_pattern: str | None = None) -> SchemaContext:
        """Synchronous schema discovery."""
        if not self._conn:
            raise RuntimeError("Connection not initialized")

        # Get all tables
        tables_result = self._conn.execute("SHOW TABLES").fetchall()

        tables = []
        for (table_name,) in tables_result:
            # Apply filter if provided
            if table_pattern and table_pattern.lower() not in table_name.lower():
                continue

            # Get column info for each table
            columns_result = self._conn.execute(f"DESCRIBE {table_name}").fetchall()

            columns = []
            column_types = {}
            for col_info in columns_result:
                col_name = col_info[0]
                col_type = col_info[1]
                columns.append(col_name)
                column_types[col_name] = col_type

            tables.append(
                TableSchema(
                    table_name=table_name,
                    columns=tuple(columns),
                    column_types=column_types,
                )
            )

        return SchemaContext(tables=tuple(tables))

    async def get_column_statistics(
        self, table_name: str, column_name: str
    ) -> dict[str, float | int | str | None]:
        """Get statistics for a specific column.

        Args:
            table_name: Name of the table.
            column_name: Name of the column.

        Returns:
            Dictionary with statistics (count, null_count, null_rate,
            distinct_count, min, max, avg for numerics).
        """
        if not self._conn:
            raise RuntimeError("Connection not initialized. Call connect() first.")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._get_column_statistics_sync, table_name, column_name
        )

    def _get_column_statistics_sync(
        self, table_name: str, column_name: str
    ) -> dict[str, float | int | str | None]:
        """Synchronous column statistics."""
        if not self._conn:
            raise RuntimeError("Connection not initialized")

        stats: dict[str, float | int | str | None] = {}

        # Basic counts
        count_result = self._conn.execute(
            f"""
            SELECT
                COUNT(*) as total_count,
                COUNT({column_name}) as non_null_count,
                COUNT(*) - COUNT({column_name}) as null_count,
                ROUND(100.0 * (COUNT(*) - COUNT({column_name})) / COUNT(*), 2) as null_rate,
                APPROX_COUNT_DISTINCT({column_name}) as distinct_count
            FROM {table_name}
            """
        ).fetchone()

        if count_result:
            stats["total_count"] = count_result[0]
            stats["non_null_count"] = count_result[1]
            stats["null_count"] = count_result[2]
            stats["null_rate"] = count_result[3]
            stats["distinct_count"] = count_result[4]

        # Try to get min/max/avg for numeric columns
        try:
            numeric_result = self._conn.execute(
                f"""
                SELECT
                    MIN({column_name})::VARCHAR as min_val,
                    MAX({column_name})::VARCHAR as max_val,
                    AVG(TRY_CAST({column_name} AS DOUBLE)) as avg_val
                FROM {table_name}
                """
            ).fetchone()

            if numeric_result:
                stats["min"] = numeric_result[0]
                stats["max"] = numeric_result[1]
                stats["avg"] = numeric_result[2]
        except Exception:
            # Column might not support numeric operations
            pass

        return stats

    async def get_table_row_count(self, table_name: str) -> int:
        """Get approximate row count for a table.

        Args:
            table_name: Name of the table.

        Returns:
            Approximate row count.
        """
        result = await self.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        if result.rows:
            return list(result.rows[0].values())[0]  # type: ignore
        return 0
