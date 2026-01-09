"""Tests for SSO endpoints."""

import pytest
from dataing_ee.core.sso import SSOProviderType
from dataing_ee.entrypoints.api.routes.sso import _extract_domain, generate_state, router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestExtractDomain:
    """Tests for _extract_domain helper."""

    def test_extracts_domain(self) -> None:
        """Extracts domain from email."""
        assert _extract_domain("alice@acme.com") == "acme.com"

    def test_lowercases_domain(self) -> None:
        """Lowercases the domain."""
        assert _extract_domain("alice@ACME.COM") == "acme.com"

    def test_handles_subdomains(self) -> None:
        """Handles email with subdomain."""
        assert _extract_domain("alice@mail.acme.com") == "mail.acme.com"


class TestGenerateState:
    """Tests for generate_state helper."""

    def test_generates_unique_states(self) -> None:
        """Generates unique state strings."""
        state1 = generate_state("org1", SSOProviderType.OIDC)
        state2 = generate_state("org2", SSOProviderType.OIDC)
        assert state1 != state2

    def test_state_is_url_safe(self) -> None:
        """State is URL-safe."""
        state = generate_state("org1", SSOProviderType.SAML)
        # URL-safe base64 only contains alphanumeric, -, and _
        assert all(c.isalnum() or c in "-_" for c in state)


class TestDiscoverEndpoint:
    """Tests for /discover endpoint."""

    def test_returns_password_method_by_default(self, client: TestClient) -> None:
        """Returns password method when no SSO configured."""
        response = client.post(
            "/auth/sso/discover",
            json={"email": "alice@unknown.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "password"
        assert data["auth_url"] is None

    def test_validates_email_format(self, client: TestClient) -> None:
        """Rejects invalid email format."""
        response = client.post(
            "/auth/sso/discover",
            json={"email": "not-an-email"},
        )

        assert response.status_code == 422  # Validation error


class TestCallbackEndpoint:
    """Tests for /callback endpoint."""

    def test_rejects_invalid_state(self, client: TestClient) -> None:
        """Rejects callback with invalid state."""
        response = client.get(
            "/auth/sso/callback",
            params={"code": "abc123", "state": "invalid-state"},
        )

        assert response.status_code == 400
        assert "Invalid or expired state" in response.json()["detail"]
