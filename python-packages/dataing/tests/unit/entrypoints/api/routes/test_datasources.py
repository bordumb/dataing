"""Authorization tests for write-gated datasource routes."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.core.auth.jwt import create_access_token
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

    Server errors become 500 responses so an open write gate fails the
    status assertion instead of erroring inside the handler.
    """
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: app_db
    return TestClient(app, raise_server_exceptions=False)


def _jwt_request_kwargs(role: OrgRole, via: str) -> dict[str, Any]:
    """Return request kwargs carrying a JWT as a Bearer header or ?token= param."""
    token = create_access_token(
        user_id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        role=role.value,
        teams=[],
    )
    if via == "bearer":
        return {"headers": {"Authorization": f"Bearer {token}"}}
    return {"params": {"token": token}}


@pytest.mark.parametrize("via", ["bearer", "query_param"])
class TestDatasourceWriteAuthorization:
    """Write-gated datasource routes reject viewers and admit members."""

    def test_viewer_cannot_create_datasource(
        self, client: TestClient, app_db: AsyncMock, via: str
    ) -> None:
        """A viewer gets 403 and no datasource is created."""
        response = client.post(
            "/api/v1/datasources",
            json={"name": "warehouse", "type": "postgresql", "config": {}},
            **_jwt_request_kwargs(OrgRole.VIEWER, via),
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Scope 'write' required"
        app_db.create_data_source.assert_not_called()

    def test_viewer_cannot_delete_datasource(
        self, client: TestClient, app_db: AsyncMock, via: str
    ) -> None:
        """A viewer gets 403 and the datasource is not deleted."""
        response = client.delete(
            f"/api/v1/datasources/{uuid.uuid4()}",
            **_jwt_request_kwargs(OrgRole.VIEWER, via),
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Scope 'write' required"
        app_db.delete_data_source.assert_not_called()

    def test_member_can_delete_datasource(
        self, client: TestClient, app_db: AsyncMock, via: str
    ) -> None:
        """A member passes the write gate."""
        response = client.delete(
            f"/api/v1/datasources/{uuid.uuid4()}",
            **_jwt_request_kwargs(OrgRole.MEMBER, via),
        )

        assert response.status_code == 204
        app_db.delete_data_source.assert_awaited_once()
