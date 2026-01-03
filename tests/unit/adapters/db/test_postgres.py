"""Unit tests for PostgresAdapter."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataing.adapters.db.postgres import PostgresAdapter


class TestPostgresAdapter:
    """Tests for PostgresAdapter."""

    @pytest.fixture
    def adapter(self) -> PostgresAdapter:
        """Return a PostgresAdapter instance."""
        return PostgresAdapter(connection_string="postgresql://localhost:5432/test")

    @pytest.fixture
    def mock_conn(self) -> AsyncMock:
        """Return a mock connection."""
        return AsyncMock()

    @pytest.fixture
    def adapter_with_pool(self, mock_conn: AsyncMock) -> PostgresAdapter:
        """Return a PostgresAdapter with mocked pool."""
        adapter = PostgresAdapter(connection_string="postgresql://localhost:5432/test")

        mock_pool = MagicMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool.acquire = mock_acquire
        mock_pool.close = AsyncMock()
        adapter._pool = mock_pool
        return adapter

    def test_init(self, adapter: PostgresAdapter) -> None:
        """Test adapter initialization."""
        assert adapter.connection_string == "postgresql://localhost:5432/test"
        assert adapter._pool is None

    async def test_connect_creates_pool(self, adapter: PostgresAdapter) -> None:
        """Test that connect creates a connection pool."""
        mock_pool = MagicMock()

        async def mock_create_pool(*args, **kwargs):
            return mock_pool

        with patch("dataing.adapters.db.postgres.asyncpg.create_pool", side_effect=mock_create_pool):
            await adapter.connect()

            assert adapter._pool == mock_pool

    async def test_close_closes_pool(self, adapter: PostgresAdapter) -> None:
        """Test that close closes the connection pool."""
        mock_pool = AsyncMock()
        adapter._pool = mock_pool

        await adapter.close()

        mock_pool.close.assert_called_once()
        assert adapter._pool is None

    async def test_close_noop_when_no_pool(self, adapter: PostgresAdapter) -> None:
        """Test that close is a no-op when pool doesn't exist."""
        await adapter.close()  # Should not raise

    async def test_execute_query_raises_without_pool(
        self,
        adapter: PostgresAdapter,
    ) -> None:
        """Test that execute_query raises when pool not initialized."""
        with pytest.raises(RuntimeError) as exc_info:
            await adapter.execute_query("SELECT 1")

        assert "Connection pool not initialized" in str(exc_info.value)

    async def test_execute_query_returns_result(
        self,
        adapter_with_pool: PostgresAdapter,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that execute_query returns QueryResult."""
        # Create mock rows with dict-like behavior and keys() method
        mock_row = MagicMock()
        mock_row.keys.return_value = ["id", "name"]
        mock_row.__getitem__ = lambda self, key: {"id": 1, "name": "test"}[key]
        mock_row.__iter__ = lambda self: iter(["id", "name"])
        mock_rows = [mock_row]

        async def mock_fetch(sql):
            return mock_rows

        mock_conn.fetch = mock_fetch

        result = await adapter_with_pool.execute_query("SELECT id, name FROM users")

        assert result.row_count == 1
        assert result.columns == ("id", "name")

    async def test_execute_query_handles_empty_result(
        self,
        adapter_with_pool: PostgresAdapter,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that execute_query handles empty result."""
        async def mock_fetch(sql):
            return []

        mock_conn.fetch = mock_fetch

        result = await adapter_with_pool.execute_query("SELECT * FROM empty_table")

        assert result.columns == ()
        assert result.rows == ()
        assert result.row_count == 0

    async def test_get_schema_raises_without_pool(
        self,
        adapter: PostgresAdapter,
    ) -> None:
        """Test that get_schema raises when pool not initialized."""
        with pytest.raises(RuntimeError) as exc_info:
            await adapter.get_schema()

        assert "Connection pool not initialized" in str(exc_info.value)

    async def test_get_schema_returns_schema_context(
        self,
        adapter_with_pool: PostgresAdapter,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that get_schema returns SchemaContext."""
        mock_rows = [
            {
                "table_schema": "public",
                "table_name": "users",
                "column_name": "id",
                "data_type": "integer",
            },
            {
                "table_schema": "public",
                "table_name": "users",
                "column_name": "email",
                "data_type": "varchar",
            },
        ]

        async def mock_fetch(sql):
            return mock_rows

        mock_conn.fetch = mock_fetch

        schema = await adapter_with_pool.get_schema()

        assert len(schema.tables) == 1
        assert schema.tables[0].table_name == "public.users"
        assert "id" in schema.tables[0].columns
        assert "email" in schema.tables[0].columns

    async def test_get_schema_with_table_pattern(
        self,
        adapter_with_pool: PostgresAdapter,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that get_schema filters by pattern."""
        mock_rows = [
            {
                "table_schema": "public",
                "table_name": "users",
                "column_name": "id",
                "data_type": "integer",
            },
            {
                "table_schema": "public",
                "table_name": "orders",
                "column_name": "id",
                "data_type": "integer",
            },
        ]

        async def mock_fetch(sql):
            return mock_rows

        mock_conn.fetch = mock_fetch

        schema = await adapter_with_pool.get_schema(table_pattern="users")

        assert len(schema.tables) == 1
        assert schema.tables[0].table_name == "public.users"
