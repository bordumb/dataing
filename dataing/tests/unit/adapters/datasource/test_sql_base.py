"""Tests for SQLAdapter base class."""

import pytest
from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock

from dataing.adapters.datasource.sql.base import SQLAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    ConnectionTestResult,
    QueryLanguage,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceType,
)


class ConcreteSQLAdapter(SQLAdapter):
    """Concrete implementation for testing SQLAdapter."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._query_results: list[QueryResult] = []
        self._query_index = 0

    @property
    def source_type(self) -> SourceType:
        return SourceType.POSTGRESQL

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            success=True,
            latency_ms=10,
            message="Connected",
        )

    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        return self._build_schema_response(
            source_id="test",
            catalogs=[],
        )

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Return mock results or configured results."""
        if self._query_results:
            result = self._query_results[self._query_index % len(self._query_results)]
            self._query_index += 1
            return result
        return QueryResult(
            columns=[{"name": "cnt", "data_type": "integer"}],
            rows=[{"cnt": 100}],
            row_count=1,
        )

    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        return []

    def set_query_results(self, results: list[QueryResult]) -> None:
        """Set mock query results for testing."""
        self._query_results = results
        self._query_index = 0


class TestSQLAdapterCapabilities:
    """Tests for SQLAdapter default capabilities."""

    def test_default_capabilities(self):
        """Test default capability values."""
        adapter = ConcreteSQLAdapter({})
        caps = adapter.capabilities

        assert caps.supports_sql is True
        assert caps.supports_sampling is True
        assert caps.supports_row_count is True
        assert caps.supports_column_stats is True
        assert caps.supports_preview is True
        assert caps.supports_write is False
        assert caps.query_language == QueryLanguage.SQL
        assert caps.max_concurrent_queries == 10


class TestSQLAdapterSample:
    """Tests for SQLAdapter.sample method."""

    @pytest.mark.asyncio
    async def test_sample_without_schema(self):
        """Test sampling from table without schema prefix."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()

        # Mock execute_query to capture the SQL
        captured_sql = []
        original_execute = adapter.execute_query

        async def capture_execute(sql, **kwargs):
            captured_sql.append(sql)
            return await original_execute(sql, **kwargs)

        adapter.execute_query = capture_execute

        await adapter.sample("users", n=50)

        assert len(captured_sql) == 1
        assert "users" in captured_sql[0]
        assert "50" in captured_sql[0]

    @pytest.mark.asyncio
    async def test_sample_with_schema(self):
        """Test sampling from table with schema prefix."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()

        captured_sql = []
        original_execute = adapter.execute_query

        async def capture_execute(sql, **kwargs):
            captured_sql.append(sql)
            return await original_execute(sql, **kwargs)

        adapter.execute_query = capture_execute

        await adapter.sample("users", n=100, schema="public")

        assert len(captured_sql) == 1
        assert "public.users" in captured_sql[0]


class TestSQLAdapterPreview:
    """Tests for SQLAdapter.preview method."""

    @pytest.mark.asyncio
    async def test_preview_without_schema(self):
        """Test preview from table without schema prefix."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()

        captured_sql = []
        original_execute = adapter.execute_query

        async def capture_execute(sql, **kwargs):
            captured_sql.append(sql)
            return await original_execute(sql, **kwargs)

        adapter.execute_query = capture_execute

        await adapter.preview("orders", n=25)

        assert len(captured_sql) == 1
        assert "SELECT * FROM orders LIMIT 25" in captured_sql[0]

    @pytest.mark.asyncio
    async def test_preview_with_schema(self):
        """Test preview from table with schema prefix."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()

        captured_sql = []
        original_execute = adapter.execute_query

        async def capture_execute(sql, **kwargs):
            captured_sql.append(sql)
            return await original_execute(sql, **kwargs)

        adapter.execute_query = capture_execute

        await adapter.preview("orders", n=50, schema="sales")

        assert len(captured_sql) == 1
        assert "SELECT * FROM sales.orders LIMIT 50" in captured_sql[0]


class TestSQLAdapterCountRows:
    """Tests for SQLAdapter.count_rows method."""

    @pytest.mark.asyncio
    async def test_count_rows(self):
        """Test counting rows in a table."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()
        adapter.set_query_results([
            QueryResult(
                columns=[{"name": "cnt", "data_type": "integer"}],
                rows=[{"cnt": 5000}],
                row_count=1,
            )
        ])

        count = await adapter.count_rows("users")
        assert count == 5000

    @pytest.mark.asyncio
    async def test_count_rows_with_schema(self):
        """Test counting rows with schema prefix."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()

        captured_sql = []
        original_execute = adapter.execute_query

        async def capture_execute(sql, **kwargs):
            captured_sql.append(sql)
            return QueryResult(
                columns=[{"name": "cnt", "data_type": "integer"}],
                rows=[{"cnt": 100}],
                row_count=1,
            )

        adapter.execute_query = capture_execute

        await adapter.count_rows("orders", schema="analytics")

        assert "SELECT COUNT(*) as cnt FROM analytics.orders" in captured_sql[0]

    @pytest.mark.asyncio
    async def test_count_rows_empty_result(self):
        """Test count returns 0 for empty results."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()
        adapter.set_query_results([
            QueryResult(
                columns=[],
                rows=[],
                row_count=0,
            )
        ])

        count = await adapter.count_rows("empty_table")
        assert count == 0


class TestSQLAdapterBuildSampleQuery:
    """Tests for SQLAdapter._build_sample_query method."""

    def test_default_sample_query(self):
        """Test default sample query uses ORDER BY RANDOM()."""
        adapter = ConcreteSQLAdapter({})
        query = adapter._build_sample_query("users", 100)

        assert "SELECT * FROM users" in query
        assert "ORDER BY RANDOM()" in query
        assert "LIMIT 100" in query

    def test_sample_query_with_schema(self):
        """Test sample query with schema prefix."""
        adapter = ConcreteSQLAdapter({})
        query = adapter._build_sample_query("public.users", 50)

        assert "public.users" in query


class TestSQLAdapterGetColumnStats:
    """Tests for SQLAdapter.get_column_stats method."""

    @pytest.mark.asyncio
    async def test_get_column_stats_single_column(self):
        """Test getting stats for a single column."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()
        adapter.set_query_results([
            QueryResult(
                columns=[
                    {"name": "total_count", "data_type": "integer"},
                    {"name": "non_null_count", "data_type": "integer"},
                    {"name": "distinct_count", "data_type": "integer"},
                    {"name": "min_value", "data_type": "string"},
                    {"name": "max_value", "data_type": "string"},
                ],
                rows=[{
                    "total_count": 1000,
                    "non_null_count": 950,
                    "distinct_count": 100,
                    "min_value": "1",
                    "max_value": "100",
                }],
                row_count=1,
            )
        ])

        stats = await adapter.get_column_stats("users", ["age"])

        assert "age" in stats
        assert stats["age"]["null_count"] == 50
        assert stats["age"]["null_rate"] == 0.05
        assert stats["age"]["distinct_count"] == 100
        assert stats["age"]["min_value"] == "1"
        assert stats["age"]["max_value"] == "100"

    @pytest.mark.asyncio
    async def test_get_column_stats_multiple_columns(self):
        """Test getting stats for multiple columns."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()
        adapter.set_query_results([
            QueryResult(
                columns=[],
                rows=[{
                    "total_count": 100,
                    "non_null_count": 100,
                    "distinct_count": 10,
                    "min_value": "a",
                    "max_value": "z",
                }],
                row_count=1,
            ),
            QueryResult(
                columns=[],
                rows=[{
                    "total_count": 100,
                    "non_null_count": 80,
                    "distinct_count": 50,
                    "min_value": "0",
                    "max_value": "999",
                }],
                row_count=1,
            ),
        ])

        stats = await adapter.get_column_stats("users", ["name", "age"])

        assert "name" in stats
        assert "age" in stats

    @pytest.mark.asyncio
    async def test_get_column_stats_with_schema(self):
        """Test getting stats with schema prefix."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()

        captured_sql = []
        original_execute = adapter.execute_query

        async def capture_execute(sql, **kwargs):
            captured_sql.append(sql)
            return QueryResult(
                columns=[],
                rows=[{
                    "total_count": 100,
                    "non_null_count": 100,
                    "distinct_count": 10,
                    "min_value": "1",
                    "max_value": "10",
                }],
                row_count=1,
            )

        adapter.execute_query = capture_execute

        await adapter.get_column_stats("orders", ["amount"], schema="sales")

        assert any("sales.orders" in sql for sql in captured_sql)

    @pytest.mark.asyncio
    async def test_get_column_stats_error_handling(self):
        """Test that errors are handled gracefully."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()

        # Make execute_query raise an exception
        async def failing_execute(sql, **kwargs):
            raise Exception("Query failed")

        adapter.execute_query = failing_execute

        stats = await adapter.get_column_stats("users", ["broken_column"])

        assert "broken_column" in stats
        assert stats["broken_column"]["null_count"] == 0
        assert stats["broken_column"]["null_rate"] == 0.0
        assert stats["broken_column"]["distinct_count"] is None

    @pytest.mark.asyncio
    async def test_get_column_stats_zero_rows(self):
        """Test stats calculation when table has zero rows."""
        adapter = ConcreteSQLAdapter({})
        await adapter.connect()
        adapter.set_query_results([
            QueryResult(
                columns=[],
                rows=[{
                    "total_count": 0,
                    "non_null_count": 0,
                    "distinct_count": 0,
                    "min_value": None,
                    "max_value": None,
                }],
                row_count=1,
            )
        ])

        stats = await adapter.get_column_stats("empty_table", ["col"])

        assert stats["col"]["null_count"] == 0
        assert stats["col"]["null_rate"] == 0.0


class TestSQLAdapterAbstractMethods:
    """Test that abstract methods must be implemented."""

    def test_cannot_instantiate_sql_adapter(self):
        """Test that SQLAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            SQLAdapter({})
        assert "abstract" in str(exc_info.value).lower()

    def test_incomplete_implementation_fails(self):
        """Test that incomplete implementations fail."""

        class IncompleteSQLAdapter(SQLAdapter):
            @property
            def source_type(self) -> SourceType:
                return SourceType.POSTGRESQL

        with pytest.raises(TypeError):
            IncompleteSQLAdapter({})
