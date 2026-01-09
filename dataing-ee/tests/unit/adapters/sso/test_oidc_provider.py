"""Tests for OIDC provider."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dataing_ee.adapters.sso import OIDCConfig, OIDCProvider, OIDCTokens, OIDCUserInfo


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
