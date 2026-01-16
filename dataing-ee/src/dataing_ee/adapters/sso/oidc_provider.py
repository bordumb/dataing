"""OIDC authentication provider."""

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient, PyJWKClientError

logger = logging.getLogger(__name__)


class SSOTokenError(Exception):
    """Base exception for SSO token errors."""

    pass


class InvalidSignatureError(SSOTokenError):
    """Raised when JWT signature verification fails."""

    pass


class InvalidClaimsError(SSOTokenError):
    """Raised when JWT claims validation fails."""

    pass


class TokenExpiredError(SSOTokenError):
    """Raised when JWT has expired."""

    pass


@dataclass
class JWKSCache:
    """Cache for JWKS keys with configurable TTL."""

    client: PyJWKClient | None = None
    last_fetch: float = 0.0
    ttl_seconds: int = 3600  # 1 hour default

    def is_expired(self) -> bool:
        """Check if cache has expired."""
        return time.time() - self.last_fetch > self.ttl_seconds


@dataclass
class OIDCConfig:
    """OIDC provider configuration."""

    issuer_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] | None = None
    jwks_cache_ttl_seconds: int = 3600  # 1 hour default

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
        self._jwks_cache = JWKSCache(ttl_seconds=config.jwks_cache_ttl_seconds)

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

    async def _get_jwks_client(self) -> PyJWKClient:
        """Get or create JWKS client with caching.

        Returns:
            PyJWKClient configured for the IdP's JWKS endpoint.
        """
        if self._jwks_cache.client and not self._jwks_cache.is_expired():
            return self._jwks_cache.client

        discovery = await self.get_discovery()
        jwks_uri = discovery.get("jwks_uri")
        if not jwks_uri:
            msg = "JWKS URI not found in discovery document"
            raise InvalidClaimsError(msg)

        self._jwks_cache.client = PyJWKClient(jwks_uri, cache_keys=True)
        self._jwks_cache.last_fetch = time.time()
        return self._jwks_cache.client

    async def verify_id_token(
        self,
        id_token: str,
        nonce: str | None = None,
    ) -> dict[str, Any]:
        """Verify ID token signature and validate claims.

        Args:
            id_token: JWT ID token from IdP.
            nonce: Expected nonce value for replay protection.

        Returns:
            Verified token claims as dictionary.

        Raises:
            InvalidSignatureError: If signature verification fails.
            InvalidClaimsError: If claims validation fails.
            TokenExpiredError: If token has expired.
        """
        try:
            jwks_client = await self._get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        except PyJWKClientError as e:
            # Handle key rotation - try refetching JWKS
            logger.warning(f"JWKS key lookup failed, refetching: {e}")
            self._jwks_cache.last_fetch = 0  # Force cache expiry
            try:
                jwks_client = await self._get_jwks_client()
                signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            except PyJWKClientError as e2:
                raise InvalidSignatureError(f"Failed to get signing key: {e2}") from e2

        try:
            claims: dict[str, Any] = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                audience=self._config.client_id,
                issuer=self._config.issuer_url,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "require": ["exp", "iat", "iss", "aud", "sub"],
                },
            )
        except jwt.ExpiredSignatureError as e:
            raise TokenExpiredError("ID token has expired") from e
        except jwt.InvalidAudienceError as e:
            raise InvalidClaimsError(f"Invalid audience: {e}") from e
        except jwt.InvalidIssuerError as e:
            raise InvalidClaimsError(f"Invalid issuer: {e}") from e
        except jwt.InvalidSignatureError as e:
            raise InvalidSignatureError(f"Invalid signature: {e}") from e
        except jwt.PyJWTError as e:
            raise InvalidClaimsError(f"Token validation failed: {e}") from e

        # Validate nonce if provided
        if nonce is not None:
            token_nonce = claims.get("nonce")
            if token_nonce != nonce:
                raise InvalidClaimsError(
                    f"Nonce mismatch: expected '{nonce}', got '{token_nonce}'"
                )

        return claims

    def parse_id_token_claims(self, id_token: str) -> dict[str, Any]:
        """Parse claims from ID token WITHOUT verification.

        WARNING: This method does NOT verify the token signature.
        Use verify_id_token() for production code.

        Args:
            id_token: JWT ID token.

        Returns:
            Token claims as dictionary (unverified).

        Raises:
            ValueError: If token format is invalid.
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
