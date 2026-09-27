"""Tests for user datasource credentials routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.datasource.encryption import encrypt_config
from dataing.adapters.datasource.errors import CredentialsNotSupportedError
from dataing.adapters.datasource.types import ConnectionTestResult, SourceType
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.credentials import router

# Source types whose connection config has no database login, with a stored config
NO_LOGIN_SOURCES = [
    ("bigquery", {"project_id": "acme-analytics"}),
    ("sqlite", {"path": "warehouse.db"}),
    ("duckdb", {"path": "warehouse.duckdb"}),
]
LOGIN = {"username": "alice", "password": "alice-secret"}


def _datasource(source_type: str, config: dict[str, Any], key: bytes) -> dict[str, Any]:
    """Build a data_sources row with an encrypted connection config."""
    return {
        "id": uuid4(),
        "name": "Warehouse",
        "type": source_type,
        "connection_config_encrypted": encrypt_config(config, key),
    }


def _client(datasource: dict[str, Any]) -> tuple[TestClient, AsyncMock]:
    """Serve the credentials routes to a member of the datasource's tenant."""
    app_db = AsyncMock()
    app_db.get_data_source.return_value = datasource
    app_db.get_user_credentials.return_value = None
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=uuid4(),
        tenant_slug="acme",
        tenant_name="Acme",
        user_id=uuid4(),
        scopes=["read", "write"],
    )
    app.dependency_overrides[get_app_db] = lambda: app_db
    return TestClient(app), app_db


class TestSaveCredentialsEndpoint:
    """Test POST /datasources/{datasource_id}/credentials."""

    @pytest.mark.parametrize(("source_type", "stored_config"), NO_LOGIN_SOURCES)
    def test_source_without_a_login_is_rejected(
        self, encryption_key: bytes, source_type: str, stored_config: dict[str, Any]
    ) -> None:
        """Credentials that could never be used are refused rather than stored."""
        datasource = _datasource(source_type, stored_config, encryption_key)
        client, app_db = _client(datasource)

        response = client.post(f"/datasources/{datasource['id']}/credentials", json=LOGIN)

        assert response.status_code == 400
        assert response.json() == {"detail": CredentialsNotSupportedError(source_type).message}
        app_db.upsert_user_credentials.assert_not_called()

    def test_saves_login_for_postgres(self, encryption_key: bytes) -> None:
        """A source with a login still stores the user's own credentials."""
        stored_config = {"host": "db.internal", "username": "svc", "password": "svc-secret"}
        datasource = _datasource("postgresql", stored_config, encryption_key)
        client, app_db = _client(datasource)
        app_db.get_user_credentials.return_value = {
            "db_username": "alice",
            "last_used_at": None,
            "created_at": None,
        }

        response = client.post(f"/datasources/{datasource['id']}/credentials", json=LOGIN)

        assert response.status_code == 201
        assert response.json()["configured"] is True
        assert app_db.upsert_user_credentials.await_args.kwargs["db_username"] == "alice"


class TestTestCredentialsEndpoint:
    """Test POST /datasources/{datasource_id}/credentials/test."""

    def test_connects_with_submitted_login(self, encryption_key: bytes) -> None:
        """The adapter is built with the submitted login, not the stored one."""
        stored_config = {
            "host": "db.internal",
            "port": 5432,
            "database": "analytics",
            "username": "svc_dataing",
            "password": "svc-secret",
        }
        datasource = _datasource("postgresql", stored_config, encryption_key)
        client, _ = _client(datasource)
        adapter = MagicMock()
        adapter.test_connection = AsyncMock(
            return_value=ConnectionTestResult(success=True, message="Connection successful")
        )
        adapter.get_schema = AsyncMock(side_effect=RuntimeError("schema not needed"))
        registry = MagicMock()
        registry.create.return_value = adapter

        with patch(
            "dataing.entrypoints.api.routes.credentials.get_registry",
            return_value=registry,
        ):
            response = client.post(f"/datasources/{datasource['id']}/credentials/test", json=LOGIN)

        assert response.status_code == 200
        assert response.json()["success"] is True
        registry.create.assert_called_once_with(SourceType.POSTGRESQL, {**stored_config, **LOGIN})

    @pytest.mark.parametrize(("source_type", "stored_config"), NO_LOGIN_SOURCES)
    def test_source_without_a_login_is_rejected(
        self, encryption_key: bytes, source_type: str, stored_config: dict[str, Any]
    ) -> None:
        """A source with no login answers 400, instead of testing its stored config."""
        datasource = _datasource(source_type, stored_config, encryption_key)
        client, _ = _client(datasource)

        with patch("dataing.entrypoints.api.routes.credentials.get_registry") as get_registry:
            response = client.post(f"/datasources/{datasource['id']}/credentials/test", json=LOGIN)

        assert response.status_code == 400
        assert response.json() == {"detail": CredentialsNotSupportedError(source_type).message}
        get_registry.return_value.create.assert_not_called()
