"""Tests for the datasource routes refusing local paths outside the local data root."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.datasource import SourceType, get_registry
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.routes.datasources import router

ROOT_ENV = "DATAING_LOCAL_DATA_ROOT"
HEADERS = {"X-API-Key": "test-key"}
LOCAL_TYPES = ["local_file", "duckdb"]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set a local data root holding one CSV file."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "orders.csv").write_text("id\n1\n2\n")
    monkeypatch.setenv(ROOT_ENV, str(root))
    return root


@pytest.fixture
def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """App database that knows an admin API key and saves new sources."""
    monkeypatch.delenv("DATADR_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = AsyncMock()
    db.get_api_key_by_hash.return_value = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "scopes": ["read", "write", "admin"],
        "expires_at": None,
        "tenant_slug": "acme",
        "tenant_name": "Acme",
    }
    db.create_data_source.return_value = {
        "id": uuid4(),
        "name": "Orders",
        "type": "local_file",
        "is_default": False,
        "is_active": True,
        "created_at": datetime.now(UTC),
    }
    return db


@pytest.fixture
def client(app_db: AsyncMock) -> TestClient:
    """Client for the datasource routes, with no limit on datasources."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.app_db = app_db
    app.state.entitlements_adapter = AsyncMock()
    app.state.entitlements_adapter.check_limit.return_value = True
    app.dependency_overrides[get_app_db] = lambda: app_db
    return TestClient(app)


@pytest.fixture
def connections(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record the config of every local adapter that tries to connect, without connecting."""
    attempts: list[dict[str, Any]] = []

    async def record(self: Any) -> None:
        attempts.append(self._config)

    for source_type in LOCAL_TYPES:
        adapter_class = get_registry().get_adapter_class(SourceType(source_type))
        monkeypatch.setattr(adapter_class, "connect", record)
    return attempts


class TestCreateDatasource:
    """POST /datasources keeps local sources inside the local data root."""

    @pytest.mark.parametrize("source_type", LOCAL_TYPES)
    def test_refuses_a_path_outside_the_root_before_connecting(
        self,
        client: TestClient,
        app_db: AsyncMock,
        root: Path,
        connections: list[dict[str, Any]],
        source_type: str,
    ) -> None:
        """The whole host is refused before any adapter connects, and nothing is saved."""
        response = client.post(
            "/api/v1/datasources",
            json={"name": "Host", "type": source_type, "config": {"path": "/"}},
            headers=HEADERS,
        )

        assert response.status_code == 400
        assert connections == []
        app_db.create_data_source.assert_not_awaited()

    @pytest.mark.parametrize("source_type", LOCAL_TYPES)
    def test_refuses_local_sources_while_the_root_is_unset(
        self,
        client: TestClient,
        app_db: AsyncMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        source_type: str,
    ) -> None:
        """Without a root, local sources are refused and the error names the setting."""
        monkeypatch.delenv(ROOT_ENV, raising=False)

        response = client.post(
            "/api/v1/datasources",
            json={"name": "Local", "type": source_type, "config": {"path": str(tmp_path)}},
            headers=HEADERS,
        )

        assert response.status_code == 400
        assert ROOT_ENV in response.json()["detail"]
        app_db.create_data_source.assert_not_awaited()

    @pytest.mark.parametrize("source_type", LOCAL_TYPES)
    def test_creates_a_source_inside_the_root(
        self, client: TestClient, app_db: AsyncMock, root: Path, source_type: str
    ) -> None:
        """A directory inside the root is saved as before."""
        response = client.post(
            "/api/v1/datasources",
            json={"name": "Orders", "type": source_type, "config": {"path": str(root)}},
            headers=HEADERS,
        )

        assert response.status_code == 201, response.text
        app_db.create_data_source.assert_awaited_once()


class TestTestConnection:
    """POST /datasources/test keeps local sources inside the local data root."""

    @pytest.mark.parametrize("source_type", LOCAL_TYPES)
    def test_refuses_a_path_outside_the_root_before_connecting(
        self,
        client: TestClient,
        root: Path,
        connections: list[dict[str, Any]],
        source_type: str,
    ) -> None:
        """Testing a connection to the whole host is refused before any adapter connects."""
        response = client.post(
            "/api/v1/datasources/test",
            json={"type": source_type, "config": {"path": "/"}},
            headers=HEADERS,
        )

        assert response.status_code == 400
        assert connections == []
