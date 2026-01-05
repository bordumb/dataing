"""JWT token creation and validation."""

import os
from datetime import datetime, timedelta, timezone

import jwt

from dataing.core.auth.types import TokenPayload


class TokenError(Exception):
    """Raised when token validation fails."""

    pass


# Configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


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
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "teams": teams,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token.

    Args:
        user_id: User identifier

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
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

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token.

    Args:
        token: Encoded JWT string

    Returns:
        Decoded token payload

    Raises:
        TokenError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
