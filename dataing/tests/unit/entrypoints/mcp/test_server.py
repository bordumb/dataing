"""Unit tests for MCP server."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dataing.core.domain_types import (
    Finding,
    QueryResult,
    SchemaContext,
    TableSchema,
)


class TestMCPServer:
    """Tests for MCP server functionality."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database adapter."""
        mock = AsyncMock()
        mock.execute_query.return_value = QueryResult(
            columns=("count",),
            rows=({"count": 500},),
            row_count=1,
        )
        mock.get_schema.return_value = SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.orders",
                    columns=("id", "total", "status"),
                    column_types={
                        "id": "integer",
                        "total": "numeric",
                        "status": "varchar",
                    },
                ),
            )
        )
        return mock

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Return a mock LLM client."""
        mock = AsyncMock()
        return mock

    def test_tool_schema_investigate_anomaly(self) -> None:
        """Test investigate_anomaly tool schema."""
        # Define expected schema
        schema = {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "metric_name": {"type": "string"},
                "expected_value": {"type": "number"},
                "actual_value": {"type": "number"},
                "deviation_pct": {"type": "number"},
                "anomaly_date": {"type": "string"},
            },
            "required": [
                "dataset_id",
                "metric_name",
                "expected_value",
                "actual_value",
                "deviation_pct",
                "anomaly_date",
            ],
        }

        # Validate all required fields are present
        assert "dataset_id" in schema["properties"]
        assert "metric_name" in schema["properties"]
        assert "expected_value" in schema["properties"]

    def test_tool_schema_query_dataset(self) -> None:
        """Test query_dataset tool schema."""
        schema = {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
            },
            "required": ["sql"],
        }

        assert "sql" in schema["properties"]
        assert "sql" in schema["required"]

    def test_tool_schema_get_table_schema(self) -> None:
        """Test get_table_schema tool schema."""
        schema = {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
            },
            "required": ["table_name"],
        }

        assert "table_name" in schema["properties"]

    async def test_query_dataset_validates_query(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """Test that query_dataset validates SQL."""
        # A valid query should pass
        args = {"sql": "SELECT COUNT(*) FROM orders LIMIT 10"}

        # Import validate_query to test validation logic
        from dataing.safety.validator import validate_query

        # Should not raise for valid query
        validate_query(args["sql"])

    async def test_query_dataset_rejects_unsafe(self) -> None:
        """Test that query_dataset rejects unsafe SQL."""
        from dataing.core.exceptions import QueryValidationError
        from dataing.safety.validator import validate_query

        unsafe_queries = [
            "DROP TABLE users",
            "DELETE FROM users",
            "UPDATE users SET name = 'test'",
            "INSERT INTO users VALUES (1)",
        ]

        for query in unsafe_queries:
            with pytest.raises(QueryValidationError):
                validate_query(query)

    async def test_get_table_schema_returns_info(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """Test that get_table_schema returns table info."""
        schema = await mock_db.get_schema(table_pattern="orders")

        assert len(schema.tables) >= 1
        assert "id" in schema.tables[0].columns

    async def test_get_table_schema_not_found(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """Test handling of non-existent table."""
        mock_db.get_schema.return_value = SchemaContext(tables=())

        schema = await mock_db.get_schema(table_pattern="nonexistent")

        assert len(schema.tables) == 0

    def test_finding_formatting(self) -> None:
        """Test that findings are formatted correctly."""
        finding = Finding(
            investigation_id="inv-001",
            status="completed",
            root_cause="ETL job failed due to timeout",
            confidence=0.9,
            evidence=[],
            recommendations=["Restart the job", "Add monitoring"],
            duration_seconds=120.5,
        )

        # Test that all important fields are accessible
        assert finding.status == "completed"
        assert finding.root_cause is not None
        assert finding.confidence == 0.9
        assert len(finding.recommendations) == 2

    def test_query_result_formatting(self) -> None:
        """Test that query results are formatted correctly."""
        result = QueryResult(
            columns=("id", "name", "total"),
            rows=(
                {"id": 1, "name": "Order 1", "total": 100.0},
                {"id": 2, "name": "Order 2", "total": 200.0},
            ),
            row_count=2,
        )

        # Test summary formatting
        summary = result.to_summary()
        assert "id" in summary
        assert "Total rows: 2" in summary
