"""Tests for SnowflakeAdapter."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from dataing.adapters.datasource.sql.snowflake import SnowflakeAdapter


class TestSnowflakeAdapterConnect:
    """Tests for SnowflakeAdapter.connect."""

    async def test_logs_in_with_configured_username(self) -> None:
        """The configured username is passed to the Snowflake connector."""
        connector = MagicMock()
        adapter = SnowflakeAdapter(
            {
                "account": "xy12345.us-east-1",
                "warehouse": "COMPUTE_WH",
                "database": "ANALYTICS",
                "username": "alice",
                "password": "alice-secret",
            }
        )

        with patch.dict(
            sys.modules,
            {"snowflake": MagicMock(connector=connector), "snowflake.connector": connector},
        ):
            await adapter.connect()

        assert connector.connect.call_args.kwargs["user"] == "alice"
