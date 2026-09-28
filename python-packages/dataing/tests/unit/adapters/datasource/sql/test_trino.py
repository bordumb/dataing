"""Tests for TrinoAdapter."""

from __future__ import annotations

from unittest.mock import patch

from trino.auth import BasicAuthentication

from dataing.adapters.datasource.sql.trino import TrinoAdapter


class TestTrinoAdapterConnect:
    """Tests for TrinoAdapter.connect."""

    async def test_logs_in_with_configured_username(self) -> None:
        """The configured username is the Trino user and basic-auth login."""
        adapter = TrinoAdapter(
            {
                "host": "trino.internal",
                "catalog": "hive",
                "username": "alice",
                "password": "alice-secret",
            }
        )

        with patch("trino.dbapi.connect") as trino_connect:
            await adapter.connect()

        kwargs = trino_connect.call_args.kwargs
        assert kwargs["user"] == "alice"
        assert kwargs["auth"] == BasicAuthentication("alice", "alice-secret")
