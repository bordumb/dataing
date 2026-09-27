"""Tests for the user datasource credentials routes."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import HTTPException

from dataing.adapters.datasource.encryption import encrypt_config
from dataing.entrypoints.api.middleware.auth import ApiKeyContext
from dataing.entrypoints.api.routes import credentials as credentials_routes
from dataing.entrypoints.api.routes.credentials import SaveCredentialsRequest

ENCRYPTION_KEY = b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M="

AUTH = ApiKeyContext(
    key_id=uuid4(),
    tenant_id=uuid4(),
    tenant_slug="acme",
    tenant_name="Acme",
    user_id=uuid4(),
    scopes=["read", "write"],
)
USER_LOGIN = SaveCredentialsRequest(username="alice", password="alice-secret")


def _app_db_with_datasource(source_type: str, config: dict[str, Any]) -> AsyncMock:
    """Build an app database holding one datasource with this encrypted config."""
    app_db = AsyncMock()
    app_db.get_data_source.return_value = {
        "id": uuid4(),
        "name": "Warehouse",
        "type": source_type,
        "connection_config_encrypted": encrypt_config(config, ENCRYPTION_KEY),
    }
    return app_db


def _fake_asyncpg() -> MagicMock:
    """Build a fake asyncpg whose pool answers every query with no rows."""
    conn = AsyncMock()
    conn.fetchrow.return_value = ("PostgreSQL 16.4",)
    conn.fetch.return_value = []
    pool = MagicMock(close=AsyncMock())
    pool.acquire.return_value.__aenter__.return_value = conn
    return MagicMock(create_pool=AsyncMock(return_value=pool))


async def _test_credentials(app_db: AsyncMock) -> credentials_routes.TestConnectionResponse:
    """Call the test-credentials route with the user's login."""
    with patch.object(credentials_routes, "get_encryption_key", return_value=ENCRYPTION_KEY):
        return await credentials_routes.test_credentials(uuid4(), USER_LOGIN, AUTH, app_db)


class TestTestCredentials:
    """Tests for POST /datasources/{datasource_id}/credentials/test."""

    async def test_connects_as_the_user(self) -> None:
        """The connection test logs in with the submitted login, not the service account."""
        app_db = _app_db_with_datasource(
            "postgresql",
            {"host": "db", "database": "shop", "username": "svc", "password": "svc-pw"},
        )
        asyncpg = _fake_asyncpg()

        with patch.dict(sys.modules, {"asyncpg": asyncpg}):
            response = await _test_credentials(app_db)

        assert response.success is True
        dsn = urlsplit(asyncpg.create_pool.call_args.args[0])
        assert (dsn.username, dsn.password) == ("alice", "alice-secret")

    async def test_rejects_source_without_a_login(self) -> None:
        """A source with no database login can't test per-user credentials."""
        app_db = _app_db_with_datasource("sqlite", {"path": "file::memory:"})

        with pytest.raises(HTTPException) as exc_info:
            await _test_credentials(app_db)

        assert exc_info.value.status_code == 400
