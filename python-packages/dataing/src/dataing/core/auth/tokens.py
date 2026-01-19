"""Secure token generation for password reset and other auth flows."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

# Token configuration
RESET_TOKEN_BYTES = 32  # 256 bits of entropy
RESET_TOKEN_EXPIRY_HOURS = 1


def generate_reset_token() -> str:
    """Generate a cryptographically secure reset token.

    Returns:
        URL-safe base64 encoded token string.
    """
    return secrets.token_urlsafe(RESET_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Hash a token for secure storage.

    Uses SHA-256 for fast lookup while maintaining security.
    The token itself has enough entropy that rainbow tables are infeasible.

    Args:
        token: The plaintext token to hash.

    Returns:
        Hex-encoded SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_token_expiry(hours: int = RESET_TOKEN_EXPIRY_HOURS) -> datetime:
    """Calculate token expiry timestamp.

    Args:
        hours: Number of hours until expiry.

    Returns:
        UTC datetime when the token expires.
    """
    return datetime.now(UTC) + timedelta(hours=hours)


def is_token_expired(expires_at: datetime) -> bool:
    """Check if a token has expired.

    Args:
        expires_at: The token's expiry timestamp.

    Returns:
        True if the token has expired.
    """
    now = datetime.now(UTC)
    # Handle timezone-naive datetimes
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return now > expires_at
