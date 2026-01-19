"""Shared fixtures for SSO adapter tests."""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from dataing_ee.core.sso.encryption import SSO_SECRET_KEY_ENV, clear_key_cache


@pytest.fixture(autouse=True)
def sso_encryption_key() -> str:
    """Set up SSO encryption key for all tests.

    This fixture automatically sets up a test encryption key
    for all SSO tests that use the encryption module.
    """
    test_key = Fernet.generate_key().decode()
    clear_key_cache()

    with patch.dict(os.environ, {SSO_SECRET_KEY_ENV: test_key}):
        yield test_key

    clear_key_cache()
