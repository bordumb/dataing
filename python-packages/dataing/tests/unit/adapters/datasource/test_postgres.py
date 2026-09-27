"""Tests for PostgresAdapter."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncpg import connect_utils

from dataing.adapters.datasource.errors import (
    ConnectionFailedError,
)
from dataing.adapters.datasource.sql.postgres import (
    POSTGRES_CAPABILITIES,
    POSTGRES_CONFIG_SCHEMA,
    PostgresAdapter,
)
from dataing.adapters.datasource.types import (
    QueryLanguage,
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

        options = [opt.value for opt in fields["ssl_mode"].options]
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


TENANT_CONFIG: dict[str, Any] = {
    "host": "db.internal",
    "port": 5433,
    "database": "analytics",
    "username": "analyst",
    "password": "s3cret",
    "ssl_mode": "require",
}

# The API server's own libpq settings, which tenant connections must never inherit.
SERVER_PG_ENV = {
    "PGHOST": "10.0.0.1",
    "PGPORT": "6543",
    "PGDATABASE": "app",
    "PGUSER": "app_owner",
    "PGPASSWORD": "server-secret",
    "PGSSLMODE": "disable",
}


async def _resolve_connect_target(config: dict[str, Any]) -> tuple[Any, Any]:
    """Run connect() against a patched pool and resolve its arguments as asyncpg does."""
    with patch("asyncpg.create_pool", new_callable=AsyncMock) as create_pool:
        await PostgresAdapter(config).connect()

    args, kwargs = create_pool.call_args
    return connect_utils._parse_connect_dsn_and_args(
        dsn=args[0] if args else kwargs.get("dsn"),
        host=kwargs.get("host"),
        port=kwargs.get("port"),
        user=kwargs.get("user"),
        password=kwargs.get("password"),
        passfile=kwargs.get("passfile"),
        database=kwargs.get("database"),
        ssl=kwargs.get("ssl"),
        service=None,
        servicefile=None,
        direct_tls=None,
        server_settings=None,
        target_session_attrs=None,
        krbsrvname=None,
        gsslib=None,
    )


class TestPostgresAdapterConnectTarget:
    """Tests for the address and credentials asyncpg resolves from connect()."""

    @pytest.fixture(autouse=True)
    def no_pg_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Clear PG* variables so only the adapter's arguments drive resolution."""
        for name in list(os.environ):
            if name.startswith("PG"):
                monkeypatch.delenv(name)

    @pytest.fixture
    def server_pg_env(self, no_pg_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Give the server its own PG* settings for tenant connections to ignore."""
        for name, value in SERVER_PG_ENV.items():
            monkeypatch.setenv(name, value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "password",
        [
            "x@169.254.169.254:80/db?sslmode=disable#",
            "p a+ss%40w@rd:/?#",
        ],
    )
    async def test_password_reaches_configured_host_verbatim(self, password: str) -> None:
        """URL metacharacters in a password never alter it, the address, or the TLS mode."""
        addrs, params = await _resolve_connect_target({**TENANT_CONFIG, "password": password})

        assert addrs == [("db.internal", 5433)]
        assert params.password == password
        assert params.user == "analyst"
        assert params.database == "analytics"
        assert params.sslmode == connect_utils.SSLMode.require

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("server_pg_env")
    @pytest.mark.parametrize("unset", [None, ""])
    async def test_blank_credentials_never_use_server_credentials(self, unset: str | None) -> None:
        """A blank username or password never picks up the server's PGUSER or PGPASSWORD."""
        addrs, params = await _resolve_connect_target(
            {**TENANT_CONFIG, "username": unset, "password": unset}
        )

        assert addrs == [("db.internal", 5433)]
        assert (params.user, params.password) == ("", "")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("unset", [None, ""])
    async def test_blank_password_never_reads_server_passfile(
        self, unset: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A blank password never falls back to a matching entry in the server's pgpass."""
        passfile = tmp_path / "pgpass"
        passfile.write_text("*:*:*:*:pgpass-secret\n")
        passfile.chmod(0o600)
        monkeypatch.setenv("PGPASSFILE", str(passfile))

        _, params = await _resolve_connect_target({**TENANT_CONFIG, "password": unset})

        assert params.password == ""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("server_pg_env")
    @pytest.mark.parametrize("unset", [None, ""])
    async def test_unset_connection_settings_use_adapter_defaults(self, unset: str | None) -> None:
        """Unset host, port, database, or SSL mode never falls back to the server's PG*."""
        unset_settings = dict.fromkeys(("host", "port", "database", "ssl_mode"), unset)

        addrs, params = await _resolve_connect_target({**TENANT_CONFIG, **unset_settings})

        assert addrs == [("localhost", 5432)]
        assert params.database == "postgres"
        assert params.sslmode == connect_utils.SSLMode.prefer


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
