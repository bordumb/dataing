"""Encryption of git provider access tokens at rest.

Tokens are encrypted with the same key and scheme as datasource connection
configs, so one ENCRYPTION_KEY protects every stored credential.
"""

from __future__ import annotations

from cryptography.fernet import InvalidToken

from dataing.adapters.datasource.encryption import decrypt_config, encrypt_config

_TOKEN_FIELD = "access_token"


def encrypt_access_token(token: str) -> str:
    """Encrypt a git provider access token for storage.

    Args:
        token: The plaintext access token.

    Returns:
        Ciphertext for the git_repositories.access_token_encrypted column.
    """
    return encrypt_config({_TOKEN_FIELD: token})


def decrypt_access_token(encrypted: str) -> str:
    """Decrypt a stored git provider access token.

    Args:
        encrypted: The value of git_repositories.access_token_encrypted.

    Returns:
        The plaintext access token.

    Raises:
        ValueError: If the value was not encrypted with the current key, such
            as a token stored in plaintext before encryption was added.
    """
    try:
        token: str = decrypt_config(encrypted)[_TOKEN_FIELD]
    except InvalidToken:
        raise ValueError(
            "Stored git access token could not be decrypted; reconnect the repository"
        ) from None
    return token
