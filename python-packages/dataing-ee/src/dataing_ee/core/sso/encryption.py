"""Encryption utilities for SSO secrets.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).
"""

import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Environment variable for encryption key
SSO_SECRET_KEY_ENV = "SSO_SECRET_KEY"  # pragma: allowlist secret


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""

    pass


class MissingEncryptionKeyError(EncryptionError):
    """Raised when encryption key is not configured."""

    pass


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Get Fernet instance with encryption key from environment.

    Returns:
        Fernet instance for encryption/decryption.

    Raises:
        MissingEncryptionKeyError: If SSO_SECRET_KEY is not set.
        EncryptionError: If the key is invalid.
    """
    key = os.environ.get(SSO_SECRET_KEY_ENV)
    if not key:
        msg = (
            f"SSO encryption key not configured. "
            f"Set {SSO_SECRET_KEY_ENV} environment variable. "
            f"Generate a key with: python -c "
            f'"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
        raise MissingEncryptionKeyError(msg)

    try:
        return Fernet(key.encode())
    except ValueError as e:
        raise EncryptionError(f"Invalid encryption key format: {e}") from e


def encrypt_secret(plaintext: str) -> bytes:
    """Encrypt a secret string.

    Args:
        plaintext: The secret to encrypt.

    Returns:
        Encrypted bytes (Fernet token).

    Raises:
        MissingEncryptionKeyError: If encryption key is not configured.
        EncryptionError: If encryption fails.
    """
    if not plaintext:
        return b""

    try:
        fernet = _get_fernet()
        return fernet.encrypt(plaintext.encode())
    except MissingEncryptionKeyError:
        raise
    except Exception as e:
        raise EncryptionError(f"Encryption failed: {e}") from e


def decrypt_secret(ciphertext: bytes) -> str:
    """Decrypt an encrypted secret.

    Args:
        ciphertext: The encrypted bytes to decrypt.

    Returns:
        Decrypted plaintext string.

    Raises:
        MissingEncryptionKeyError: If encryption key is not configured.
        EncryptionError: If decryption fails (invalid token, wrong key, etc.).
    """
    if not ciphertext:
        return ""

    try:
        fernet = _get_fernet()
        return fernet.decrypt(ciphertext).decode()
    except MissingEncryptionKeyError:
        raise
    except InvalidToken as e:
        raise EncryptionError("Decryption failed: invalid token or wrong key") from e
    except Exception as e:
        raise EncryptionError(f"Decryption failed: {e}") from e


def generate_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        URL-safe base64 encoded key string.
    """
    return Fernet.generate_key().decode()


def clear_key_cache() -> None:
    """Clear the cached Fernet instance.

    Useful for testing or key rotation.
    """
    _get_fernet.cache_clear()
