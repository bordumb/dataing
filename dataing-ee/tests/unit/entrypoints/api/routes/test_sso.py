"""Tests for SSO endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing_ee.adapters.sso import (
    SSORepository,
    SSOStateRepository,
    StateConsumedError,
    StateExpiredError,
    StateNotFoundError,
)
from dataing_ee.core.sso import DomainClaim, SSOConfig, SSOProviderType, SSOState
from dataing_ee.entrypoints.api.routes.sso import (
    _extract_domain,
    get_sso_repository,
    get_sso_state_repository,
    router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_state_repo() -> MagicMock:
    """Create mock state repository."""
    return MagicMock(spec=SSOStateRepository)


@pytest.fixture
def mock_sso_repo() -> MagicMock:
    """Create mock SSO repository."""
    repo = MagicMock(spec=SSORepository)
    # Default: no domain claims
    repo.get_domain_claim = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def app(mock_state_repo: MagicMock, mock_sso_repo: MagicMock) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router)

    # Override the repository dependencies
    app.dependency_overrides[get_sso_state_repository] = lambda: mock_state_repo
    app.dependency_overrides[get_sso_repository] = lambda: mock_sso_repo

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

    def test_returns_password_for_unverified_domain(
        self, client: TestClient, mock_sso_repo: MagicMock
    ) -> None:
        """Returns password method for unverified domain claim."""
        now = datetime.now(UTC)
        mock_sso_repo.get_domain_claim = AsyncMock(
            return_value=DomainClaim(
                id=uuid4(),
                org_id=uuid4(),
                domain="unverified.com",
                is_verified=False,  # Not verified
                verification_token="token",
                verified_at=None,
                expires_at=now + timedelta(days=1),
                created_at=now,
            )
        )

        response = client.post(
            "/auth/sso/discover",
            json={"email": "alice@unverified.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "password"

    def test_returns_password_for_disabled_sso(
        self, client: TestClient, mock_sso_repo: MagicMock
    ) -> None:
        """Returns password method when SSO is disabled."""
        now = datetime.now(UTC)
        org_id = uuid4()

        mock_sso_repo.get_domain_claim = AsyncMock(
            return_value=DomainClaim(
                id=uuid4(),
                org_id=org_id,
                domain="example.com",
                is_verified=True,
                verification_token=None,
                verified_at=now,
                expires_at=None,
                created_at=now,
            )
        )
        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=uuid4(),
                org_id=org_id,
                provider_type=SSOProviderType.OIDC,
                display_name="Okta",
                is_enabled=False,  # Disabled
                oidc_issuer_url="https://example.okta.com",
                oidc_client_id="client-id",
                saml_idp_metadata_url=None,
                saml_idp_entity_id=None,
                saml_certificate=None,
                created_at=now,
                updated_at=now,
            )
        )

        response = client.post(
            "/auth/sso/discover",
            json={"email": "alice@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "password"


class TestCallbackEndpoint:
    """Tests for /callback endpoint."""

    def test_rejects_not_found_state(
        self, client: TestClient, mock_state_repo: MagicMock
    ) -> None:
        """Rejects callback with unknown state."""
        mock_state_repo.validate_and_consume = AsyncMock(
            side_effect=StateNotFoundError("SSO state not found")
        )

        response = client.get(
            "/auth/sso/callback",
            params={"code": "abc123", "state": "unknown-state"},
        )

        assert response.status_code == 400
        assert "Invalid state" in response.json()["detail"]

    def test_rejects_expired_state(
        self, client: TestClient, mock_state_repo: MagicMock
    ) -> None:
        """Rejects callback with expired state."""
        mock_state_repo.validate_and_consume = AsyncMock(
            side_effect=StateExpiredError("SSO state has expired")
        )

        response = client.get(
            "/auth/sso/callback",
            params={"code": "abc123", "state": "expired-state"},
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"]

    def test_rejects_consumed_state(
        self, client: TestClient, mock_state_repo: MagicMock
    ) -> None:
        """Rejects callback with already-used state (replay attack)."""
        mock_state_repo.validate_and_consume = AsyncMock(
            side_effect=StateConsumedError("SSO state has already been used")
        )

        response = client.get(
            "/auth/sso/callback",
            params={"code": "abc123", "state": "used-state"},
        )

        assert response.status_code == 400
        assert "already been used" in response.json()["detail"]

    def test_returns_not_implemented(
        self, client: TestClient, mock_state_repo: MagicMock
    ) -> None:
        """Returns 501 when state is valid (feature not yet implemented)."""
        now = datetime.now(UTC)
        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=uuid4(),
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        response = client.get(
            "/auth/sso/callback",
            params={"code": "abc123", "state": "valid-state"},
        )

        # Feature not yet implemented
        assert response.status_code == 501
        assert "not yet implemented" in response.json()["detail"]
