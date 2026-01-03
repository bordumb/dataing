"""Unit tests for TrinoAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dataing.adapters.db.trino import TrinoAdapter


class TestTrinoAdapter:
    """Tests for TrinoAdapter."""

    @pytest.fixture
    def adapter(self) -> TrinoAdapter:
        """Return a TrinoAdapter instance."""
        return TrinoAdapter(
            host="localhost",
            port=8080,
            catalog="hive",
            schema="default",
            user="test_user",
        )

    def test_init(self, adapter: TrinoAdapter) -> None:
        """Test adapter initialization."""
        assert adapter.host == "localhost"
        assert adapter.port == 8080
        assert adapter.catalog == "hive"
        assert adapter.schema == "default"
        assert adapter.user == "test_user"

    async def test_connect_is_noop(self, adapter: TrinoAdapter) -> None:
        """Test that connect is a no-op for Trino."""
        await adapter.connect()
        # Should not raise

    async def test_close_shuts_down_executor(self, adapter: TrinoAdapter) -> None:
        """Test that close shuts down the executor."""
        with patch.object(adapter._executor, "shutdown") as mock_shutdown:
            await adapter.close()
            mock_shutdown.assert_called_once_with(wait=True)

    def test_execute_sync_returns_query_result(self, adapter: TrinoAdapter) -> None:
        """Test that _execute_sync returns QueryResult."""
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "test")]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dataing.adapters.db.trino.connect", return_value=mock_conn):
            result = adapter._execute_sync("SELECT id, name FROM users")

        assert result.columns == ("id", "name")
        assert result.row_count == 1
        assert result.rows[0]["id"] == 1
        assert result.rows[0]["name"] == "test"
        mock_conn.close.assert_called_once()

    def test_execute_sync_handles_empty_result(self, adapter: TrinoAdapter) -> None:
        """Test that _execute_sync handles empty results."""
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dataing.adapters.db.trino.connect", return_value=mock_conn):
            result = adapter._execute_sync("SELECT * FROM empty")

        assert result.columns == ()
        assert result.rows == ()
        assert result.row_count == 0

    def test_fetch_schema_sync(self, adapter: TrinoAdapter) -> None:
        """Test that _fetch_schema_sync returns rows."""
        mock_cursor = MagicMock()
        mock_cursor.description = [
            ("table_schema",),
            ("table_name",),
            ("column_name",),
            ("data_type",),
        ]
        mock_cursor.fetchall.return_value = [
            ("default", "users", "id", "integer"),
            ("default", "users", "name", "varchar"),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dataing.adapters.db.trino.connect", return_value=mock_conn):
            result = adapter._fetch_schema_sync("SELECT * FROM information_schema.columns")

        assert len(result) == 2
        assert result[0]["table_schema"] == "default"
        assert result[0]["table_name"] == "users"
