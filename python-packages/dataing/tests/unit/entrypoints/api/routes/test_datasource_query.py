"""Tests for POST /datasources/{id}/query (ad-hoc SQL with stored credentials)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.datasource import AdapterRegistry
from dataing.adapters.datasource.encryption import encrypt_config
from dataing.adapters.datasource.types import QueryResult
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.routes.datasources import router

ADMIN_SCOPES = ["read", "write", "admin"]


class RecordingAdapter:
    """Stands in for a warehouse connection and records every query it runs."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, int]] = []

    async def __aenter__(self) -> RecordingAdapter:
        """Open the (fake) connection."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Close the (fake) connection."""
        return None

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        self.executed.append((sql, timeout_seconds))
        return QueryResult(columns=[{"name": "n", "data_type": "integer"}], rows=[], row_count=0)


def api_key_record(scopes: list[str]) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "scopes": scopes,
        "expires_at": None,
        "tenant_slug": "acme",
        "tenant_name": "Acme",
    }


@pytest.fixture
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> bytes:
    key = Fernet.generate_key()
    monkeypatch.delenv("DATADR_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("ENCRYPTION_KEY", key.decode())
    return key


@pytest.fixture
def app_db() -> AsyncMock:
    db = AsyncMock()
    db.get_api_key_by_hash.return_value = api_key_record(ADMIN_SCOPES)
    return db


@pytest.fixture
def use_datasource(app_db: AsyncMock, encryption_key: bytes) -> Any:
    def _use(source_type: str, config: dict[str, Any] | None = None) -> None:
        app_db.get_data_source.return_value = {
            "id": uuid4(),
            "type": source_type,
            "connection_config_encrypted": encrypt_config(config or {}, encryption_key),
        }

    return _use


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> RecordingAdapter:
    recording = RecordingAdapter()
    monkeypatch.setattr(AdapterRegistry, "create", lambda self, source_type, config: recording)
    return recording


@pytest.fixture
def client(app_db: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.app_db = app_db
    app.dependency_overrides[get_app_db] = lambda: app_db
    return TestClient(app)


def post_query(client: TestClient, sql: str, **body: Any) -> Any:
    return client.post(
        f"/api/v1/datasources/{uuid4()}/query",
        json={"query": sql, **body},
        headers={"X-API-Key": "test-key"},
    )


class TestExecuteQueryAccess:
    """Ad-hoc SQL runs with the datasource's service credentials: admins only."""

    def test_rejects_non_admin(
        self,
        client: TestClient,
        app_db: AsyncMock,
        use_datasource: Any,
        adapter: RecordingAdapter,
    ) -> None:
        app_db.get_api_key_by_hash.return_value = api_key_record(["read", "write"])
        use_datasource("postgresql")

        response = post_query(client, "SELECT 1")

        assert response.status_code == 403
        assert adapter.executed == []


class TestExecuteQueryValidation:
    """Only single, read-only statements reach the datasource."""

    @pytest.mark.parametrize(
        "sql",
        [
            "DELETE FROM orders",
            "UPDATE orders SET status = 'void'",
            "INSERT INTO orders (id) VALUES (1)",
            "DROP TABLE orders",
            "CREATE TABLE pwned AS SELECT 1",
            "SELECT * INTO pwned FROM orders",
            "SELECT 1; DROP TABLE orders",
        ],
    )
    def test_rejects_non_read_only_sql(
        self, client: TestClient, use_datasource: Any, adapter: RecordingAdapter, sql: str
    ) -> None:
        use_datasource("postgresql")

        response = post_query(client, sql)

        assert response.status_code == 400
        assert adapter.executed == []

    def test_runs_read_query_without_limit(
        self, client: TestClient, use_datasource: Any, adapter: RecordingAdapter
    ) -> None:
        use_datasource("postgresql")
        sql = "SELECT status, count(*) FROM orders GROUP BY status"

        response = post_query(client, sql)

        assert response.status_code == 200
        assert adapter.executed == [(sql, 30)]

    def test_validates_in_the_datasource_dialect(
        self, client: TestClient, use_datasource: Any, adapter: RecordingAdapter
    ) -> None:
        # One SELECT to a postgres parser (nested comment); MySQL closes the
        # comment at the first */ and runs the RENAME.
        use_datasource("mysql")

        response = post_query(client, "SELECT 1 /* /* */ ; RENAME TABLE orders TO gone; /* */ */")

        assert response.status_code == 400
        assert adapter.executed == []

    def test_accepts_dialect_specific_syntax(
        self, client: TestClient, use_datasource: Any, adapter: RecordingAdapter
    ) -> None:
        use_datasource("mysql")
        sql = "SELECT `id` FROM `orders`"

        response = post_query(client, sql)

        assert response.status_code == 200
        assert adapter.executed == [(sql, 30)]


class TestExecuteQueryTimeout:
    """timeout_seconds is bounded: 0 disables Postgres/MySQL statement timeouts."""

    @pytest.mark.parametrize("timeout_seconds", [0, -1, 121])
    def test_rejects_timeout_out_of_range(
        self,
        client: TestClient,
        use_datasource: Any,
        adapter: RecordingAdapter,
        timeout_seconds: int,
    ) -> None:
        use_datasource("postgresql")

        response = post_query(client, "SELECT 1", timeout_seconds=timeout_seconds)

        assert response.status_code == 422
        assert adapter.executed == []

    def test_passes_timeout_at_cap(
        self, client: TestClient, use_datasource: Any, adapter: RecordingAdapter
    ) -> None:
        use_datasource("postgresql")

        response = post_query(client, "SELECT 1", timeout_seconds=120)

        assert response.status_code == 200
        assert adapter.executed == [("SELECT 1", 120)]


class TestExecuteQueryOnDuckDB:
    """End to end through the real DuckDB adapter."""

    def test_returns_rows(
        self,
        client: TestClient,
        use_datasource: Any,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("DATAING_LOCAL_DATA_ROOT", str(tmp_path))
        use_datasource("duckdb", {"path": ":memory:"})

        response = post_query(client, "SELECT 42 AS answer")

        assert response.status_code == 200
        assert response.json()["rows"] == [{"answer": 42}]
