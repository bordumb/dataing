"""Unit tests for Redshift adapter."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from asyncpg import connect_utils

from dataing.adapters.datasource.sql.redshift import RedshiftAdapter

STORED_CONFIG: dict[str, Any] = {
    "host": "warehouse.internal",
    "port": 5439,
    "database": "dev",
    "username": "analyst",
    "password": "s3cret",
}


@pytest.fixture
def no_pg_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep PG* environment variables out of asyncpg's connection resolution."""
    for name in list(os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)


async def _resolve_connect_target(config: dict[str, Any]) -> tuple[Any, Any]:
    """Run connect() against a patched pool and resolve its arguments like asyncpg."""
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


@pytest.mark.usefixtures("no_pg_env")
@pytest.mark.parametrize(
    "password",
    [
        "x@169.254.169.254:80/dev?sslmode=disable#",
        "p a+ss%40w@rd:/?#",
    ],
)
async def test_password_metacharacters_cannot_redirect_connection(password: str) -> None:
    """URL metacharacters in a password never change host, port, or TLS mode."""
    addrs, params = await _resolve_connect_target({**STORED_CONFIG, "password": password})

    assert addrs == [("warehouse.internal", 5439)]
    assert params.sslmode == connect_utils.SSLMode.require
    assert params.password == password
    assert params.user == "analyst"
    assert params.database == "dev"


@pytest.mark.usefixtures("no_pg_env")
@pytest.mark.parametrize("unset", [None, ""])
async def test_unset_config_never_falls_back_to_server_environment(
    unset: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset values use adapter defaults, never the server's own PG* settings."""
    server_env = {
        "PGHOST": "10.0.0.1",
        "PGPORT": "6543",
        "PGDATABASE": "app",
        "PGUSER": "app_owner",
        "PGPASSWORD": "server-secret",
        "PGSSLMODE": "disable",
    }
    for name, value in server_env.items():
        monkeypatch.setenv(name, value)
    fields = ("host", "port", "database", "username", "password", "ssl_mode")

    addrs, params = await _resolve_connect_target(dict.fromkeys(fields, unset))

    assert addrs == [("localhost", 5439)]
    assert (params.user, params.password, params.database) == ("", "", "dev")
    assert params.sslmode == connect_utils.SSLMode.require
