"""Tests for SSO endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dataing_ee.adapters.sso import (
    InvalidSignatureError,
    OIDCTokens,
    SSORepository,
    SSOStateRepository,
    StateConsumedError,
    StateExpiredError,
    StateNotFoundError,
    TokenExpiredError,
)
from dataing_ee.core.sso import (
    DomainClaim,
    SSOConfig,
    SSOIdentity,
    SSOProviderType,
    SSOState,
)
from dataing_ee.entrypoints.api.routes.sso import (
    _extract_domain,
    get_sso_repository,
    get_sso_state_repository,
    router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.core.auth.types import OrgRole, User


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
def mock_app_db() -> MagicMock:
    """Create mock AppDatabase."""
    return MagicMock()


@pytest.fixture
def app(
    mock_state_repo: MagicMock, mock_sso_repo: MagicMock, mock_app_db: MagicMock
) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router)

    # Set up app state for callback endpoint
    app.state.app_db = mock_app_db

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

    def test_rejects_disabled_sso_config(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Rejects callback when SSO config is disabled."""
        now = datetime.now(UTC)
        org_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )
        mock_sso_repo.get_sso_config = AsyncMock(return_value=None)

        response = client.get(
            "/auth/sso/callback",
            params={"code": "abc123", "state": "valid-state"},
        )

        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_callback_exchanges_code_and_creates_user(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Successful callback exchanges code, verifies token, and creates user."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()
        user_id = uuid4()

        # Set up state
        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        # Set up SSO config
        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )
        mock_sso_repo.get_sso_identity = AsyncMock(return_value=None)
        mock_sso_repo.create_sso_identity = AsyncMock(
            return_value=SSOIdentity(
                id=uuid4(),
                user_id=user_id,
                sso_config_id=config_id,
                idp_user_id="idp-user-123",
                created_at=now,
            )
        )

        # Mock OIDC provider
        with (
            patch(
                "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
            ) as mock_provider_class,
            patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_class,
        ):
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-token",
                    id_token="id-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(
                return_value={
                    "sub": "idp-user-123",
                    "email": "alice@example.com",
                    "name": "Alice Smith",
                    "nonce": "test-nonce",
                }
            )
            mock_provider_class.return_value = mock_provider

            # Mock auth repository
            mock_auth_repo = MagicMock()
            mock_auth_repo.get_user_by_email = AsyncMock(return_value=None)
            mock_auth_repo.create_user = AsyncMock(
                return_value=User(
                    id=user_id,
                    email="alice@example.com",
                    name="Alice Smith",
                    is_active=True,
                    created_at=now,
                )
            )
            mock_auth_repo.add_user_to_org = AsyncMock(
                return_value=MagicMock(user_id=user_id, org_id=org_id, role=OrgRole.MEMBER)
            )
            mock_auth_repo.get_user_org_membership = AsyncMock(
                return_value=MagicMock(user_id=user_id, org_id=org_id, role=OrgRole.MEMBER)
            )
            mock_auth_repo.get_user_teams = AsyncMock(return_value=[])
            mock_auth_repo_class.return_value = mock_auth_repo

            response = client.get(
                "/auth/sso/callback",
                params={"code": "auth-code-123", "state": "valid-state"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_callback_uses_existing_sso_identity(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Callback uses existing SSO identity to log in user."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()
        user_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )
        # Existing SSO identity
        mock_sso_repo.get_sso_identity = AsyncMock(
            return_value=SSOIdentity(
                id=uuid4(),
                user_id=user_id,
                sso_config_id=config_id,
                idp_user_id="idp-user-123",
                created_at=now - timedelta(days=30),
            )
        )

        with (
            patch(
                "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
            ) as mock_provider_class,
            patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_class,
        ):
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-token",
                    id_token="id-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(
                return_value={
                    "sub": "idp-user-123",
                    "email": "alice@example.com",
                    "nonce": "test-nonce",
                }
            )
            mock_provider_class.return_value = mock_provider

            mock_auth_repo = MagicMock()
            mock_auth_repo.get_user_by_id = AsyncMock(
                return_value=User(
                    id=user_id,
                    email="alice@example.com",
                    name="Alice Smith",
                    is_active=True,
                    created_at=now - timedelta(days=30),
                )
            )
            mock_auth_repo.get_user_org_membership = AsyncMock(
                return_value=MagicMock(user_id=user_id, org_id=org_id, role=OrgRole.MEMBER)
            )
            mock_auth_repo.get_user_teams = AsyncMock(return_value=[])
            mock_auth_repo_class.return_value = mock_auth_repo

            response = client.get(
                "/auth/sso/callback",
                params={"code": "auth-code-123", "state": "valid-state"},
            )

        assert response.status_code == 200
        # Should not have created a new user
        mock_auth_repo.create_user.assert_not_called()

    def test_callback_rejects_token_exchange_failure(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Rejects callback when token exchange fails."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )

        with patch(
            "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                side_effect=Exception("Token exchange failed")
            )
            mock_provider_class.return_value = mock_provider

            response = client.get(
                "/auth/sso/callback",
                params={"code": "invalid-code", "state": "valid-state"},
            )

        assert response.status_code == 400
        assert "exchange" in response.json()["detail"].lower()

    def test_callback_rejects_expired_id_token(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Rejects callback when ID token has expired."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )

        with patch(
            "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-token",
                    id_token="id-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(
                side_effect=TokenExpiredError("ID token expired")
            )
            mock_provider_class.return_value = mock_provider

            response = client.get(
                "/auth/sso/callback",
                params={"code": "auth-code-123", "state": "valid-state"},
            )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_callback_rejects_invalid_signature(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Rejects callback when ID token signature is invalid."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )

        with patch(
            "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-token",
                    id_token="id-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(
                side_effect=InvalidSignatureError("Invalid signature")
            )
            mock_provider_class.return_value = mock_provider

            response = client.get(
                "/auth/sso/callback",
                params={"code": "auth-code-123", "state": "valid-state"},
            )

        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()

    def test_callback_rejects_missing_email(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Rejects callback when email is not provided by IdP."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )

        with patch(
            "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-token",
                    id_token="id-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            # No email in claims
            mock_provider.verify_id_token = AsyncMock(
                return_value={
                    "sub": "idp-user-123",
                    "nonce": "test-nonce",
                }
            )
            # Userinfo also fails to provide email
            mock_provider.get_user_info = AsyncMock(
                side_effect=Exception("Userinfo failed")
            )
            mock_provider_class.return_value = mock_provider

            response = client.get(
                "/auth/sso/callback",
                params={"code": "auth-code-123", "state": "valid-state"},
            )

        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    def test_callback_links_existing_user_with_verified_email(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Links existing user when email is verified by IdP."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()
        user_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )
        mock_sso_repo.get_sso_identity = AsyncMock(return_value=None)
        mock_sso_repo.create_sso_identity = AsyncMock(
            return_value=SSOIdentity(
                id=uuid4(),
                user_id=user_id,
                sso_config_id=config_id,
                idp_user_id="idp-user-123",
                created_at=now,
            )
        )

        with (
            patch(
                "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
            ) as mock_provider_class,
            patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_class,
        ):
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-token",
                    id_token="id-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            # Email is verified by IdP
            mock_provider.verify_id_token = AsyncMock(
                return_value={
                    "sub": "idp-user-123",
                    "email": "alice@example.com",
                    "email_verified": True,
                    "nonce": "test-nonce",
                }
            )
            mock_provider_class.return_value = mock_provider

            # Existing user found by email
            mock_auth_repo = MagicMock()
            mock_auth_repo.get_user_by_email = AsyncMock(
                return_value=User(
                    id=user_id,
                    email="alice@example.com",
                    name="Alice Smith",
                    is_active=True,
                    created_at=now - timedelta(days=30),
                )
            )
            mock_auth_repo.get_user_org_membership = AsyncMock(
                return_value=MagicMock(user_id=user_id, org_id=org_id, role=OrgRole.MEMBER)
            )
            mock_auth_repo.get_user_teams = AsyncMock(return_value=[])
            mock_auth_repo_class.return_value = mock_auth_repo

            response = client.get(
                "/auth/sso/callback",
                params={"code": "auth-code-123", "state": "valid-state"},
            )

        assert response.status_code == 200
        # Should have linked existing user, not created new one
        mock_auth_repo.create_user.assert_not_called()
        # SSO identity should be created
        mock_sso_repo.create_sso_identity.assert_called_once()

    def test_callback_rejects_link_when_email_not_verified(
        self, client: TestClient, mock_state_repo: MagicMock, mock_sso_repo: MagicMock
    ) -> None:
        """Rejects linking existing user when email is not verified by IdP."""
        now = datetime.now(UTC)
        org_id = uuid4()
        config_id = uuid4()
        user_id = uuid4()

        mock_state_repo.validate_and_consume = AsyncMock(
            return_value=SSOState(
                state_id="valid-state",
                nonce="test-nonce",
                org_id=org_id,
                redirect_uri=None,
                created_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=9),
                consumed_at=now,
            )
        )

        mock_sso_repo.get_sso_config = AsyncMock(
            return_value=SSOConfig(
                id=config_id,
                org_id=org_id,
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
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(
            return_value="client-secret"
        )
        mock_sso_repo.get_sso_identity = AsyncMock(return_value=None)

        with (
            patch(
                "dataing_ee.entrypoints.api.routes.sso.OIDCProvider"
            ) as mock_provider_class,
            patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_class,
        ):
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-token",
                    id_token="id-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            # Email is NOT verified by IdP
            mock_provider.verify_id_token = AsyncMock(
                return_value={
                    "sub": "idp-user-123",
                    "email": "alice@example.com",
                    "email_verified": False,
                    "nonce": "test-nonce",
                }
            )
            mock_provider_class.return_value = mock_provider

            # Existing user found by email
            mock_auth_repo = MagicMock()
            mock_auth_repo.get_user_by_email = AsyncMock(
                return_value=User(
                    id=user_id,
                    email="alice@example.com",
                    name="Alice Smith",
                    is_active=True,
                    created_at=now - timedelta(days=30),
                )
            )
            mock_auth_repo_class.return_value = mock_auth_repo

            response = client.get(
                "/auth/sso/callback",
                params={"code": "auth-code-123", "state": "valid-state"},
            )

        assert response.status_code == 400
        assert "verified" in response.json()["detail"].lower()
        # Should NOT have linked or created
        mock_sso_repo.create_sso_identity.assert_not_called()
