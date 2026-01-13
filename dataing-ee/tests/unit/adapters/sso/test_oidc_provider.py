"""Tests for OIDC provider."""

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dataing_ee.adapters.sso import (
    InvalidClaimsError,
    InvalidSignatureError,
    OIDCConfig,
    OIDCProvider,
    OIDCTokens,
    OIDCUserInfo,
    TokenExpiredError,
)


@pytest.fixture
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate RSA key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def oidc_config() -> OIDCConfig:
    """Create test OIDC configuration."""
    return OIDCConfig(
        issuer_url="https://idp.example.com",
        client_id="test-client-id",
        client_secret="test-client-secret",  # pragma: allowlist secret
        redirect_uri="https://app.example.com/callback",
    )


@pytest.fixture
def provider(oidc_config: OIDCConfig) -> OIDCProvider:
    """Create OIDC provider with test config."""
    return OIDCProvider(oidc_config)


@pytest.fixture
def mock_discovery() -> dict:
    """Mock OIDC discovery document."""
    return {
        "authorization_endpoint": "https://idp.example.com/authorize",
        "token_endpoint": "https://idp.example.com/token",
        "userinfo_endpoint": "https://idp.example.com/userinfo",
        "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        "issuer": "https://idp.example.com",
    }


class TestOIDCConfig:
    """Tests for OIDCConfig."""

    def test_default_scopes(self, oidc_config: OIDCConfig) -> None:
        """Returns default scopes when none specified."""
        assert oidc_config.default_scopes == ["openid", "email", "profile"]

    def test_custom_scopes(self) -> None:
        """Uses custom scopes when specified."""
        config = OIDCConfig(
            issuer_url="https://idp.example.com",
            client_id="test",
            client_secret="test",  # pragma: allowlist secret
            redirect_uri="https://app.example.com/callback",
            scopes=["openid", "groups"],
        )
        assert config.default_scopes == ["openid", "groups"]


class TestOIDCProvider:
    """Tests for OIDCProvider."""

    def test_can_instantiate(self, oidc_config: OIDCConfig) -> None:
        """Can create provider with config."""
        provider = OIDCProvider(oidc_config)
        assert provider._config.client_id == "test-client-id"


class TestGetAuthorizationUrl:
    """Tests for get_authorization_url method."""

    async def test_builds_auth_url(self, provider: OIDCProvider, mock_discovery: dict) -> None:
        """Builds correct authorization URL."""
        provider._discovery = mock_discovery

        url = await provider.get_authorization_url(state="test-state", nonce="test-nonce")

        assert "https://idp.example.com/authorize?" in url
        assert "response_type=code" in url
        assert "client_id=test-client-id" in url
        assert "state=test-state" in url
        assert "nonce=test-nonce" in url
        assert "scope=openid+email+profile" in url


class TestExchangeCode:
    """Tests for exchange_code method."""

    async def test_exchanges_code_for_tokens(
        self, provider: OIDCProvider, mock_discovery: dict
    ) -> None:
        """Exchanges code for tokens."""
        provider._discovery = mock_discovery

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "access-123",
            "id_token": "id-token-123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "refresh-123",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            tokens = await provider.exchange_code("auth-code-123")

        assert isinstance(tokens, OIDCTokens)
        assert tokens.access_token == "access-123"
        assert tokens.id_token == "id-token-123"
        assert tokens.refresh_token == "refresh-123"


class TestGetUserInfo:
    """Tests for get_user_info method."""

    async def test_fetches_user_info(self, provider: OIDCProvider, mock_discovery: dict) -> None:
        """Fetches user info from userinfo endpoint."""
        provider._discovery = mock_discovery

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sub": "user-123",
            "email": "alice@example.com",
            "email_verified": True,
            "name": "Alice Smith",
            "given_name": "Alice",
            "family_name": "Smith",
            "groups": ["Engineering", "Admins"],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            user_info = await provider.get_user_info("access-token-123")

        assert isinstance(user_info, OIDCUserInfo)
        assert user_info.sub == "user-123"
        assert user_info.email == "alice@example.com"
        assert user_info.email_verified is True
        assert user_info.groups == ["Engineering", "Admins"]


class TestParseIdTokenClaims:
    """Tests for parse_id_token_claims method."""

    def test_parses_valid_token(self, provider: OIDCProvider) -> None:
        """Parses claims from valid JWT."""
        # Create a mock JWT with claims
        claims = {"sub": "user-123", "email": "alice@example.com", "nonce": "test-nonce"}
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        # JWT format: header.payload.signature
        mock_token = f"eyJ0eXAiOiJKV1QifQ.{payload}.fake-signature"

        parsed = provider.parse_id_token_claims(mock_token)

        assert parsed["sub"] == "user-123"
        assert parsed["email"] == "alice@example.com"

    def test_raises_on_invalid_token(self, provider: OIDCProvider) -> None:
        """Raises error for invalid token format."""
        with pytest.raises(ValueError, match="Invalid ID token format"):
            provider.parse_id_token_claims("not-a-valid-token")


class TestVerifyIdToken:
    """Tests for verify_id_token method."""

    def _create_signed_token(
        self,
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

    async def test_verifies_valid_token(
        self,
        provider: OIDCProvider,
        mock_discovery: dict,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Verifies a properly signed token with valid claims."""
        private_key, public_key = rsa_keypair
        provider._discovery = mock_discovery

        now = datetime.now(UTC)
        claims = {
            "sub": "user-123",
            "email": "alice@example.com",
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": "test-nonce",
        }
        token = self._create_signed_token(private_key, claims)

        # Mock the JWKS client
        mock_signing_key = MagicMock()
        mock_signing_key.key = public_key

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch.object(provider, "_get_jwks_client", return_value=mock_jwks_client):
            verified_claims = await provider.verify_id_token(token, nonce="test-nonce")

        assert verified_claims["sub"] == "user-123"
        assert verified_claims["email"] == "alice@example.com"

    async def test_rejects_expired_token(
        self,
        provider: OIDCProvider,
        mock_discovery: dict,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Rejects token that has expired."""
        private_key, public_key = rsa_keypair
        provider._discovery = mock_discovery

        now = datetime.now(UTC)
        claims = {
            "sub": "user-123",
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now - timedelta(hours=1)).timestamp()),  # Expired
            "iat": int((now - timedelta(hours=2)).timestamp()),
        }
        token = self._create_signed_token(private_key, claims)

        mock_signing_key = MagicMock()
        mock_signing_key.key = public_key

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch.object(provider, "_get_jwks_client", return_value=mock_jwks_client):
            with pytest.raises(TokenExpiredError, match="ID token has expired"):
                await provider.verify_id_token(token)

    async def test_rejects_wrong_issuer(
        self,
        provider: OIDCProvider,
        mock_discovery: dict,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Rejects token from wrong issuer."""
        private_key, public_key = rsa_keypair
        provider._discovery = mock_discovery

        now = datetime.now(UTC)
        claims = {
            "sub": "user-123",
            "iss": "https://wrong-issuer.com",  # Wrong issuer
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
        }
        token = self._create_signed_token(private_key, claims)

        mock_signing_key = MagicMock()
        mock_signing_key.key = public_key

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch.object(provider, "_get_jwks_client", return_value=mock_jwks_client):
            with pytest.raises(InvalidClaimsError, match="Invalid issuer"):
                await provider.verify_id_token(token)

    async def test_rejects_wrong_audience(
        self,
        provider: OIDCProvider,
        mock_discovery: dict,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Rejects token for wrong audience."""
        private_key, public_key = rsa_keypair
        provider._discovery = mock_discovery

        now = datetime.now(UTC)
        claims = {
            "sub": "user-123",
            "iss": "https://idp.example.com",
            "aud": "wrong-client-id",  # Wrong audience
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
        }
        token = self._create_signed_token(private_key, claims)

        mock_signing_key = MagicMock()
        mock_signing_key.key = public_key

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch.object(provider, "_get_jwks_client", return_value=mock_jwks_client):
            with pytest.raises(InvalidClaimsError, match="Invalid audience"):
                await provider.verify_id_token(token)

    async def test_rejects_nonce_mismatch(
        self,
        provider: OIDCProvider,
        mock_discovery: dict,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Rejects token with nonce mismatch."""
        private_key, public_key = rsa_keypair
        provider._discovery = mock_discovery

        now = datetime.now(UTC)
        claims = {
            "sub": "user-123",
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": "token-nonce",  # Different from expected
        }
        token = self._create_signed_token(private_key, claims)

        mock_signing_key = MagicMock()
        mock_signing_key.key = public_key

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch.object(provider, "_get_jwks_client", return_value=mock_jwks_client):
            with pytest.raises(InvalidClaimsError, match="Nonce mismatch"):
                await provider.verify_id_token(token, nonce="expected-nonce")

    async def test_rejects_invalid_signature(
        self,
        provider: OIDCProvider,
        mock_discovery: dict,
        rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    ) -> None:
        """Rejects token with invalid signature."""
        private_key, public_key = rsa_keypair
        provider._discovery = mock_discovery

        # Create a token signed with one key
        now = datetime.now(UTC)
        claims = {
            "sub": "user-123",
            "iss": "https://idp.example.com",
            "aud": "test-client-id",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
        }
        token = self._create_signed_token(private_key, claims)

        # But verify with a different key
        different_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        ).public_key()

        mock_signing_key = MagicMock()
        mock_signing_key.key = different_key

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch.object(provider, "_get_jwks_client", return_value=mock_jwks_client):
            with pytest.raises(InvalidSignatureError, match="Invalid signature"):
                await provider.verify_id_token(token)


class TestJWKSCaching:
    """Tests for JWKS client caching."""

    async def test_caches_jwks_client(
        self,
        provider: OIDCProvider,
        mock_discovery: dict,
    ) -> None:
        """Reuses cached JWKS client within TTL."""
        provider._discovery = mock_discovery

        with patch("dataing_ee.adapters.sso.oidc_provider.PyJWKClient") as mock_client:
            # First call creates client
            await provider._get_jwks_client()
            assert mock_client.call_count == 1

            # Second call within TTL reuses client
            await provider._get_jwks_client()
            assert mock_client.call_count == 1  # Still 1

    async def test_refetches_after_ttl_expires(
        self,
        oidc_config: OIDCConfig,
        mock_discovery: dict,
    ) -> None:
        """Creates new JWKS client after TTL expires."""
        # Use short TTL for testing
        config = OIDCConfig(
            issuer_url=oidc_config.issuer_url,
            client_id=oidc_config.client_id,
            client_secret=oidc_config.client_secret,
            redirect_uri=oidc_config.redirect_uri,
            jwks_cache_ttl_seconds=0,  # Immediate expiry
        )
        provider = OIDCProvider(config)
        provider._discovery = mock_discovery

        with patch("dataing_ee.adapters.sso.oidc_provider.PyJWKClient") as mock_client:
            # First call creates client
            await provider._get_jwks_client()
            assert mock_client.call_count == 1

            # Second call after TTL creates new client
            await provider._get_jwks_client()
            assert mock_client.call_count == 2
