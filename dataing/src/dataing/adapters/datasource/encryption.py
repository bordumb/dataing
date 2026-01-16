"""Encryption utilities for datasource credentials.

This module provides encryption/decryption for datasource connection
configurations. Used by both API routes (when storing credentials) and
workers (when reconstructing adapters from stored configs).
"""

from __future__ import annotations

import json
import os
from typing import Any

from cryptography.fernet import Fernet

from dataing.core.json_utils import to_json_string


def get_encryption_key(*, allow_generation: bool = False) -> bytes:
    """Get the encryption key for datasource configs.

    Checks DATADR_ENCRYPTION_KEY first (used by demo), then ENCRYPTION_KEY.

    Args:
        allow_generation: If True and no key is set, generates one and sets
            ENCRYPTION_KEY. Only use this for local development - in production
            or distributed systems, all processes must share the same key.

    Returns:
        The encryption key as bytes.

    Raises:
        ValueError: If no key is set and allow_generation is False.
    """
    key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")

    if not key:
        if allow_generation:
            key = Fernet.generate_key().decode()
            os.environ["ENCRYPTION_KEY"] = key
        else:
            raise ValueError(
                "ENCRYPTION_KEY or DATADR_ENCRYPTION_KEY environment variable must be set. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

    return key.encode() if isinstance(key, str) else key


def encrypt_config(config: dict[str, Any], key: bytes | None = None) -> str:
    """Encrypt datasource configuration.

    Args:
        config: The configuration dictionary to encrypt.
        key: Optional encryption key. If not provided, fetches from environment.

    Returns:
        The encrypted configuration as a string.
    """
    if key is None:
        key = get_encryption_key()

    f = Fernet(key)
    encrypted = f.encrypt(to_json_string(config).encode())
    return encrypted.decode()


def decrypt_config(encrypted: str, key: bytes | None = None) -> dict[str, Any]:
    """Decrypt datasource configuration.

    Args:
        encrypted: The encrypted configuration string.
        key: Optional encryption key. If not provided, fetches from environment.

    Returns:
        The decrypted configuration dictionary.
    """
    if key is None:
        key = get_encryption_key()

    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode())
    result: dict[str, Any] = json.loads(decrypted.decode())
    return result
