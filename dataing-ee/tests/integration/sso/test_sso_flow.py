"""Integration tests for SSO authentication flow.

These tests verify the complete SSO flow from discovery to authenticated session,
using mocked external IdP responses but exercising the full internal logic.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.core.auth.types import User
from dataing_ee.adapters.sso import (
    OIDCTokens,
    SSORepository,
    SSOStateRepository,
)
from dataing_ee.core.sso import (
    DomainClaim,
    SSOConfig,
    SSOIdentity,
    SSOProviderType,
    SSOState,
)
from dataing_ee.entrypoints.api.routes.sso import (
    get_sso_repository,
    get_sso_state_repository,
    router,
)


@pytest.fixture
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate RSA key pair for signing tokens."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def tenant_id() -> UUID:
    """Test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Test user ID."""
    return uuid4()


@pytest.fixture
def config_id() -> UUID:
    """Test SSO config ID."""
    return uuid4()


@pytest.fixture
def sso_config(tenant_id: UUID, config_id: UUID) -> SSOConfig:
    """Create test SSO configuration."""
    return SSOConfig(
        id=config_id,
        org_id=tenant_id,
        provider_type=SSOProviderType.OIDC,
        display_name="Sign in with Test IdP",
        is_enabled=True,
        oidc_issuer_url="https://idp.example.com",
        oidc_client_id="test-client-id",
        saml_idp_metadata_url=None,
        saml_idp_entity_id=None,
        saml_certificate=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def domain_claim(tenant_id: UUID) -> DomainClaim:
    """Create verified domain claim."""
    return DomainClaim(
        id=uuid4(),
        org_id=tenant_id,
        domain="acme.com",
        is_verified=True,
        verification_token=None,
        verified_at=datetime.now(UTC),
        expires_at=None,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_state_repo() -> MagicMock:
    """Create mock state repository."""
    return MagicMock(spec=SSOStateRepository)


@pytest.fixture
def mock_sso_repo() -> MagicMock:
    """Create mock SSO repository."""
    repo = MagicMock(spec=SSORepository)
    repo.get_domain_claim = AsyncMock(return_value=None)
    repo.get_sso_config = AsyncMock(return_value=None)
    repo.get_sso_identity = AsyncMock(return_value=None)
    repo.create_sso_identity = AsyncMock()
    repo.get_decrypted_client_secret = AsyncMock(return_value="client-secret")
    return repo


@pytest.fixture
def mock_app_db() -> MagicMock:
    """Create mock AppDatabase."""
    return MagicMock()


@pytest.fixture
def mock_auth_repo() -> MagicMock:
    """Create mock auth repository."""
    repo = MagicMock()
    repo.get_user_by_email = AsyncMock(return_value=None)
    repo.create_user = AsyncMock()
    repo.add_user_to_org = AsyncMock()
    return repo


@pytest.fixture
def app(
    mock_state_repo: MagicMock,
    mock_sso_repo: MagicMock,
    mock_app_db: MagicMock,
) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router)
    app.state.app_db = mock_app_db

    app.dependency_overrides[get_sso_state_repository] = lambda: mock_state_repo
    app.dependency_overrides[get_sso_repository] = lambda: mock_sso_repo

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


def create_signed_token(
    private_key: rsa.RSAPrivateKey,
    claims: dict,
    kid: str = "test-key-id",
) -> str:
    """Create a signed JWT for testing."""
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.mark.integration
class TestSSODiscoveryFlow:
    """Tests for SSO discovery endpoint."""

    def test_discovery_returns_password_for_unknown_domain(
        self,
        client: TestClient,
        mock_sso_repo: MagicMock,
    ) -> None:
        """Returns password method for unconfigured domain."""
        mock_sso_repo.get_domain_claim = AsyncMock(return_value=None)

        response = client.post(
            "/auth/sso/discover",
            json={"email": "alice@unknown.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "password"
        assert data["auth_url"] is None

    def test_discovery_returns_password_for_unverified_domain(
        self,
        client: TestClient,
        mock_sso_repo: MagicMock,
        tenant_id: UUID,
    ) -> None:
        """Returns password method for unverified domain claim."""
        unverified_claim = DomainClaim(
            id=uuid4(),
            org_id=tenant_id,
            domain="pending.com",
            is_verified=False,
            verification_token="pending-token",
            verified_at=None,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            created_at=datetime.now(UTC),
        )
        mock_sso_repo.get_domain_claim = AsyncMock(return_value=unverified_claim)

        response = client.post(
            "/auth/sso/discover",
            json={"email": "alice@pending.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "password"

    def test_discovery_returns_sso_for_verified_domain(
        self,
        client: TestClient,
        mock_sso_repo: MagicMock,
        mock_state_repo: MagicMock,
        domain_claim: DomainClaim,
        sso_config: SSOConfig,
    ) -> None:
        """Returns SSO auth URL for verified domain with SSO configured."""
        mock_sso_repo.get_domain_claim = AsyncMock(return_value=domain_claim)
        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)
        mock_state_repo.create_state = AsyncMock(
            return_value=SSOState(
                state_id="test-state",
                nonce="test-nonce",
                org_id=domain_claim.org_id,
                redirect_uri=None,
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
                consumed_at=None,
            )
        )

        with patch("dataing_ee.entrypoints.api.routes.sso.OIDCProvider") as mock_provider:
            mock_provider.return_value.get_authorization_url = AsyncMock(
                return_value="https://idp.example.com/authorize?state=test-state"
            )

            response = client.post(
                "/auth/sso/discover",
                json={"email": "alice@acme.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "oidc"  # Returns 'oidc' not 'sso'
        assert "idp.example.com" in data["auth_url"]

    def test_discovery_returns_password_when_sso_disabled(
        self,
        client: TestClient,
        mock_sso_repo: MagicMock,
        domain_claim: DomainClaim,
        sso_config: SSOConfig,
    ) -> None:
        """Returns password when SSO config exists but is disabled."""
        sso_config.is_enabled = False
        mock_sso_repo.get_domain_claim = AsyncMock(return_value=domain_claim)
        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)

        response = client.post(
            "/auth/sso/discover",
            json={"email": "alice@acme.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "password"


@pytest.mark.integration
class TestSSOCallbackFlow:
    """Tests for SSO callback endpoint."""

    def test_callback_rejects_invalid_state(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
    ) -> None:
        """Rejects callback with invalid or expired state."""
        from dataing_ee.adapters.sso import StateNotFoundError

        mock_state_repo.validate_and_consume = AsyncMock(
            side_effect=StateNotFoundError("State not found")
        )

        response = client.get("/auth/sso/callback?code=abc&state=invalid-state")

        assert response.status_code == 400
        assert "Invalid state" in response.json()["detail"]

    def test_callback_rejects_consumed_state(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
    ) -> None:
        """Rejects callback with already-used state (replay attack)."""
        from dataing_ee.adapters.sso import StateConsumedError

        mock_state_repo.validate_and_consume = AsyncMock(
            side_effect=StateConsumedError("State already consumed")
        )

        response = client.get("/auth/sso/callback?code=abc&state=used-state")

        assert response.status_code == 400
        assert "already been used" in response.json()["detail"]

    def test_callback_jit_provisions_new_user(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
        mock_sso_repo: MagicMock,
        mock_auth_repo: MagicMock,
        sso_config: SSOConfig,
        tenant_id: UUID,
        user_id: UUID,
        config_id: UUID,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Creates new user on first SSO login (JIT provisioning)."""
        private_key, public_key = rsa_keypair
        now = datetime.now(UTC)

        # Create valid state
        state = SSOState(
            state_id="test-state",
            nonce="test-nonce",
            org_id=tenant_id,
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=now,
        )
        mock_state_repo.validate_and_consume = AsyncMock(return_value=state)

        # SSO config exists
        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)
        mock_sso_repo.get_sso_identity = AsyncMock(return_value=None)  # No existing SSO link
        mock_sso_repo.create_sso_identity = AsyncMock()
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(return_value="client-secret")

        # No existing user
        mock_auth_repo.get_user_by_email = AsyncMock(return_value=None)
        created_user = User(
            id=user_id,
            email="newuser@acme.com",
            name="New User",
            is_active=True,
            created_at=now,
        )
        mock_auth_repo.create_user = AsyncMock(return_value=created_user)
        mock_auth_repo.add_user_to_org = AsyncMock()

        # Create valid ID token claims
        claims = {
            "sub": "idp-user-123",
            "email": "newuser@acme.com",
            "email_verified": True,
            "name": "New User",
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": "test-nonce",
        }
        id_token = create_signed_token(private_key, claims)

        # Mock OIDC provider
        with patch("dataing_ee.entrypoints.api.routes.sso.OIDCProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider_cls.return_value = mock_provider
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-123",
                    id_token=id_token,
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token="refresh-123",
                )
            )
            mock_provider.verify_id_token = AsyncMock(return_value=claims)

            # Mock auth repository - set return_value directly (not a context manager)
            with patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_cls:
                mock_auth_repo_cls.return_value = mock_auth_repo
                mock_auth_repo.get_user_org_membership = AsyncMock(return_value=MagicMock())
                mock_auth_repo.get_user_teams = AsyncMock(return_value=[])

                # Mock JWT creation
                with patch(
                    "dataing_ee.entrypoints.api.routes.sso.create_access_token"
                ) as mock_create_token:
                    mock_create_token.return_value = "jwt-access-token"

                    with patch(
                        "dataing_ee.entrypoints.api.routes.sso.create_refresh_token"
                    ) as mock_create_refresh:
                        mock_create_refresh.return_value = "jwt-refresh-token"

                        response = client.get(
                            "/auth/sso/callback?code=auth-code&state=test-state"
                        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "jwt-access-token"
        assert data["refresh_token"] == "jwt-refresh-token"
        assert data["token_type"] == "bearer"

    def test_callback_links_existing_user_with_verified_email(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
        mock_sso_repo: MagicMock,
        mock_auth_repo: MagicMock,
        sso_config: SSOConfig,
        tenant_id: UUID,
        user_id: UUID,
        config_id: UUID,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Links existing user to SSO identity when email is verified."""
        private_key, public_key = rsa_keypair
        now = datetime.now(UTC)

        # Create valid state
        state = SSOState(
            state_id="test-state",
            nonce="test-nonce",
            org_id=tenant_id,
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=now,
        )
        mock_state_repo.validate_and_consume = AsyncMock(return_value=state)

        # SSO config exists, no existing SSO identity
        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)
        mock_sso_repo.get_sso_identity = AsyncMock(return_value=None)
        mock_sso_repo.create_sso_identity = AsyncMock()
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(return_value="client-secret")

        # Existing user with password auth
        existing_user = User(
            id=user_id,
            email="existing@acme.com",
            name="Existing User",
            is_active=True,
            created_at=now - timedelta(days=30),
        )
        mock_auth_repo.get_user_by_email = AsyncMock(return_value=existing_user)

        # ID token with verified email
        claims = {
            "sub": "idp-user-456",
            "email": "existing@acme.com",
            "email_verified": True,
            "name": "Existing User",
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": "test-nonce",
        }
        id_token = create_signed_token(private_key, claims)

        with patch("dataing_ee.entrypoints.api.routes.sso.OIDCProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider_cls.return_value = mock_provider
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-123",
                    id_token=id_token,
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(return_value=claims)

            with patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_cls:
                mock_auth_repo_cls.return_value = mock_auth_repo
                mock_auth_repo.get_user_org_membership = AsyncMock(return_value=MagicMock())
                mock_auth_repo.get_user_teams = AsyncMock(return_value=[])

                with patch(
                    "dataing_ee.entrypoints.api.routes.sso.create_access_token"
                ) as mock_create_token:
                    mock_create_token.return_value = "jwt-access-token"

                    with patch(
                        "dataing_ee.entrypoints.api.routes.sso.create_refresh_token"
                    ) as mock_create_refresh:
                        mock_create_refresh.return_value = "jwt-refresh-token"

                        response = client.get(
                            "/auth/sso/callback?code=auth-code&state=test-state"
                        )

        assert response.status_code == 200

        # Verify SSO identity was created linking to existing user
        mock_sso_repo.create_sso_identity.assert_called_once()
        call_kwargs = mock_sso_repo.create_sso_identity.call_args.kwargs
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["idp_user_id"] == "idp-user-456"

    def test_callback_rejects_link_with_unverified_email(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
        mock_sso_repo: MagicMock,
        mock_auth_repo: MagicMock,
        sso_config: SSOConfig,
        tenant_id: UUID,
        user_id: UUID,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Rejects account linking when IdP email is not verified."""
        private_key, public_key = rsa_keypair
        now = datetime.now(UTC)

        state = SSOState(
            state_id="test-state",
            nonce="test-nonce",
            org_id=tenant_id,
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=now,
        )
        mock_state_repo.validate_and_consume = AsyncMock(return_value=state)

        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)
        mock_sso_repo.get_sso_identity = AsyncMock(return_value=None)
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(return_value="client-secret")

        # Existing user exists
        existing_user = User(
            id=user_id,
            email="existing@acme.com",
            name="Existing User",
            is_active=True,
            created_at=now - timedelta(days=30),
        )
        mock_auth_repo.get_user_by_email = AsyncMock(return_value=existing_user)

        # ID token with UNVERIFIED email
        claims = {
            "sub": "idp-user-789",
            "email": "existing@acme.com",
            "email_verified": False,  # Not verified!
            "name": "Existing User",
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": "test-nonce",
        }
        id_token = create_signed_token(private_key, claims)

        with patch("dataing_ee.entrypoints.api.routes.sso.OIDCProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider_cls.return_value = mock_provider
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-123",
                    id_token=id_token,
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(return_value=claims)

            with patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_cls:
                mock_auth_repo_cls.return_value = mock_auth_repo

                response = client.get(
                    "/auth/sso/callback?code=auth-code&state=test-state"
                )

        assert response.status_code == 400
        assert "email not verified" in response.json()["detail"].lower()

    def test_callback_reuses_existing_sso_identity(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
        mock_sso_repo: MagicMock,
        sso_config: SSOConfig,
        tenant_id: UUID,
        user_id: UUID,
        config_id: UUID,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Subsequent SSO logins use existing identity link."""
        private_key, public_key = rsa_keypair
        now = datetime.now(UTC)

        state = SSOState(
            state_id="test-state",
            nonce="test-nonce",
            org_id=tenant_id,
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=now,
        )
        mock_state_repo.validate_and_consume = AsyncMock(return_value=state)

        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(return_value="client-secret")

        # Existing SSO identity link
        existing_identity = SSOIdentity(
            id=uuid4(),
            user_id=user_id,
            sso_config_id=config_id,
            idp_user_id="idp-user-123",
            created_at=now - timedelta(days=30),
        )
        mock_sso_repo.get_sso_identity = AsyncMock(return_value=existing_identity)
        mock_sso_repo.update_sso_identity_last_login = AsyncMock()

        # Create existing user to be returned by get_user_by_id
        existing_user = User(
            id=user_id,
            email="returning@acme.com",
            name="Returning User",
            is_active=True,
            created_at=now - timedelta(days=60),
        )

        claims = {
            "sub": "idp-user-123",
            "email": "returning@acme.com",
            "email_verified": True,
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": "test-nonce",
        }
        id_token = create_signed_token(private_key, claims)

        with patch("dataing_ee.entrypoints.api.routes.sso.OIDCProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider_cls.return_value = mock_provider
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-123",
                    id_token=id_token,
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(return_value=claims)

            with patch(
                "dataing_ee.entrypoints.api.routes.sso.PostgresAuthRepository"
            ) as mock_auth_repo_cls:
                mock_auth_repo = MagicMock()
                mock_auth_repo_cls.return_value = mock_auth_repo
                mock_auth_repo.get_user_by_id = AsyncMock(return_value=existing_user)
                mock_auth_repo.get_user_org_membership = AsyncMock(return_value=MagicMock())
                mock_auth_repo.get_user_teams = AsyncMock(return_value=[])

                with patch(
                    "dataing_ee.entrypoints.api.routes.sso.create_access_token"
                ) as mock_create_token:
                    mock_create_token.return_value = "jwt-access-token"

                    with patch(
                        "dataing_ee.entrypoints.api.routes.sso.create_refresh_token"
                    ) as mock_create_refresh:
                        mock_create_refresh.return_value = "jwt-refresh-token"

                        response = client.get(
                            "/auth/sso/callback?code=auth-code&state=test-state"
                        )

        assert response.status_code == 200

        # Verify no new identity was created
        mock_sso_repo.create_sso_identity.assert_not_called()

    def test_callback_rejects_invalid_id_token(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
        mock_sso_repo: MagicMock,
        sso_config: SSOConfig,
        tenant_id: UUID,
    ) -> None:
        """Rejects callback when ID token verification fails."""
        from dataing_ee.adapters.sso import InvalidSignatureError

        now = datetime.now(UTC)

        state = SSOState(
            state_id="test-state",
            nonce="test-nonce",
            org_id=tenant_id,
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=now,
        )
        mock_state_repo.validate_and_consume = AsyncMock(return_value=state)
        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(return_value="client-secret")

        with patch("dataing_ee.entrypoints.api.routes.sso.OIDCProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider_cls.return_value = mock_provider
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-123",
                    id_token="invalid-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(
                side_effect=InvalidSignatureError("Invalid signature")
            )

            response = client.get(
                "/auth/sso/callback?code=auth-code&state=test-state"
            )

        assert response.status_code == 400
        assert "token" in response.json()["detail"].lower()

    def test_callback_rejects_expired_id_token(
        self,
        client: TestClient,
        mock_state_repo: MagicMock,
        mock_sso_repo: MagicMock,
        sso_config: SSOConfig,
        tenant_id: UUID,
    ) -> None:
        """Rejects callback when ID token is expired."""
        from dataing_ee.adapters.sso import TokenExpiredError

        now = datetime.now(UTC)

        state = SSOState(
            state_id="test-state",
            nonce="test-nonce",
            org_id=tenant_id,
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=now,
        )
        mock_state_repo.validate_and_consume = AsyncMock(return_value=state)
        mock_sso_repo.get_sso_config = AsyncMock(return_value=sso_config)
        mock_sso_repo.get_decrypted_client_secret = AsyncMock(return_value="client-secret")

        with patch("dataing_ee.entrypoints.api.routes.sso.OIDCProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider_cls.return_value = mock_provider
            mock_provider.exchange_code = AsyncMock(
                return_value=OIDCTokens(
                    access_token="access-123",
                    id_token="expired-token",
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=None,
                )
            )
            mock_provider.verify_id_token = AsyncMock(
                side_effect=TokenExpiredError("ID token has expired")
            )

            response = client.get(
                "/auth/sso/callback?code=auth-code&state=test-state"
            )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()
