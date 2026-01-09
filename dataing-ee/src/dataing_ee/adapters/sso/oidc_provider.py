"""OIDC authentication provider."""

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OIDCConfig:
    """OIDC provider configuration."""

    issuer_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] | None = None

    @property
    def default_scopes(self) -> list[str]:
        """Default OIDC scopes."""
        return self.scopes or ["openid", "email", "profile"]


@dataclass
class OIDCUserInfo:
    """User information from OIDC provider."""

    sub: str  # Unique user ID at IdP
    email: str
    email_verified: bool = False
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    groups: list[str] | None = None


@dataclass
class OIDCTokens:
    """Tokens from OIDC provider."""

    access_token: str
    id_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None


class OIDCProvider:
    """OIDC authentication provider.

    Handles OAuth2/OIDC flow:
    1. Generate authorization URL
    2. Exchange code for tokens
    3. Validate and extract user info from ID token
    """

    def __init__(self, config: OIDCConfig) -> None:
        """Initialize the provider.

        Args:
            config: OIDC configuration.
        """
        self._config = config
        self._discovery: dict[str, Any] | None = None

    async def get_discovery(self) -> dict[str, Any]:
        """Fetch OIDC discovery document.

        Returns:
            Discovery document with endpoints.
        """
        if self._discovery:
            return self._discovery

        discovery_url = f"{self._config.issuer_url.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            self._discovery = response.json()

        return self._discovery

    async def get_authorization_url(self, state: str, nonce: str) -> str:
        """Generate authorization URL for user redirect.

        Args:
            state: State parameter for CSRF protection.
            nonce: Nonce for ID token replay protection.

        Returns:
            Authorization URL to redirect user to.
        """
        discovery = await self.get_discovery()
        auth_endpoint = discovery["authorization_endpoint"]

        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "scope": " ".join(self._config.default_scopes),
            "state": state,
            "nonce": nonce,
        }

        return f"{auth_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OIDCTokens:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from IdP callback.

        Returns:
            Token response with access_token, id_token, etc.

        Raises:
            httpx.HTTPStatusError: If token exchange fails.
        """
        discovery = await self.get_discovery()
        token_endpoint = discovery["token_endpoint"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                },
            )
            response.raise_for_status()
            data = response.json()

        return OIDCTokens(
            access_token=data["access_token"],
            id_token=data["id_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in", 3600),
            refresh_token=data.get("refresh_token"),
        )

    async def get_user_info(self, access_token: str) -> OIDCUserInfo:
        """Fetch user info from userinfo endpoint.

        Args:
            access_token: Access token from token exchange.

        Returns:
            User information from IdP.

        Raises:
            httpx.HTTPStatusError: If userinfo request fails.
        """
        discovery = await self.get_discovery()
        userinfo_endpoint = discovery["userinfo_endpoint"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

        return OIDCUserInfo(
            sub=data["sub"],
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            name=data.get("name"),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
            groups=data.get("groups"),
        )

    def parse_id_token_claims(self, id_token: str) -> dict[str, Any]:
        """Parse claims from ID token (without verification).

        Note: In production, use a proper JWT library to verify
        the token signature and validate claims.

        Args:
            id_token: JWT ID token.

        Returns:
            Token claims as dictionary.
        """
        import base64
        import json

        # Split token into parts
        parts = id_token.split(".")
        if len(parts) != 3:
            msg = "Invalid ID token format"
            raise ValueError(msg)

        # Decode payload (middle part)
        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        decoded = base64.urlsafe_b64decode(payload)
        claims: dict[str, Any] = json.loads(decoded)
        return claims
