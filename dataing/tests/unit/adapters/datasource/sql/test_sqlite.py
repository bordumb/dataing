"""Unit tests for SQLite adapter."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from dataing.adapters.datasource.sql.sqlite import (
    SQLiteAdapter,
    SQLITE_CONFIG_SCHEMA,
    SQLITE_CAPABILITIES,
)
from dataing.adapters.datasource.types import (
    NormalizedType,
    QueryLanguage,
    SchemaFilter,
    SourceType,
)


@pytest.fixture
def sample_db():
    """Create a temporary SQLite database with sample data."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            age INTEGER,
            created_at DATETIME
        )
    """)
    conn.execute("""
        INSERT INTO users (name, email, age, created_at)
        VALUES
            ('Alice', 'alice@example.com', 30, '2024-01-01'),
            ('Bob', 'bob@example.com', 25, '2024-01-02'),
            ('Charlie', NULL, 35, '2024-01-03')
    """)
    conn.execute("""
        CREATE VIEW active_users AS
        SELECT * FROM users WHERE age < 35
    """)
    conn.commit()
    conn.close()

    yield db_path

    Path(db_path).unlink(missing_ok=True)


class TestSQLiteAdapterConfig:
    """Tests for SQLiteAdapter configuration schema."""

    def test_config_schema_field_groups(self) -> None:
        """Test config schema has expected field groups."""
        groups = {fg.id: fg for fg in SQLITE_CONFIG_SCHEMA.field_groups}

        assert "connection" in groups
        assert groups["connection"].collapsed_by_default is False

    def test_config_schema_connection_fields(self) -> None:
        """Test config schema has required connection fields."""
        fields = {f.name: f for f in SQLITE_CONFIG_SCHEMA.fields}

        assert "path" in fields
        assert fields["path"].required is True
        assert fields["path"].group == "connection"

        assert "read_only" in fields
        assert fields["read_only"].default_value is True
        assert fields["read_only"].required is False


class TestSQLiteCapabilities:
    """Tests for SQLiteAdapter capabilities."""

    def test_capabilities_values(self) -> None:
        """Test capability values are correct."""
        assert SQLITE_CAPABILITIES.supports_sql is True
        assert SQLITE_CAPABILITIES.supports_sampling is True
        assert SQLITE_CAPABILITIES.supports_row_count is True
        assert SQLITE_CAPABILITIES.supports_column_stats is True
        assert SQLITE_CAPABILITIES.supports_preview is True
        assert SQLITE_CAPABILITIES.supports_write is False
        assert SQLITE_CAPABILITIES.query_language == QueryLanguage.SQL
        assert SQLITE_CAPABILITIES.max_concurrent_queries == 1


class TestSQLiteAdapter:
    """Tests for SQLiteAdapter."""

    async def test_source_type(self, sample_db: str) -> None:
        """Test source_type property."""
        adapter = SQLiteAdapter({"path": sample_db})
        assert adapter.source_type == SourceType.SQLITE

    async def test_capabilities(self, sample_db: str) -> None:
        """Test capabilities property."""
        adapter = SQLiteAdapter({"path": sample_db})
        assert adapter.capabilities == SQLITE_CAPABILITIES

    async def test_connect_success(self, sample_db: str) -> None:
        """Test successful connection."""
        adapter = SQLiteAdapter({"path": sample_db})
        await adapter.connect()
        assert adapter.is_connected
        await adapter.disconnect()
        assert not adapter.is_connected

    async def test_connect_file_not_found(self) -> None:
        """Test connection failure when file doesn't exist."""
        from dataing.adapters.datasource.errors import ConnectionFailedError

        adapter = SQLiteAdapter({"path": "/nonexistent/path.sqlite"})
        with pytest.raises(ConnectionFailedError) as exc_info:
            await adapter.connect()
        assert "not found" in str(exc_info.value).lower()

    async def test_test_connection(self, sample_db: str) -> None:
        """Test connection test returns version."""
        adapter = SQLiteAdapter({"path": sample_db})
        result = await adapter.test_connection()
        assert result.success
        assert "SQLite" in (result.server_version or "")
        await adapter.disconnect()

    async def test_test_connection_not_connected(self, sample_db: str) -> None:
        """Test test_connection auto-connects."""
        adapter = SQLiteAdapter({"path": sample_db})
        assert not adapter.is_connected
        result = await adapter.test_connection()
        assert result.success
        assert adapter.is_connected
        await adapter.disconnect()

    async def test_execute_query(self, sample_db: str) -> None:
        """Test query execution."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.execute_query("SELECT * FROM users ORDER BY id")
            assert result.row_count == 3
            assert result.rows[0]["name"] == "Alice"

    async def test_execute_query_with_limit(self, sample_db: str) -> None:
        """Test query execution with limit."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.execute_query(
                "SELECT * FROM users ORDER BY id",
                limit=2,
            )
            assert result.row_count == 2
            assert result.truncated is True

    async def test_execute_query_empty_result(self, sample_db: str) -> None:
        """Test query with no results."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.execute_query(
                "SELECT * FROM users WHERE age > 100"
            )
            assert result.row_count == 0
            assert result.rows == []

    async def test_execute_query_syntax_error(self, sample_db: str) -> None:
        """Test query syntax error handling."""
        from dataing.adapters.datasource.errors import QuerySyntaxError

        async with SQLiteAdapter({"path": sample_db}) as adapter:
            with pytest.raises(QuerySyntaxError):
                await adapter.execute_query("SELCT * FROM users")

    async def test_execute_query_not_connected(self, sample_db: str) -> None:
        """Test query fails when not connected."""
        from dataing.adapters.datasource.errors import ConnectionFailedError

        adapter = SQLiteAdapter({"path": sample_db})
        with pytest.raises(ConnectionFailedError):
            await adapter.execute_query("SELECT 1")

    async def test_get_schema(self, sample_db: str) -> None:
        """Test schema discovery."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema()

            assert schema.source_type == SourceType.SQLITE
            assert len(schema.catalogs) == 1
            assert len(schema.catalogs[0].schemas) == 1

            tables = schema.get_all_tables()
            table_names = [t.name for t in tables]
            assert "users" in table_names
            assert "active_users" in table_names

            users_table = next(t for t in tables if t.name == "users")
            col_names = [c.name for c in users_table.columns]
            assert "id" in col_names
            assert "name" in col_names
            assert "email" in col_names

            id_col = next(c for c in users_table.columns if c.name == "id")
            assert id_col.is_primary_key

    async def test_get_schema_exclude_views(self, sample_db: str) -> None:
        """Test schema discovery with views excluded."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema(
                filter=SchemaFilter(include_views=False)
            )

            tables = schema.get_all_tables()
            table_names = [t.name for t in tables]
            assert "users" in table_names
            assert "active_users" not in table_names

    async def test_get_schema_table_pattern(self, sample_db: str) -> None:
        """Test schema discovery with table pattern filter."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema(
                filter=SchemaFilter(table_pattern="user%")
            )

            tables = schema.get_all_tables()
            table_names = [t.name for t in tables]
            assert "users" in table_names
            assert "active_users" not in table_names

    async def test_get_schema_max_tables(self, sample_db: str) -> None:
        """Test schema discovery with max tables limit."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema(
                filter=SchemaFilter(max_tables=1)
            )

            tables = schema.get_all_tables()
            assert len(tables) == 1

    async def test_get_schema_not_connected(self, sample_db: str) -> None:
        """Test get_schema fails when not connected."""
        from dataing.adapters.datasource.errors import ConnectionFailedError

        adapter = SQLiteAdapter({"path": sample_db})
        with pytest.raises(ConnectionFailedError):
            await adapter.get_schema()

    async def test_count_rows(self, sample_db: str) -> None:
        """Test row counting."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            count = await adapter.count_rows("users")
            assert count == 3

    async def test_sample(self, sample_db: str) -> None:
        """Test sampling."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.sample("users", n=2)
            assert result.row_count == 2

    async def test_preview(self, sample_db: str) -> None:
        """Test preview."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.preview("users", n=2)
            assert result.row_count == 2

    async def test_get_column_stats(self, sample_db: str) -> None:
        """Test column statistics."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            stats = await adapter.get_column_stats("users", ["email", "age"])

            assert "email" in stats
            assert stats["email"]["null_count"] == 1
            assert stats["email"]["distinct_count"] == 2

            assert "age" in stats
            assert stats["age"]["null_count"] == 0

    async def test_read_only_mode(self, sample_db: str) -> None:
        """Test read-only mode prevents writes."""
        async with SQLiteAdapter({"path": sample_db, "read_only": True}) as adapter:
            result = await adapter.execute_query("SELECT * FROM users")
            assert result.row_count == 3

            with pytest.raises(Exception):
                await adapter.execute_query(
                    "INSERT INTO users (name) VALUES ('Test')"
                )

    async def test_context_manager(self, sample_db: str) -> None:
        """Test async context manager."""
        adapter = SQLiteAdapter({"path": sample_db})
        assert not adapter.is_connected
        async with adapter:
            assert adapter.is_connected
        assert not adapter.is_connected

    async def test_type_normalization(self, sample_db: str) -> None:
        """Test type normalization in schema."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema()
            users_table = next(
                t for t in schema.get_all_tables() if t.name == "users"
            )

            id_col = next(c for c in users_table.columns if c.name == "id")
            assert id_col.data_type == NormalizedType.INTEGER

            name_col = next(c for c in users_table.columns if c.name == "name")
            assert name_col.data_type == NormalizedType.STRING

            created_col = next(
                c for c in users_table.columns if c.name == "created_at"
            )
            assert created_col.data_type == NormalizedType.DATETIME

    async def test_column_nullability(self, sample_db: str) -> None:
        """Test column nullability is correctly detected."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema()
            users_table = next(
                t for t in schema.get_all_tables() if t.name == "users"
            )

            name_col = next(c for c in users_table.columns if c.name == "name")
            assert name_col.nullable is False

            email_col = next(c for c in users_table.columns if c.name == "email")
            assert email_col.nullable is True


class TestSQLiteAdapterURI:
    """Tests for SQLite URI building."""

    def test_build_uri_default(self) -> None:
        """Test URI with default values."""
        adapter = SQLiteAdapter({"path": "/tmp/test.sqlite"})
        uri = adapter._build_uri()

        assert uri.startswith("file:")
        assert "/tmp/test.sqlite" in uri
        assert "mode=ro" in uri

    def test_build_uri_read_write(self) -> None:
        """Test URI with read_only=False."""
        adapter = SQLiteAdapter({"path": "/tmp/test.sqlite", "read_only": False})
        uri = adapter._build_uri()

        assert uri.startswith("file:")
        assert "/tmp/test.sqlite" in uri
        assert "mode=ro" not in uri

    def test_build_uri_already_file_uri(self) -> None:
        """Test that existing file: URI is passed through."""
        adapter = SQLiteAdapter({"path": "file:/tmp/test.sqlite?mode=rwc"})
        uri = adapter._build_uri()

        assert uri == "file:/tmp/test.sqlite?mode=rwc"


class TestSQLiteAdapterSampling:
    """Tests for SQLite sampling query."""

    def test_build_sample_query(self) -> None:
        """Test sample query uses SQLite-specific syntax."""
        adapter = SQLiteAdapter({"path": ":memory:"})
        query = adapter._build_sample_query("users", 100)

        assert "SELECT * FROM users" in query
        assert "ORDER BY RANDOM()" in query
        assert "LIMIT 100" in query


class TestSQLiteAdapterInMemory:
    """Tests for SQLite in-memory database."""

    async def test_memory_database(self) -> None:
        """Test connecting to in-memory database."""
        adapter = SQLiteAdapter({"path": ":memory:", "read_only": False})
        await adapter.connect()
        assert adapter.is_connected

        result = await adapter.execute_query("SELECT sqlite_version()")
        assert result.row_count == 1

        await adapter.disconnect()
        assert not adapter.is_connected

    async def test_memory_database_create_table(self) -> None:
        """Test creating tables in in-memory database."""
        async with SQLiteAdapter(
            {"path": ":memory:", "read_only": False}
        ) as adapter:
            await adapter.execute_query(
                "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)"
            )
            await adapter.execute_query(
                "INSERT INTO test (name) VALUES ('Alice'), ('Bob')"
            )

            result = await adapter.execute_query("SELECT * FROM test")
            assert result.row_count == 2
