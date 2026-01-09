"""Base class for SQL database adapters.

This module provides the abstract base class for all SQL-speaking
data source adapters, adding query execution capabilities.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    QueryLanguage,
    QueryResult,
)


class SQLAdapter(BaseAdapter):
    """Abstract base class for SQL database adapters.

    Extends BaseAdapter with SQL query execution capabilities.
    All SQL adapters must implement:
    - execute_query: Execute arbitrary SQL
    - _get_schema_query: Return SQL to fetch schema metadata
    - _get_tables_query: Return SQL to list tables
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        """SQL adapters support SQL queries by default."""
        return AdapterCapabilities(
            supports_sql=True,
            supports_sampling=True,
            supports_row_count=True,
            supports_column_stats=True,
            supports_preview=True,
            supports_write=False,
            query_language=QueryLanguage.SQL,
            max_concurrent_queries=10,
        )

    @abstractmethod
    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Execute a SQL query against the data source.

        Args:
            sql: The SQL query to execute.
            params: Optional query parameters.
            timeout_seconds: Query timeout in seconds.
            limit: Optional row limit (may be applied via LIMIT clause).

        Returns:
            QueryResult with columns, rows, and metadata.

        Raises:
            QuerySyntaxError: If the query syntax is invalid.
            QueryTimeoutError: If the query times out.
            AccessDeniedError: If access is denied.
        """
        ...

    async def sample(
        self,
        table: str,
        n: int = 100,
        schema: str | None = None,
    ) -> QueryResult:
        """Get a random sample of rows from a table.

        Args:
            table: Table name.
            n: Number of rows to sample.
            schema: Optional schema name.

        Returns:
            QueryResult with sampled rows.
        """
        full_table = f"{schema}.{table}" if schema else table
        sql = self._build_sample_query(full_table, n)
        return await self.execute_query(sql, limit=n)

    async def preview(
        self,
        table: str,
        n: int = 100,
        schema: str | None = None,
    ) -> QueryResult:
        """Get a preview of rows from a table (first N rows).

        Args:
            table: Table name.
            n: Number of rows to preview.
            schema: Optional schema name.

        Returns:
            QueryResult with preview rows.
        """
        full_table = f"{schema}.{table}" if schema else table
        sql = f"SELECT * FROM {full_table} LIMIT {n}"
        return await self.execute_query(sql, limit=n)

    async def count_rows(
        self,
        table: str,
        schema: str | None = None,
    ) -> int:
        """Get the row count for a table.

        Args:
            table: Table name.
            schema: Optional schema name.

        Returns:
            Number of rows in the table.
        """
        full_table = f"{schema}.{table}" if schema else table
        sql = f"SELECT COUNT(*) as cnt FROM {full_table}"
        result = await self.execute_query(sql)
        if result.rows:
            return int(result.rows[0].get("cnt", 0))
        return 0

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build a sampling query for the database type.

        Default implementation uses TABLESAMPLE if available,
        otherwise falls back to ORDER BY RANDOM().
        Subclasses should override for optimal sampling.

        Args:
            table: Full table name (schema.table).
            n: Number of rows to sample.

        Returns:
            SQL query string.
        """
        return f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT {n}"

    @abstractmethod
    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        """Fetch table metadata from the database.

        Returns:
            List of dictionaries with table metadata:
            - catalog: Catalog name
            - schema: Schema name
            - table_name: Table name
            - table_type: Type (table, view, etc.)
            - columns: List of column dictionaries
        """
        ...

    async def get_column_stats(
        self,
        table: str,
        columns: list[str],
        schema: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Get statistics for specific columns.

        Args:
            table: Table name.
            columns: List of column names.
            schema: Optional schema name.

        Returns:
            Dictionary mapping column names to their statistics.
        """
        full_table = f"{schema}.{table}" if schema else table
        stats = {}

        for col in columns:
            sql = f"""
                SELECT
                    COUNT(*) as total_count,
                    COUNT({col}) as non_null_count,
                    COUNT(DISTINCT {col}) as distinct_count,
                    MIN({col}::text) as min_value,
                    MAX({col}::text) as max_value
                FROM {full_table}
            """
            try:
                result = await self.execute_query(sql, timeout_seconds=60)
                if result.rows:
                    row = result.rows[0]
                    total = row.get("total_count", 0)
                    non_null = row.get("non_null_count", 0)
                    null_count = total - non_null if total else 0
                    stats[col] = {
                        "null_count": null_count,
                        "null_rate": null_count / total if total > 0 else 0.0,
                        "distinct_count": row.get("distinct_count"),
                        "min_value": row.get("min_value"),
                        "max_value": row.get("max_value"),
                    }
            except Exception:
                stats[col] = {
                    "null_count": 0,
                    "null_rate": 0.0,
                    "distinct_count": None,
                    "min_value": None,
                    "max_value": None,
                }

        return stats
