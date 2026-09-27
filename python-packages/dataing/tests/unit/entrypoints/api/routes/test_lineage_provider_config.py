"""Tests for the lineage routes reading provider settings only from the organization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.entrypoints.api.routes.lineage import router

ROOT_ENV = "DATAING_LOCAL_DATA_ROOT"
HEADERS = {"X-API-Key": "test-key"}


def manifest(model: str) -> str:
    """A dbt manifest holding one model."""
    node = {"name": model, "resource_type": "model", "database": "analytics", "schema": "shop"}
    return json.dumps({"nodes": {f"model.shop.{model}": node}})


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set a local data root holding two dbt manifests."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "manifest.json").write_text(manifest("orders"))
    (root / "other.json").write_text(manifest("secrets"))
    monkeypatch.setenv(ROOT_ENV, str(root))
    return root


@pytest.fixture
def app_db() -> AsyncMock:
    """App database with an API key for an organization with no lineage settings."""
    db = AsyncMock()
    db.get_api_key_by_hash.return_value = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "scopes": ["read"],
        "expires_at": None,
        "tenant_slug": "acme",
        "tenant_name": "Acme",
    }
    db.get_tenant.return_value = {"id": uuid4(), "settings": {}}
    return db


def configure(app_db: AsyncMock, config: dict[str, Any]) -> None:
    """Store a dbt lineage provider in the organization's settings."""
    providers = [{"provider": "dbt", "config": config}]
    app_db.get_tenant.return_value = {"id": uuid4(), "settings": {"lineage_providers": providers}}


@pytest.fixture
def client(app_db: AsyncMock) -> TestClient:
    """Client for the lineage routes."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.app_db = app_db
    return TestClient(app)


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every outbound HTTP request the server makes, without sending it."""
    urls: list[str] = []

    async def send(self: httpx.AsyncClient, request: httpx.Request, **kwargs: Any) -> Any:
        urls.append(str(request.url))
        raise httpx.ConnectError("outbound requests are blocked in tests", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    return urls


def search(client: TestClient, **params: str) -> Any:
    """Search lineage datasets, passing any extra query parameters."""
    return client.get("/api/v1/lineage/search", params={"q": "s", **params}, headers=HEADERS)


def names(response: Any) -> list[str]:
    """Dataset names in a search response."""
    return [d["name"] for d in response.json()["datasets"]]


class TestLineageProviderConfig:
    """Lineage routes use the organization's configured provider, never the caller's."""

    def test_reads_the_configured_provider(
        self, client: TestClient, app_db: AsyncMock, root: Path
    ) -> None:
        """The provider comes from the organization's settings."""
        configure(app_db, {"manifest_path": str(root / "manifest.json")})

        response = search(client)

        assert response.status_code == 200, response.text
        assert names(response) == ["orders"]

    def test_ignores_a_caller_supplied_manifest_path(
        self, client: TestClient, app_db: AsyncMock, root: Path
    ) -> None:
        """A caller cannot point the server at another file."""
        configure(app_db, {"manifest_path": str(root / "manifest.json")})

        response = search(client, manifest_path=str(root / "other.json"))

        assert response.status_code == 200, response.text
        assert names(response) == ["orders"]

    def test_ignores_a_caller_supplied_base_url(
        self, client: TestClient, app_db: AsyncMock, root: Path, outbound: list[str]
    ) -> None:
        """A caller cannot make the server fetch a URL of its choosing."""
        configure(app_db, {"manifest_path": str(root / "manifest.json")})

        response = search(client, provider="openlineage", base_url="http://169.254.169.254")

        assert response.status_code == 200, response.text
        assert names(response) == ["orders"]
        assert outbound == []

    def test_refuses_when_no_provider_is_configured(
        self, client: TestClient, outbound: list[str]
    ) -> None:
        """Without a configured provider nothing is queried, not even a default URL."""
        response = search(client, provider="openlineage")

        assert response.status_code == 404
        assert outbound == []

    def test_refuses_a_configured_manifest_outside_the_root(
        self, client: TestClient, app_db: AsyncMock, root: Path
    ) -> None:
        """A stored manifest path is held to the local data root as well."""
        outside = root.parent / "outside.json"
        outside.write_text(manifest("secrets"))
        configure(app_db, {"manifest_path": str(outside)})

        response = search(client)

        assert response.status_code == 500
        assert ROOT_ENV in response.json()["detail"]
