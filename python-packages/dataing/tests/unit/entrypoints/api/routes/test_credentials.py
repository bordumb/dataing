"""Tests for user datasource credentials routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.datasource.encryption import encrypt_config
from dataing.adapters.datasource.types import ConnectionTestResult, SourceType
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.credentials import router


class TestTestCredentialsEndpoint:
    """Test POST /datasources/{datasource_id}/credentials/test."""

    def test_connects_with_submitted_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The adapter is built with the submitted login, not the stored one."""
        key = Fernet.generate_key()
        monkeypatch.delenv("DATADR_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("ENCRYPTION_KEY", key.decode())
        tenant_id = uuid4()
        datasource_id = uuid4()
        stored_config = {
            "host": "db.internal",
            "port": 5432,
            "database": "analytics",
            "username": "svc_dataing",
            "password": "svc-secret",
        }
        app_db = AsyncMock()
        app_db.get_data_source.return_value = {
            "id": datasource_id,
            "name": "Warehouse",
            "type": "postgresql",
            "connection_config_encrypted": encrypt_config(stored_config, key),
        }
        adapter = MagicMock()
        adapter.test_connection = AsyncMock(
            return_value=ConnectionTestResult(success=True, message="Connection successful")
        )
        adapter.get_schema = AsyncMock(side_effect=RuntimeError("schema not needed"))
        registry = MagicMock()
        registry.create.return_value = adapter

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
            key_id=uuid4(),
            tenant_id=tenant_id,
            tenant_slug="acme",
            tenant_name="Acme",
            user_id=uuid4(),
            scopes=["read", "write"],
        )
        app.dependency_overrides[get_app_db] = lambda: app_db

        with patch(
            "dataing.entrypoints.api.routes.credentials.get_registry",
            return_value=registry,
        ):
            response = TestClient(app).post(
                f"/datasources/{datasource_id}/credentials/test",
                json={"username": "alice", "password": "alice-secret"},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        registry.create.assert_called_once_with(
            SourceType.POSTGRESQL,
            {**stored_config, "username": "alice", "password": "alice-secret"},
        )
