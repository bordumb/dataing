"""Unit tests for MockDatabaseAdapter."""

from __future__ import annotations

import pytest

from dataing.adapters.db.mock import MockDatabaseAdapter
from dataing.core.domain_types import QueryResult, SchemaContext, TableSchema


class TestMockDatabaseAdapter:
    """Tests for MockDatabaseAdapter."""

    @pytest.fixture
    def adapter(self) -> MockDatabaseAdapter:
        """Return a mock database adapter."""
        return MockDatabaseAdapter()

    @pytest.fixture
    def custom_schema(self) -> SchemaContext:
        """Return a custom schema."""
        return SchemaContext(
            tables=(
                TableSchema(
                    table_name="custom.table",
                    columns=("id", "name"),
                    column_types={"id": "integer", "name": "varchar"},
                ),
            )
        )

    async def test_connect_noop(self, adapter: MockDatabaseAdapter) -> None:
        """Test that connect is a no-op."""
        await adapter.connect()
        # Should not raise

    async def test_close_noop(self, adapter: MockDatabaseAdapter) -> None:
        """Test that close is a no-op."""
        await adapter.close()
        # Should not raise

    async def test_execute_query_returns_empty_by_default(
        self,
        adapter: MockDatabaseAdapter,
    ) -> None:
        """Test that execute_query returns empty result by default."""
        result = await adapter.execute_query("SELECT * FROM unknown")

        assert result.columns == ()
        assert result.rows == ()
        assert result.row_count == 0

    async def test_execute_query_logs_queries(
        self,
        adapter: MockDatabaseAdapter,
    ) -> None:
        """Test that execute_query logs executed queries."""
        await adapter.execute_query("SELECT 1")
        await adapter.execute_query("SELECT 2")

        assert len(adapter.executed_queries) == 2
        assert "SELECT 1" in adapter.executed_queries
        assert "SELECT 2" in adapter.executed_queries

    async def test_execute_query_matches_pattern(
        self,
        adapter: MockDatabaseAdapter,
    ) -> None:
        """Test that execute_query matches patterns case-insensitively."""
        expected_result = QueryResult(
            columns=("count",),
            rows=({"count": 42},),
            row_count=1,
        )
        adapter.add_response("users", expected_result)

        result = await adapter.execute_query("SELECT COUNT(*) FROM USERS")

        assert result.row_count == 1
        assert result.rows[0]["count"] == 42

    async def test_get_schema_returns_default(
        self,
        adapter: MockDatabaseAdapter,
    ) -> None:
        """Test that get_schema returns default schema."""
        schema = await adapter.get_schema()

        assert len(schema.tables) == 3
        table_names = [t.table_name for t in schema.tables]
        assert "public.users" in table_names
        assert "public.orders" in table_names
        assert "public.products" in table_names

    async def test_get_schema_with_custom_schema(
        self,
        custom_schema: SchemaContext,
    ) -> None:
        """Test that get_schema returns custom schema when provided."""
        adapter = MockDatabaseAdapter(schema=custom_schema)

        schema = await adapter.get_schema()

        assert len(schema.tables) == 1
        assert schema.tables[0].table_name == "custom.table"

    async def test_get_schema_with_pattern_filter(
        self,
        adapter: MockDatabaseAdapter,
    ) -> None:
        """Test that get_schema filters by pattern."""
        schema = await adapter.get_schema(table_pattern="orders")

        assert len(schema.tables) == 1
        assert schema.tables[0].table_name == "public.orders"

    def test_add_response(self, adapter: MockDatabaseAdapter) -> None:
        """Test that add_response adds a canned response."""
        result = QueryResult(
            columns=("value",),
            rows=({"value": "test"},),
            row_count=1,
        )
        adapter.add_response("test_pattern", result)

        assert "test_pattern" in adapter.responses

    def test_add_row_count_response(self, adapter: MockDatabaseAdapter) -> None:
        """Test that add_row_count_response adds a count response."""
        adapter.add_row_count_response("COUNT(*)", 100)

        assert "COUNT(*)" in adapter.responses
        assert adapter.responses["COUNT(*)"].row_count == 1
        assert adapter.responses["COUNT(*)"].rows[0]["count"] == 100

    def test_clear_queries(self, adapter: MockDatabaseAdapter) -> None:
        """Test that clear_queries clears the log."""
        adapter.executed_queries = ["SELECT 1", "SELECT 2"]

        adapter.clear_queries()

        assert adapter.executed_queries == []

    def test_get_query_count(self, adapter: MockDatabaseAdapter) -> None:
        """Test that get_query_count returns correct count."""
        adapter.executed_queries = ["SELECT 1", "SELECT 2", "SELECT 3"]

        assert adapter.get_query_count() == 3

    def test_was_query_executed_true(self, adapter: MockDatabaseAdapter) -> None:
        """Test was_query_executed returns True when pattern matches."""
        adapter.executed_queries = ["SELECT * FROM users WHERE id = 1"]

        assert adapter.was_query_executed("users")
        assert adapter.was_query_executed("USERS")  # case-insensitive
        assert adapter.was_query_executed("id = 1")

    def test_was_query_executed_false(self, adapter: MockDatabaseAdapter) -> None:
        """Test was_query_executed returns False when pattern doesn't match."""
        adapter.executed_queries = ["SELECT * FROM users"]

        assert not adapter.was_query_executed("orders")
        assert not adapter.was_query_executed("DELETE")
