"""API key related fixtures."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def sample_api_key() -> str:
    """Return a sample API key."""
    return "ddr_test_api_key_12345678901234567890"


@pytest.fixture
def sample_api_key_hash(sample_api_key: str) -> str:
    """Return the SHA256 hash of the sample API key."""
    return hashlib.sha256(sample_api_key.encode()).hexdigest()


@pytest.fixture
def sample_tenant_id() -> uuid.UUID:
    """Return a sample tenant UUID."""
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """Return a sample user UUID."""
    return uuid.UUID("87654321-4321-8765-4321-876543218765")


@pytest.fixture
def sample_api_key_record(
    sample_api_key: str,
    sample_tenant_id: uuid.UUID,
) -> dict:
    """Return a sample API key database record."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": sample_tenant_id,
        "user_id": None,
        "key_hash": hashlib.sha256(sample_api_key.encode()).hexdigest(),
        "key_prefix": sample_api_key[:8],
        "name": "Test API Key",
        "scopes": ["read", "write"],
        "is_active": True,
        "last_used_at": None,
        "expires_at": None,
        "created_at": datetime.now(timezone.utc),
        "tenant_slug": "test-tenant",
        "tenant_name": "Test Tenant",
    }


@pytest.fixture
def expired_api_key_record(sample_api_key_record: dict) -> dict:
    """Return an expired API key database record."""
    record = sample_api_key_record.copy()
    record["expires_at"] = datetime.now(timezone.utc) - timedelta(days=1)
    return record
