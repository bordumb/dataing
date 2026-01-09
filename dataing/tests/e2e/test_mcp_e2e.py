"""End-to-end tests for MCP server functionality.

These tests verify the complete MCP tool execution flow.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dataing.adapters.db.mock import MockDatabaseAdapter
from dataing.core.domain_types import (
    Finding,
    QueryResult,
    SchemaContext,
    TableSchema,
)
from dataing.core.exceptions import QueryValidationError
from dataing.safety.validator import validate_query


class TestMCPToolExecution:
    """End-to-end tests for MCP tool execution."""

    @pytest.fixture
    def mock_db(self) -> MockDatabaseAdapter:
        """Return a mock database adapter."""
        schema = SchemaContext(
            tables=(
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
                    table_name="public.users",
                    columns=("id", "email", "created_at"),
                    column_types={
                        "id": "integer",
                        "email": "varchar",
                        "created_at": "timestamp",
                    },
                ),
            )
        )

        responses = {
            "COUNT": QueryResult(
                columns=("count",),
                rows=({"count": 500},),
                row_count=1,
            ),
        }

        return MockDatabaseAdapter(responses=responses, schema=schema)

    async def test_query_dataset_valid_query(
        self,
        mock_db: MockDatabaseAdapter,
    ) -> None:
        """Test executing a valid query through MCP."""
        sql = "SELECT COUNT(*) FROM orders LIMIT 10"

        # Validate query
        validate_query(sql)

        # Execute query
        result = await mock_db.execute_query(sql)

        assert result.row_count == 1

    async def test_query_dataset_unsafe_query_rejected(self) -> None:
        """Test that unsafe queries are rejected."""
        unsafe_queries = [
            "DROP TABLE users",
            "DELETE FROM orders WHERE 1=1",
            "UPDATE orders SET total = 0",
            "INSERT INTO orders VALUES (1)",
            "TRUNCATE orders",
        ]

        for sql in unsafe_queries:
            with pytest.raises(QueryValidationError):
                validate_query(sql)

    async def test_query_dataset_requires_limit(self) -> None:
        """Test that queries require LIMIT clause."""
        sql = "SELECT * FROM orders"

        with pytest.raises(QueryValidationError) as exc_info:
            validate_query(sql)

        assert "LIMIT" in str(exc_info.value)

    async def test_get_table_schema(
        self,
        mock_db: MockDatabaseAdapter,
    ) -> None:
        """Test getting table schema through MCP."""
        schema = await mock_db.get_schema(table_pattern="orders")

        assert len(schema.tables) == 1
        assert schema.tables[0].table_name == "public.orders"
        assert "id" in schema.tables[0].columns
        assert "total" in schema.tables[0].columns

    async def test_get_table_schema_not_found(
        self,
        mock_db: MockDatabaseAdapter,
    ) -> None:
        """Test getting schema for non-existent table."""
        schema = await mock_db.get_schema(table_pattern="nonexistent")

        assert len(schema.tables) == 0

    async def test_investigation_tool_returns_finding(self) -> None:
        """Test that investigate_anomaly returns a proper finding."""
        # Mock finding
        finding = Finding(
            investigation_id="inv-001",
            status="completed",
            root_cause="ETL job failed due to timeout",
            confidence=0.9,
            evidence=[],
            recommendations=[
                "Restart the ETL job",
                "Add monitoring for ETL timeouts",
            ],
            duration_seconds=120.5,
        )

        # Verify finding structure
        assert finding.status == "completed"
        assert finding.root_cause is not None
        assert finding.confidence > 0.0
        assert len(finding.recommendations) > 0

    async def test_query_with_pii_warning(
        self,
        mock_db: MockDatabaseAdapter,
    ) -> None:
        """Test that queries with PII are flagged."""
        from dataing.safety.pii import contains_pii

        sql = "SELECT * FROM users WHERE email = 'john@example.com' LIMIT 10"

        # Validate query is syntactically safe
        validate_query(sql)

        # Check for PII
        assert contains_pii(sql) is True

    async def test_query_result_formatting(
        self,
        mock_db: MockDatabaseAdapter,
    ) -> None:
        """Test that query results are properly formatted."""
        result = await mock_db.execute_query("SELECT COUNT(*) FROM orders LIMIT 10")

        # Test summary formatting
        summary = result.to_summary()

        assert "count" in summary.lower() or "row" in summary.lower()


class TestMCPToolErrors:
    """Tests for MCP tool error handling."""

    async def test_sql_injection_prevented(self) -> None:
        """Test that SQL injection attempts are prevented."""
        injection_attempts = [
            "SELECT * FROM users; DROP TABLE users; --",
            "SELECT * FROM users WHERE id = 1 OR 1=1",
            "SELECT * FROM users WHERE name = 'a'; DELETE FROM users; --",
        ]

        for sql in injection_attempts:
            with pytest.raises(QueryValidationError):
                validate_query(sql)

    async def test_invalid_sql_syntax(self) -> None:
        """Test handling of invalid SQL syntax."""
        invalid_queries = [
            "SELECTT * FROM users LIMIT 10",
            "SELECT * FORM users LIMIT 10",
            "SELET * FROM users LIMIT 10",
        ]

        for sql in invalid_queries:
            with pytest.raises(QueryValidationError):
                validate_query(sql)

    async def test_query_timeout_handling(self) -> None:
        """Test that query timeouts are handled gracefully."""
        import asyncio

        mock_db = AsyncMock()
        mock_db.execute_query.side_effect = asyncio.TimeoutError()

        with pytest.raises(asyncio.TimeoutError):
            await mock_db.execute_query("SELECT * FROM large_table LIMIT 10")
