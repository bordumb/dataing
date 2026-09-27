"""Tests for the lineage routes refusing dbt manifests outside the local data root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.entrypoints.api.routes.lineage import router

ROOT_ENV = "DATAING_LOCAL_DATA_ROOT"
HEADERS = {"X-API-Key": "test-key"}
MANIFEST = {
    "nodes": {
        "model.shop.orders": {
            "name": "orders",
            "resource_type": "model",
            "database": "analytics",
            "schema": "shop",
        }
    }
}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set a local data root holding a dbt manifest, with another manifest outside it."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps(MANIFEST))
    (tmp_path / "outside.json").write_text(json.dumps(MANIFEST))
    monkeypatch.setenv(ROOT_ENV, str(root))
    return root


@pytest.fixture
def client() -> TestClient:
    """Client for the lineage routes, with an API key that authenticates."""
    app_db = AsyncMock()
    app_db.get_api_key_by_hash.return_value = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "scopes": ["read", "write", "admin"],
        "expires_at": None,
        "tenant_slug": "acme",
        "tenant_name": "Acme",
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.app_db = app_db
    return TestClient(app)


def search(client: TestClient, manifest_path: str) -> Any:
    """Search dbt lineage read from the manifest at manifest_path."""
    return client.get(
        "/api/v1/lineage/search",
        params={"q": "orders", "provider": "dbt", "manifest_path": manifest_path},
        headers=HEADERS,
    )


class TestManifestPath:
    """A dbt manifest_path query parameter is read only from inside the root."""

    def test_reads_a_manifest_inside_the_root(self, client: TestClient, root: Path) -> None:
        """A manifest inside the root is read as before."""
        response = search(client, str(root / "manifest.json"))

        assert response.status_code == 200, response.text
        assert [d["name"] for d in response.json()["datasets"]] == ["orders"]

    def test_refuses_a_manifest_outside_the_root(self, client: TestClient, root: Path) -> None:
        """Any authenticated caller could otherwise make the server read host files."""
        response = search(client, str(root.parent / "outside.json"))

        assert response.status_code == 400

    def test_refuses_manifests_while_the_root_is_unset(
        self, client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without a root, local manifests are refused and the error names the setting."""
        monkeypatch.delenv(ROOT_ENV)

        response = search(client, str(root / "manifest.json"))

        assert response.status_code == 400
        assert ROOT_ENV in response.json()["detail"]
