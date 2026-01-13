"""Tests for SSO admin configuration routes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing_ee.adapters.sso import SSORepository
from dataing_ee.core.sso import SSOConfig, SSOProviderType
from dataing_ee.entrypoints.api.routes.settings import (
    get_sso_repository,
    router,
)


@dataclass
class MockApiKeyContext:
    """Mock API key context for testing."""

    key_id: UUID
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    user_id: UUID | None
    scopes: list[str]


@pytest.fixture
def tenant_id() -> UUID:
    """Create a test tenant ID."""
    return uuid4()


@pytest.fixture
def mock_sso_repo() -> MagicMock:
    """Create mock SSO repository."""
    repo = MagicMock(spec=SSORepository)
    repo.get_sso_config = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_auth(tenant_id: UUID) -> MockApiKeyContext:
    """Create mock auth context with admin scope."""
    return MockApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test-tenant",
        tenant_name="Test Tenant",
        user_id=uuid4(),
        scopes=["admin", "read", "write"],
    )


@pytest.fixture
def app(mock_sso_repo: MagicMock, mock_auth: MockApiKeyContext) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    from dataing.entrypoints.api.middleware.auth import verify_api_key

    app = FastAPI()
    app.include_router(router)

    # Override the repository dependency
    app.dependency_overrides[get_sso_repository] = lambda: mock_sso_repo

    # Override the base auth dependency - this makes all scope checks work
    async def mock_verify_api_key():
        return mock_auth

    app.dependency_overrides[verify_api_key] = mock_verify_api_key

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestGetSSOConfig:
    """Tests for GET /settings/sso/config endpoint."""

    def test_returns_none_when_not_configured(
        self, client: TestClient, mock_sso_repo: MagicMock
    ) -> None:
        """Returns None when SSO is not configured."""
        mock_sso_repo.get_sso_config = AsyncMock(return_value=None)

        response = client.get("/settings/sso/config")

        assert response.status_code == 200
        assert response.json() is None

    def test_returns_config_when_configured(
        self, client: TestClient, mock_sso_repo: MagicMock, tenant_id: UUID
    ) -> None:
        """Returns SSO config when configured."""
        now = datetime.now(UTC)
        config_id = uuid4()

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=tenant_id,
                provider_type=SSOProviderType.OIDC,
                display_name="Okta",
                is_enabled=True,
                oidc_issuer_url="https://example.okta.com",
                oidc_client_id="client-id",
                saml_idp_metadata_url=None,
                saml_idp_entity_id=None,
                saml_certificate=None,
                created_at=now,
                updated_at=now,
            )
        )

        response = client.get("/settings/sso/config")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(config_id)
        assert data["provider_type"] == "oidc"
        assert data["display_name"] == "Okta"
        assert data["oidc_issuer_url"] == "https://example.okta.com"
        assert data["oidc_client_id"] == "client-id"
        assert data["is_enabled"] is True


class TestCreateSSOConfig:
    """Tests for POST /settings/sso/config endpoint."""

    def test_creates_new_config(
        self, client: TestClient, mock_sso_repo: MagicMock, tenant_id: UUID
    ) -> None:
        """Creates new SSO config when none exists."""
        now = datetime.now(UTC)
        config_id = uuid4()

        mock_sso_repo.get_sso_config = AsyncMock(return_value=None)
        mock_sso_repo.create_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=tenant_id,
                provider_type=SSOProviderType.OIDC,
                display_name="Okta",
                is_enabled=True,
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
            "/settings/sso/config",
            json={
                "provider_type": "oidc",
                "display_name": "Okta",
                "oidc_issuer_url": "https://example.okta.com",
                "oidc_client_id": "client-id",
                "oidc_client_secret": "client-secret",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["provider_type"] == "oidc"
        assert data["display_name"] == "Okta"
        mock_sso_repo.create_sso_config.assert_called_once()

    def test_updates_existing_config(
        self, client: TestClient, mock_sso_repo: MagicMock, tenant_id: UUID
    ) -> None:
        """Updates SSO config when one already exists."""
        now = datetime.now(UTC)
        config_id = uuid4()

        existing = SSOConfig(
            id=config_id,
            org_id=tenant_id,
            provider_type=SSOProviderType.OIDC,
            display_name="Old Name",
            is_enabled=False,
            oidc_issuer_url="https://old.okta.com",
            oidc_client_id="old-client-id",
            saml_idp_metadata_url=None,
            saml_idp_entity_id=None,
            saml_certificate=None,
            created_at=now,
            updated_at=now,
        )
        updated = SSOConfig(
            id=config_id,
            org_id=tenant_id,
            provider_type=SSOProviderType.OIDC,
            display_name="New Name",
            is_enabled=True,
            oidc_issuer_url="https://old.okta.com",
            oidc_client_id="old-client-id",
            saml_idp_metadata_url=None,
            saml_idp_entity_id=None,
            saml_certificate=None,
            created_at=now,
            updated_at=now,
        )

        mock_sso_repo.get_sso_config = AsyncMock(return_value=existing)
        mock_sso_repo.update_sso_config = AsyncMock(return_value=updated)
        mock_sso_repo.update_client_secret = AsyncMock(return_value=True)

        response = client.post(
            "/settings/sso/config",
            json={
                "provider_type": "oidc",
                "display_name": "New Name",
                "oidc_issuer_url": "https://example.okta.com",
                "oidc_client_id": "client-id",
                "oidc_client_secret": "new-secret",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["display_name"] == "New Name"
        assert data["is_enabled"] is True
        mock_sso_repo.update_client_secret.assert_called_once()


class TestDisableSSOConfig:
    """Tests for DELETE /settings/sso/config endpoint."""

    def test_disables_existing_config(
        self, client: TestClient, mock_sso_repo: MagicMock, tenant_id: UUID
    ) -> None:
        """Disables SSO config when it exists."""
        now = datetime.now(UTC)
        config_id = uuid4()

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=tenant_id,
                provider_type=SSOProviderType.OIDC,
                display_name="Okta",
                is_enabled=True,
                oidc_issuer_url="https://example.okta.com",
                oidc_client_id="client-id",
                saml_idp_metadata_url=None,
                saml_idp_entity_id=None,
                saml_certificate=None,
                created_at=now,
                updated_at=now,
            )
        )
        mock_sso_repo.update_sso_config = AsyncMock(return_value=True)

        response = client.delete("/settings/sso/config")

        assert response.status_code == 204
        mock_sso_repo.update_sso_config.assert_called_once_with(config_id, is_enabled=False)

    def test_returns_404_when_not_configured(
        self, client: TestClient, mock_sso_repo: MagicMock
    ) -> None:
        """Returns 404 when SSO is not configured."""
        mock_sso_repo.get_sso_config = AsyncMock(return_value=None)

        response = client.delete("/settings/sso/config")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestSSOConfigTest:
    """Tests for POST /settings/sso/test endpoint."""

    def test_returns_success_for_valid_discovery(self, client: TestClient) -> None:
        """Returns success when OIDC discovery is valid."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "authorization_endpoint": "https://example.okta.com/oauth2/v1/authorize",
            "token_endpoint": "https://example.okta.com/oauth2/v1/token",
            "jwks_uri": "https://example.okta.com/oauth2/v1/keys",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            response = client.post(
                "/settings/sso/test",
                json={"oidc_issuer_url": "https://example.okta.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "valid" in data["message"].lower()

    def test_returns_failure_for_missing_fields(self, client: TestClient) -> None:
        """Returns failure when discovery is missing required fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "authorization_endpoint": "https://example.okta.com/oauth2/v1/authorize",
            # Missing token_endpoint and jwks_uri
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            response = client.post(
                "/settings/sso/test",
                json={"oidc_issuer_url": "https://example.okta.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "missing" in data["message"].lower()

    def test_returns_failure_for_connection_error(self, client: TestClient) -> None:
        """Returns failure when IdP is unreachable."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            response = client.post(
                "/settings/sso/test",
                json={"oidc_issuer_url": "https://unreachable.example.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "connect" in data["message"].lower()
