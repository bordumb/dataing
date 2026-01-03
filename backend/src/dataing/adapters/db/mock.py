"""Mock database adapter for testing."""

from __future__ import annotations

import re
from typing import Any

from dataing.core.domain_types import QueryResult, SchemaContext, TableSchema


class MockDatabaseAdapter:
    """Mock adapter for testing - returns canned responses.

    This adapter is useful for:
    - Unit testing without a real database
    - Integration testing with deterministic responses
    - Development without database setup

    Attributes:
        responses: Map of query patterns to responses.
        executed_queries: Log of all executed queries.
    """

    def __init__(
        self,
        responses: dict[str, QueryResult] | None = None,
        schema: SchemaContext | None = None,
    ) -> None:
        """Initialize the mock adapter.

        Args:
            responses: Map of query patterns to responses.
            schema: Mock schema to return from get_schema.
        """
        self.responses = responses or {}
        self._mock_schema = schema or self._default_schema()
        self.executed_queries: list[str] = []

    def _default_schema(self) -> SchemaContext:
        """Create a default mock schema for testing."""
        return SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.users",
                    columns=("id", "email", "created_at", "updated_at"),
                    column_types={
                        "id": "integer",
                        "email": "varchar",
                        "created_at": "timestamp",
                        "updated_at": "timestamp",
                    },
                ),
                TableSchema(
                    table_name="public.orders",
                    columns=("id", "user_id", "total", "status", "created_at"),
                    column_types={
                        "id": "integer",
                        "user_id": "integer",
                        "total": "numeric",
                        "status": "varchar",
                        "created_at": "timestamp",
                    },
                ),
                TableSchema(
                    table_name="public.products",
                    columns=("id", "name", "price", "category"),
                    column_types={
                        "id": "integer",
                        "name": "varchar",
                        "price": "numeric",
                        "category": "varchar",
                    },
                ),
            )
        )

    async def connect(self) -> None:
        """No-op for mock adapter."""
        pass

    async def close(self) -> None:
        """No-op for mock adapter."""
        pass

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        """Execute a mock query.

        Matches the SQL against registered patterns and returns
        the corresponding response.

        Args:
            sql: The SQL query to execute.
            timeout_seconds: Ignored for mock.

        Returns:
            Matching QueryResult or empty result.
        """
        self.executed_queries.append(sql)

        # Find matching response by substring (case-insensitive)
        for pattern, response in self.responses.items():
            if pattern.lower() in sql.lower():
                return response

        # Default empty response
        return QueryResult(columns=(), rows=(), row_count=0)

    async def get_schema(self, table_pattern: str | None = None) -> SchemaContext:
        """Return mock schema.

        Args:
            table_pattern: Optional filter pattern.

        Returns:
            Mock SchemaContext.
        """
        if table_pattern:
            filtered_tables = tuple(
                t for t in self._mock_schema.tables if table_pattern.lower() in t.table_name.lower()
            )
            return SchemaContext(tables=filtered_tables)
        return self._mock_schema

    def add_response(self, pattern: str, response: QueryResult) -> None:
        """Add a canned response for a query pattern.

        Args:
            pattern: Substring to match in queries.
            response: QueryResult to return when pattern matches.
        """
        self.responses[pattern] = response

    def add_row_count_response(
        self,
        pattern: str,
        count: int,
    ) -> None:
        """Add a simple row count response.

        Args:
            pattern: Substring to match in queries.
            count: Row count to return.
        """
        self.responses[pattern] = QueryResult(
            columns=("count",),
            rows=({"count": count},),
            row_count=1,
        )

    def clear_queries(self) -> None:
        """Clear the executed queries log."""
        self.executed_queries = []

    def get_query_count(self) -> int:
        """Get the number of queries executed."""
        return len(self.executed_queries)

    def was_query_executed(self, pattern: str) -> bool:
        """Check if a query matching pattern was executed.

        Args:
            pattern: Substring to search for.

        Returns:
            True if any executed query contains the pattern.
        """
        return any(pattern.lower() in q.lower() for q in self.executed_queries)
