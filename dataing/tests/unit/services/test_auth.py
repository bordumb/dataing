"""Unit tests for AuthService."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from dataing.services.auth import ApiKeyResult, AuthService


class TestAuthService:
    """Tests for AuthService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database."""
        mock = AsyncMock()
        mock.create_api_key.return_value = {
            "id": uuid.uuid4(),
            "name": "Test Key",
        }
        mock.list_api_keys.return_value = []
        mock.revoke_api_key.return_value = True
        return mock

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> AuthService:
        """Return an auth service."""
        return AuthService(db=mock_db)

    @pytest.fixture
    def tenant_id(self) -> uuid.UUID:
        """Return a sample tenant ID."""
        return uuid.uuid4()

    async def test_create_api_key_generates_key(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test that create_api_key generates a key."""
        result = await service.create_api_key(
            tenant_id=tenant_id,
            name="Test API Key",
        )

        assert isinstance(result, ApiKeyResult)
        assert result.key.startswith("ddr_")
        assert len(result.key) > 40  # Should be a secure length

    async def test_create_api_key_hashes_key(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test that create_api_key passes hashed key to DB."""
        await service.create_api_key(
            tenant_id=tenant_id,
            name="Test Key",
        )

        # Check that create_api_key was called with a hash
        call_kwargs = mock_db.create_api_key.call_args.kwargs
        assert "key_hash" in call_kwargs
        assert len(call_kwargs["key_hash"]) == 64  # SHA256 hex length

    async def test_create_api_key_with_scopes(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test creating API key with custom scopes."""
        result = await service.create_api_key(
            tenant_id=tenant_id,
            name="Read-Only Key",
            scopes=["read"],
        )

        assert result.scopes == ["read"]

    async def test_create_api_key_default_scopes(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test default scopes."""
        result = await service.create_api_key(
            tenant_id=tenant_id,
            name="Test Key",
        )

        assert result.scopes == ["read", "write"]

    async def test_create_api_key_with_expiration(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test creating API key with expiration."""
        result = await service.create_api_key(
            tenant_id=tenant_id,
            name="Expiring Key",
            expires_in_days=30,
        )

        assert result.expires_at is not None
        assert result.expires_at > datetime.now(timezone.utc)

    async def test_list_api_keys(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test listing API keys."""
        mock_db.list_api_keys.return_value = [
            {"id": uuid.uuid4(), "name": "Key 1"},
            {"id": uuid.uuid4(), "name": "Key 2"},
        ]

        result = await service.list_api_keys(tenant_id)

        assert len(result) == 2
        mock_db.list_api_keys.assert_called_once_with(tenant_id)

    async def test_revoke_api_key(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test revoking an API key."""
        key_id = uuid.uuid4()

        result = await service.revoke_api_key(key_id, tenant_id)

        assert result is True
        mock_db.revoke_api_key.assert_called_once_with(key_id, tenant_id)

    async def test_revoke_api_key_not_found(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test revoking non-existent API key."""
        mock_db.revoke_api_key.return_value = False
        key_id = uuid.uuid4()

        result = await service.revoke_api_key(key_id, tenant_id)

        assert result is False

    async def test_rotate_api_key(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test rotating an API key."""
        old_key_id = uuid.uuid4()
        mock_db.list_api_keys.return_value = [
            {
                "id": old_key_id,
                "name": "Old Key",
                "scopes": ["read", "write"],
            }
        ]

        result = await service.rotate_api_key(old_key_id, tenant_id)

        assert result is not None
        assert result.name == "Old Key (rotated)"
        mock_db.revoke_api_key.assert_called_once()

    async def test_rotate_api_key_not_found(
        self,
        service: AuthService,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test rotating non-existent API key."""
        mock_db.list_api_keys.return_value = []
        key_id = uuid.uuid4()

        result = await service.rotate_api_key(key_id, tenant_id)

        assert result is None


class TestApiKeyResult:
    """Tests for ApiKeyResult."""

    def test_create_result(self) -> None:
        """Test creating an API key result."""
        result = ApiKeyResult(
            id=uuid.uuid4(),
            key="ddr_test_key",
            key_prefix="ddr_test",
            name="Test Key",
            scopes=["read", "write"],
            expires_at=None,
        )

        assert result.key.startswith("ddr_")
        assert result.name == "Test Key"
