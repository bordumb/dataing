"""Tests for SSO encryption module."""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from dataing_ee.core.sso.encryption import (
    SSO_SECRET_KEY_ENV,
    EncryptionError,
    MissingEncryptionKeyError,
    clear_key_cache,
    decrypt_secret,
    encrypt_secret,
    generate_key,
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """Clear encryption key cache before each test."""
    clear_key_cache()


@pytest.fixture
def test_key() -> str:
    """Generate a test encryption key."""
    return Fernet.generate_key().decode()


class TestEncryptDecrypt:
    """Tests for encrypt_secret and decrypt_secret."""

    def test_encrypt_decrypt_roundtrip(self, test_key: str) -> None:
        """Encrypts and decrypts a secret successfully."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            plaintext = "my-super-secret-client-secret"

            encrypted = encrypt_secret(plaintext)
            decrypted = decrypt_secret(encrypted)

            assert decrypted == plaintext
            assert encrypted != plaintext.encode()

    def test_encrypt_produces_different_ciphertext(self, test_key: str) -> None:
        """Each encryption produces different ciphertext (due to random IV)."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            plaintext = "my-secret"

            encrypted1 = encrypt_secret(plaintext)
            encrypted2 = encrypt_secret(plaintext)

            assert encrypted1 != encrypted2
            # But both decrypt to same value
            assert decrypt_secret(encrypted1) == decrypt_secret(encrypted2)

    def test_encrypt_empty_string(self, test_key: str) -> None:
        """Encrypting empty string returns empty bytes."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            encrypted = encrypt_secret("")
            assert encrypted == b""

    def test_decrypt_empty_bytes(self, test_key: str) -> None:
        """Decrypting empty bytes returns empty string."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            decrypted = decrypt_secret(b"")
            assert decrypted == ""


class TestMissingKey:
    """Tests for missing encryption key."""

    def test_encrypt_without_key_raises(self) -> None:
        """Encrypting without key raises MissingEncryptionKeyError."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure key is not set
            os.environ.pop(SSO_SECRET_KEY_ENV, None)
            clear_key_cache()

            with pytest.raises(MissingEncryptionKeyError) as exc_info:
                encrypt_secret("secret")

            assert SSO_SECRET_KEY_ENV in str(exc_info.value)

    def test_decrypt_without_key_raises(self) -> None:
        """Decrypting without key raises MissingEncryptionKeyError."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(SSO_SECRET_KEY_ENV, None)
            clear_key_cache()

            with pytest.raises(MissingEncryptionKeyError):
                decrypt_secret(b"some-ciphertext")


class TestInvalidKey:
    """Tests for invalid encryption key."""

    def test_invalid_key_format_raises(self) -> None:
        """Invalid key format raises EncryptionError."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: "not-a-valid-fernet-key"}):
            with pytest.raises(EncryptionError, match="Invalid encryption key"):
                encrypt_secret("secret")


class TestDecryptionFailures:
    """Tests for decryption failures."""

    def test_decrypt_with_wrong_key(self, test_key: str) -> None:
        """Decrypting with wrong key raises EncryptionError."""
        wrong_key = Fernet.generate_key().decode()

        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            encrypted = encrypt_secret("secret")

        clear_key_cache()

        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: wrong_key}):
            with pytest.raises(EncryptionError, match="invalid token or wrong key"):
                decrypt_secret(encrypted)

    def test_decrypt_corrupted_data(self, test_key: str) -> None:
        """Decrypting corrupted data raises EncryptionError."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            with pytest.raises(EncryptionError):
                decrypt_secret(b"this-is-not-a-fernet-token")


class TestGenerateKey:
    """Tests for generate_key."""

    def test_generates_valid_key(self) -> None:
        """Generates a valid Fernet key."""
        key = generate_key()

        # Key should be URL-safe base64
        assert isinstance(key, str)
        assert len(key) == 44  # Fernet keys are 44 chars base64

        # Key should work for encryption
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: key}):
            clear_key_cache()
            encrypted = encrypt_secret("test")
            assert decrypt_secret(encrypted) == "test"

    def test_generates_unique_keys(self) -> None:
        """Each call generates a unique key."""
        key1 = generate_key()
        key2 = generate_key()

        assert key1 != key2


class TestCaching:
    """Tests for key caching."""

    def test_key_is_cached(self, test_key: str) -> None:
        """Fernet instance is cached."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            # First call caches the key
            encrypt_secret("test1")

            # Changing env var doesn't affect cached key
            with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: "different-key"}):
                # This should still work because key is cached
                encrypted = encrypt_secret("test2")
                assert decrypt_secret(encrypted) == "test2"

    def test_cache_clear_reloads_key(self, test_key: str) -> None:
        """Clearing cache reloads the key."""
        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
            encrypt_secret("test")

            # Clear cache and set invalid key
            clear_key_cache()

        with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: "invalid"}):
            # Now it should try to load the new (invalid) key
            with pytest.raises(EncryptionError):
                encrypt_secret("test2")
