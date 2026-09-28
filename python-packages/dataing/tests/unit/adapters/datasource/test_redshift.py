"""Tests for RedshiftAdapter."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from asyncpg import connect_utils

from dataing.adapters.datasource.sql.redshift import RedshiftAdapter

TENANT_CONFIG: dict[str, Any] = {
    "host": "warehouse.internal",
    "port": 5439,
    "database": "dev",
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
        await RedshiftAdapter(config).connect()

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


class TestRedshiftAdapterConnectTarget:
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

    @pytest.mark.parametrize(
        "password",
        [
            "x@169.254.169.254:80/dev?sslmode=disable#",
            "p a+ss%40w@rd:/?#",
        ],
    )
    async def test_password_reaches_configured_host_verbatim(self, password: str) -> None:
        """URL metacharacters in a password never alter it, the address, or the TLS mode."""
        addrs, params = await _resolve_connect_target({**TENANT_CONFIG, "password": password})

        assert addrs == [("warehouse.internal", 5439)]
        assert params.password == password
        assert params.user == "analyst"
        assert params.database == "dev"
        assert params.sslmode == connect_utils.SSLMode.require

    @pytest.mark.usefixtures("server_pg_env")
    @pytest.mark.parametrize("unset", [None, ""])
    async def test_blank_credentials_never_use_server_credentials(self, unset: str | None) -> None:
        """A blank username or password never picks up the server's PGUSER or PGPASSWORD."""
        addrs, params = await _resolve_connect_target(
            {**TENANT_CONFIG, "username": unset, "password": unset}
        )

        assert addrs == [("warehouse.internal", 5439)]
        assert (params.user, params.password) == ("", "")

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

    @pytest.mark.usefixtures("server_pg_env")
    @pytest.mark.parametrize("unset", [None, ""])
    async def test_unset_connection_settings_use_adapter_defaults(self, unset: str | None) -> None:
        """Unset host, port, database, or SSL mode never falls back to the server's PG*."""
        unset_settings = dict.fromkeys(("host", "port", "database", "ssl_mode"), unset)

        addrs, params = await _resolve_connect_target({**TENANT_CONFIG, **unset_settings})

        assert addrs == [("localhost", 5439)]
        assert params.database == "dev"
        assert params.sslmode == connect_utils.SSLMode.require
