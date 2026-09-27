"""Git access tokens are encrypted at rest with the datasource encryption key."""

from __future__ import annotations

import pytest

from dataing.adapters.git.access_token import decrypt_access_token, encrypt_access_token

TOKEN = "ghp_s3cr3tT0ken"


@pytest.fixture(autouse=True)
def _key(encryption_key: bytes) -> None:
    """Encrypt every test's tokens with a fresh key."""


def test_stored_value_does_not_reveal_the_token() -> None:
    """The value written to the database is ciphertext, not the token."""
    assert TOKEN not in encrypt_access_token(TOKEN)


def test_stored_value_decrypts_to_the_token() -> None:
    """Readers get the original token back."""
    assert decrypt_access_token(encrypt_access_token(TOKEN)) == TOKEN


def test_value_not_encrypted_with_the_key_is_rejected() -> None:
    """A plaintext or foreign value fails loudly instead of being used as a token."""
    with pytest.raises(ValueError, match="could not be decrypted"):
        decrypt_access_token(TOKEN)
