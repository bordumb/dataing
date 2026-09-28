"""JWT token creation and validation."""

import os
from datetime import UTC, datetime, timedelta

import jwt

from dataing.core.auth.types import TokenPayload


class TokenError(Exception):
    """Raised when token validation fails."""

    pass


class JWTSecretKeyError(RuntimeError):
    """Raised when JWT_SECRET_KEY is missing or too short to sign tokens safely."""


# Configuration
JWT_SECRET_KEY_ENV = "JWT_SECRET_KEY"  # pragma: allowlist secret
# HS256 wants a key at least as long as its 32-byte hash output (RFC 7518, section 3.2)
MIN_SECRET_KEY_BYTES = 32
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7


def jwt_secret_key() -> str:
    """Return the key that signs and verifies JWTs.

    There is deliberately no built-in fallback: a key that ships in the source lets
    anyone who reads it forge tokens for any user, org and role.

    Returns:
        The JWT_SECRET_KEY environment variable.

    Raises:
        JWTSecretKeyError: If JWT_SECRET_KEY is unset or shorter than 32 bytes.
    """
    key = os.environ.get(JWT_SECRET_KEY_ENV, "")
    size = len(key.encode())
    if size < MIN_SECRET_KEY_BYTES:
        problem = "is not set" if not key else f"is only {size} bytes"
        raise JWTSecretKeyError(
            f"{JWT_SECRET_KEY_ENV} {problem}; it must be at least {MIN_SECRET_KEY_BYTES} "
            "random bytes. Generate one with: openssl rand -hex 32"
        )
    return key


def create_access_token(
    user_id: str,
    org_id: str,
    role: str,
    teams: list[str],
) -> str:
    """Create a short-lived access token.

    Args:
        user_id: User identifier
        org_id: Organization identifier
        role: User's role in the org
        teams: List of team IDs user belongs to

    Returns:
        Encoded JWT string
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "teams": teams,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }

    return jwt.encode(payload, jwt_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token.

    Args:
        user_id: User identifier

    Returns:
        Encoded JWT string
    """
    now = datetime.now(UTC)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "org_id": "",  # Refresh tokens don't carry org context
        "role": "",
        "teams": [],
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "refresh",
    }

    return jwt.encode(payload, jwt_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token.

    Args:
        token: Encoded JWT string

    Returns:
        Decoded token payload

    Raises:
        TokenError: If token is invalid or expired
        JWTSecretKeyError: If JWT_SECRET_KEY is missing or too short
    """
    try:
        payload = jwt.decode(token, jwt_secret_key(), algorithms=[ALGORITHM])
        return TokenPayload(
            sub=payload["sub"],
            org_id=payload["org_id"],
            role=payload["role"],
            teams=payload["teams"],
            exp=payload["exp"],
            iat=payload["iat"],
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired") from None
    except jwt.InvalidTokenError as e:
        raise TokenError(f"Invalid token: {e}") from None
