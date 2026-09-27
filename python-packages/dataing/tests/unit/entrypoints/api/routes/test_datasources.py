"""Authorization tests for datasource connection management.

Creating, deleting and trial-connecting a datasource are admin-only; the full
per-route policy lives in test_route_authorization.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fixtures.route_authorization import JWT_VIAS, jwt_request_kwargs

from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.routes.datasources import router


@pytest.fixture
def app_db() -> AsyncMock:
    """Return a mock app database where deletes succeed."""
    db = AsyncMock()
    db.delete_data_source.return_value = True
    return db


@pytest.fixture
def client(app_db: AsyncMock) -> TestClient:
    """Return a client for the datasources router with real JWT auth.

    Server errors become 500 responses so an open gate fails the status
    assertion instead of erroring inside the handler.
    """
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: app_db
    return TestClient(app, raise_server_exceptions=False)


def test_anonymous_caller_cannot_trial_connect(client: TestClient) -> None:
    """Trying connection settings needs a signed-in admin, not just a request."""
    response = client.post(
        "/api/v1/datasources/test",
        json={"type": "duckdb", "config": {"path": ":memory:"}},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("via", JWT_VIAS)
class TestDatasourceAdminAuthorization:
    """Connection management rejects members and admits admins."""

    def test_member_cannot_create_datasource(
        self, client: TestClient, app_db: AsyncMock, via: str
    ) -> None:
        """A member gets 403 and no datasource is created."""
        response = client.post(
            "/api/v1/datasources",
            json={"name": "warehouse", "type": "postgresql", "config": {}},
            **jwt_request_kwargs(OrgRole.MEMBER, via),
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Scope 'admin' required"
        app_db.create_data_source.assert_not_called()

    def test_member_cannot_delete_datasource(
        self, client: TestClient, app_db: AsyncMock, via: str
    ) -> None:
        """A member gets 403 and the datasource is not deleted."""
        response = client.delete(
            f"/api/v1/datasources/{uuid.uuid4()}",
            **jwt_request_kwargs(OrgRole.MEMBER, via),
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Scope 'admin' required"
        app_db.delete_data_source.assert_not_called()

    def test_admin_can_delete_datasource(
        self, client: TestClient, app_db: AsyncMock, via: str
    ) -> None:
        """An admin passes the admin gate."""
        response = client.delete(
            f"/api/v1/datasources/{uuid.uuid4()}",
            **jwt_request_kwargs(OrgRole.ADMIN, via),
        )

        assert response.status_code == 204
        app_db.delete_data_source.assert_awaited_once()
