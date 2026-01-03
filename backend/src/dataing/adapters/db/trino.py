"""Trino implementation of DatabaseAdapter."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from trino.dbapi import connect

from dataing.core.domain_types import QueryResult, SchemaContext, TableSchema


class TrinoAdapter:
    """Trino implementation of DatabaseAdapter.

    Trino's Python client is synchronous, so we wrap
    calls in an executor for async compatibility.

    Attributes:
        host: Trino server host.
        port: Trino server port.
        catalog: Trino catalog to use.
        schema: Trino schema to use.
    """

    def __init__(
        self,
        host: str,
        port: int,
        catalog: str,
        schema: str,
        user: str = "dataing",
    ) -> None:
        """Initialize the Trino adapter.

        Args:
            host: Trino server host.
            port: Trino server port.
            catalog: Trino catalog to use.
            schema: Trino schema to use.
            user: User for authentication.
        """
        self.host = host
        self.port = port
        self.catalog = catalog
        self.schema = schema
        self.user = user
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def connect(self) -> None:
        """Initialize connection (no-op for Trino as connections are per-query)."""
        pass

    async def close(self) -> None:
        """Cleanup executor."""
        self._executor.shutdown(wait=True)

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        """Execute a read-only SQL query.

        Args:
            sql: The SQL query to execute.
            timeout_seconds: Maximum time to wait for query completion.

        Returns:
            QueryResult with columns, rows, and row count.

        Raises:
            asyncio.TimeoutError: If query exceeds timeout.
        """
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(self._executor, self._execute_sync, sql),
            timeout=timeout_seconds,
        )

    def _execute_sync(self, sql: str) -> QueryResult:
        """Execute query synchronously.

        Args:
            sql: The SQL query to execute.

        Returns:
            QueryResult with columns, rows, and row count.
        """
        conn = connect(
            host=self.host,
            port=self.port,
            catalog=self.catalog,
            schema=self.schema,
            user=self.user,
        )
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = tuple(desc[0] for desc in cursor.description) if cursor.description else ()

            result_rows = tuple(dict(zip(columns, row, strict=False)) for row in rows)

            return QueryResult(
                columns=columns,
                rows=result_rows,
                row_count=len(rows),
            )
        finally:
            conn.close()

    async def get_schema(self, table_pattern: str | None = None) -> SchemaContext:
        """Discover available tables and columns.

        Args:
            table_pattern: Optional pattern to filter tables.

        Returns:
            SchemaContext with all discovered tables.
        """
        query = f"""
            SELECT table_schema, table_name, column_name, data_type
            FROM {self.catalog}.information_schema.columns
            WHERE table_schema = '{self.schema}'
            ORDER BY table_name, ordinal_position
        """

        loop = asyncio.get_event_loop()
        rows: list[dict[str, Any]] = await loop.run_in_executor(
            self._executor, self._fetch_schema_sync, query
        )

        # Group by table - use TypedDict-like structure
        tables_dict: dict[str, dict[str, Any]] = {}
        for row in rows:
            full_name = f"{row['table_schema']}.{row['table_name']}"

            # Apply filter if provided
            if table_pattern and table_pattern.lower() not in full_name.lower():
                continue

            if full_name not in tables_dict:
                tables_dict[full_name] = {
                    "columns": [],
                    "column_types": {},
                }
            tables_dict[full_name]["columns"].append(row["column_name"])
            tables_dict[full_name]["column_types"][row["column_name"]] = row["data_type"]

        # Convert to TableSchema objects
        tables = tuple(
            TableSchema(
                table_name=name,
                columns=tuple(data["columns"]),
                column_types=dict(data["column_types"]),
            )
            for name, data in tables_dict.items()
        )

        return SchemaContext(tables=tables)

    def _fetch_schema_sync(self, query: str) -> list[dict[str, Any]]:
        """Fetch schema information synchronously.

        Args:
            query: Schema query to execute.

        Returns:
            List of row dictionaries.
        """
        conn = connect(
            host=self.host,
            port=self.port,
            catalog=self.catalog,
            schema=self.schema,
            user=self.user,
        )
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return [dict(zip(columns, row, strict=False)) for row in rows]
        finally:
            conn.close()
