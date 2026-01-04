"""Tests for PostgresAdapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from dataing.adapters.datasource.sql.postgres import (
    PostgresAdapter,
    POSTGRES_CONFIG_SCHEMA,
    POSTGRES_CAPABILITIES,
)
from dataing.adapters.datasource.errors import (
    AuthenticationFailedError,
    ConnectionFailedError,
    ConnectionTimeoutError,
    QuerySyntaxError,
    QueryTimeoutError,
    AccessDeniedError,
    SchemaFetchFailedError,
)
from dataing.adapters.datasource.types import (
    NormalizedType,
    QueryLanguage,
    SchemaFilter,
    SourceCategory,
    SourceType,
)


class TestPostgresAdapterConfig:
    """Tests for PostgresAdapter configuration schema."""

    def test_config_schema_field_groups(self):
        """Test config schema has expected field groups."""
        groups = {fg.id: fg for fg in POSTGRES_CONFIG_SCHEMA.field_groups}

        assert "connection" in groups
        assert "auth" in groups
        assert "ssl" in groups
        assert "advanced" in groups

        assert groups["ssl"].collapsed_by_default is True
        assert groups["advanced"].collapsed_by_default is True

    def test_config_schema_connection_fields(self):
        """Test config schema has required connection fields."""
        fields = {f.name: f for f in POSTGRES_CONFIG_SCHEMA.fields}

        assert "host" in fields
        assert fields["host"].required is True
        assert fields["host"].group == "connection"

        assert "port" in fields
        assert fields["port"].default_value == 5432
        assert fields["port"].min_value == 1
        assert fields["port"].max_value == 65535

        assert "database" in fields
        assert fields["database"].required is True

    def test_config_schema_auth_fields(self):
        """Test config schema has required auth fields."""
        fields = {f.name: f for f in POSTGRES_CONFIG_SCHEMA.fields}

        assert "username" in fields
        assert fields["username"].required is True
        assert fields["username"].group == "auth"

        assert "password" in fields
        assert fields["password"].type == "secret"

    def test_config_schema_ssl_field(self):
        """Test config schema has SSL options."""
        fields = {f.name: f for f in POSTGRES_CONFIG_SCHEMA.fields}

        assert "ssl_mode" in fields
        assert fields["ssl_mode"].type == "enum"
        assert fields["ssl_mode"].default_value == "prefer"

        options = [opt["value"] for opt in fields["ssl_mode"].options]
        assert "disable" in options
        assert "require" in options
        assert "verify-full" in options


class TestPostgresCapabilities:
    """Tests for PostgresAdapter capabilities."""

    def test_capabilities_values(self):
        """Test capability values are correct."""
        assert POSTGRES_CAPABILITIES.supports_sql is True
        assert POSTGRES_CAPABILITIES.supports_sampling is True
        assert POSTGRES_CAPABILITIES.supports_row_count is True
        assert POSTGRES_CAPABILITIES.supports_column_stats is True
        assert POSTGRES_CAPABILITIES.supports_preview is True
        assert POSTGRES_CAPABILITIES.supports_write is False
        assert POSTGRES_CAPABILITIES.query_language == QueryLanguage.SQL
        assert POSTGRES_CAPABILITIES.max_concurrent_queries == 10


class TestPostgresAdapterInit:
    """Tests for PostgresAdapter initialization."""

    def test_init_with_config(self):
        """Test adapter initializes with config."""
        config = {
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "username": "user",
            "password": "pass",
        }
        adapter = PostgresAdapter(config)

        assert adapter._config == config
        assert adapter._pool is None
        assert adapter._connected is False

    def test_source_type(self):
        """Test source_type property."""
        adapter = PostgresAdapter({})
        assert adapter.source_type == SourceType.POSTGRESQL

    def test_capabilities(self):
        """Test capabilities property."""
        adapter = PostgresAdapter({})
        assert adapter.capabilities == POSTGRES_CAPABILITIES


class TestPostgresAdapterDSN:
    """Tests for DSN building."""

    def test_build_dsn_default(self):
        """Test DSN with default values."""
        adapter = PostgresAdapter({})
        dsn = adapter._build_dsn()

        assert "postgresql://" in dsn
        assert "localhost" in dsn
        assert "5432" in dsn
        assert "postgres" in dsn
        assert "sslmode=prefer" in dsn

    def test_build_dsn_custom(self):
        """Test DSN with custom values."""
        config = {
            "host": "db.example.com",
            "port": 5433,
            "database": "mydb",
            "username": "admin",
            "password": "secret123",
            "ssl_mode": "require",
        }
        adapter = PostgresAdapter(config)
        dsn = adapter._build_dsn()

        assert "db.example.com" in dsn
        assert "5433" in dsn
        assert "mydb" in dsn
        assert "admin" in dsn
        assert "secret123" in dsn
        assert "sslmode=require" in dsn


class TestPostgresAdapterConnect:
    """Tests for PostgresAdapter.connect method."""

    @pytest.mark.asyncio
    async def test_connect_import_error(self):
        """Test connect raises error when asyncpg not installed."""
        with patch.dict("sys.modules", {"asyncpg": None}):
            adapter = PostgresAdapter({})
            with pytest.raises(ConnectionFailedError) as exc_info:
                await adapter.connect()
            assert "asyncpg is not installed" in str(exc_info.value)



class TestPostgresAdapterDisconnect:
    """Tests for PostgresAdapter.disconnect method."""

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """Test disconnect when not connected."""
        adapter = PostgresAdapter({})
        await adapter.disconnect()
        assert adapter._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        """Test disconnect clears internal state."""
        adapter = PostgresAdapter({})
        adapter._connected = True
        mock_pool = AsyncMock()
        adapter._pool = mock_pool

        await adapter.disconnect()

        mock_pool.close.assert_called_once()
        assert adapter._pool is None
        assert adapter._connected is False


class TestPostgresAdapterTestConnection:
    """Tests for PostgresAdapter.test_connection method."""

    @pytest.mark.asyncio
    async def test_test_connection_when_not_connected(self):
        """Test test_connection attempts connection when not connected."""
        import sys

        mock_asyncpg = MagicMock()
        mock_asyncpg.create_pool = AsyncMock(side_effect=Exception("Connection refused"))

        with patch.dict(sys.modules, {"asyncpg": mock_asyncpg}):
            adapter = PostgresAdapter({})
            result = await adapter.test_connection()

            # Should fail because connection fails
            assert result.success is False
            assert result.error_code == "CONNECTION_FAILED"


class TestPostgresAdapterExecuteQuery:
    """Tests for PostgresAdapter.execute_query method."""

    @pytest.mark.asyncio
    async def test_execute_query_not_connected(self):
        """Test query fails when not connected."""
        adapter = PostgresAdapter({})
        with pytest.raises(ConnectionFailedError) as exc_info:
            await adapter.execute_query("SELECT 1")
        assert "Not connected" in str(exc_info.value)


class TestPostgresAdapterGetSchema:
    """Tests for PostgresAdapter.get_schema method."""

    @pytest.mark.asyncio
    async def test_get_schema_not_connected(self):
        """Test get_schema fails when not connected."""
        adapter = PostgresAdapter({})
        with pytest.raises(ConnectionFailedError):
            await adapter.get_schema()


class TestPostgresAdapterSampleQuery:
    """Tests for PostgresAdapter._build_sample_query method."""

    def test_sample_query_uses_tablesample(self):
        """Test sample query uses PostgreSQL TABLESAMPLE."""
        adapter = PostgresAdapter({})
        query = adapter._build_sample_query("users", 100)

        assert "SELECT * FROM users" in query
        assert "TABLESAMPLE SYSTEM" in query
        assert "LIMIT 100" in query
