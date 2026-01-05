"""Tests for auth API routes."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dataing.core.auth.service import AuthError
from dataing.entrypoints.api.routes.auth import get_auth_service, router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """Create mock auth service."""
    return MagicMock()


@pytest.fixture
def app(mock_auth_service: MagicMock) -> FastAPI:
    """Create test app with auth router and mocked service."""
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestLoginEndpoint:
    """Test POST /auth/login."""

    def test_login_success(self, client: TestClient, mock_auth_service: MagicMock) -> None:
        """Should return tokens on successful login."""
        mock_auth_service.login = AsyncMock(
            return_value={
                "access_token": "access.token.here",
                "refresh_token": "refresh.token.here",
                "token_type": "bearer",
                "user": {"id": "user-id", "email": "test@example.com", "name": "Test"},
                "org": {"id": "org-id", "name": "Org", "slug": "org", "plan": "free"},
                "role": "admin",
            }
        )

        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",  # pragma: allowlist secret
                "org_id": "00000000-0000-0000-0000-000000000001",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_credentials(
        self, client: TestClient, mock_auth_service: MagicMock
    ) -> None:
        """Should return 401 for invalid credentials."""
        mock_auth_service.login = AsyncMock(side_effect=AuthError("Invalid credentials"))

        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrong",  # pragma: allowlist secret
                "org_id": "00000000-0000-0000-0000-000000000001",
            },
        )

        assert response.status_code == 401


class TestRegisterEndpoint:
    """Test POST /auth/register."""

    def test_register_success(self, client: TestClient, mock_auth_service: MagicMock) -> None:
        """Should create user and return tokens."""
        mock_auth_service.register = AsyncMock(
            return_value={
                "access_token": "access.token.here",
                "refresh_token": "refresh.token.here",
                "token_type": "bearer",
                "user": {"id": "user-id", "email": "new@example.com", "name": "New User"},
                "org": {"id": "org-id", "name": "New Org", "slug": "new-org", "plan": "free"},
                "role": "owner",
            }
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",  # pragma: allowlist secret
                "name": "New User",
                "org_name": "New Org",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "new@example.com"
