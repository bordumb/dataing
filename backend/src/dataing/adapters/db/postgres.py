"""PostgreSQL implementation of DatabaseAdapter."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import asyncpg

from dataing.core.domain_types import QueryResult, SchemaContext, TableSchema

if TYPE_CHECKING:
    pass


class PostgresAdapter:
    """PostgreSQL implementation of DatabaseAdapter.

    Uses asyncpg for async PostgreSQL connections with
    connection pooling for efficiency.

    Attributes:
        connection_string: PostgreSQL connection URL.
    """

    def __init__(self, connection_string: str) -> None:
        """Initialize the Postgres adapter.

        Args:
            connection_string: PostgreSQL connection URL.
        """
        self.connection_string = connection_string
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Establish connection pool.

        Should be called during application startup.
        """
        self._pool = await asyncpg.create_pool(self.connection_string)

    async def close(self) -> None:
        """Close connection pool.

        Should be called during application shutdown.
        """
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        """Execute a read-only SQL query.

        Args:
            sql: The SQL query to execute.
            timeout_seconds: Maximum time to wait for query completion.

        Returns:
            QueryResult with columns, rows, and row count.

        Raises:
            RuntimeError: If connection pool not initialized.
            asyncio.TimeoutError: If query exceeds timeout.
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized. Call connect() first.")

        async with self._pool.acquire() as conn:
            rows = await asyncio.wait_for(
                conn.fetch(sql),
                timeout=timeout_seconds,
            )

            if not rows:
                return QueryResult(
                    columns=(),
                    rows=(),
                    row_count=0,
                )

            columns = tuple(rows[0].keys())
            result_rows = tuple(dict(r) for r in rows)

            return QueryResult(
                columns=columns,
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
            RuntimeError: If connection pool not initialized.
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized. Call connect() first.")

        query = """
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name, ordinal_position
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)

        # Group by table - use dict[str, Any] for mixed value types
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
