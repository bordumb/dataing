"""Unit tests for auth middleware."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    optional_api_key,
    require_scope,
    verify_api_key,
)


class TestVerifyApiKey:
    """Tests for verify_api_key."""

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Return a mock request."""
        request = MagicMock()
        request.app.state.db = AsyncMock()
        return request

    @pytest.fixture
    def sample_api_key(self) -> str:
        """Return a sample API key."""
        return "ddr_test_key_12345678901234567890"

    @pytest.fixture
    def sample_api_key_record(self, sample_api_key: str) -> dict:
        """Return a sample API key record."""
        return {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "user_id": None,
            "key_hash": hashlib.sha256(sample_api_key.encode()).hexdigest(),
            "name": "Test Key",
            "scopes": ["read", "write"],
            "expires_at": None,
            "tenant_slug": "test-tenant",
            "tenant_name": "Test Tenant",
        }

    async def test_verify_missing_api_key(self, mock_request: MagicMock) -> None:
        """Test that missing API key raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request, api_key=None)

        assert exc_info.value.status_code == 401
        assert "Missing" in exc_info.value.detail

    async def test_verify_invalid_api_key(
        self,
        mock_request: MagicMock,
    ) -> None:
        """Test that invalid API key raises 401."""
        mock_request.app.state.db.get_api_key_by_hash.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request, api_key="invalid_key")

        assert exc_info.value.status_code == 401
        assert "Invalid" in exc_info.value.detail

    async def test_verify_expired_api_key(
        self,
        mock_request: MagicMock,
        sample_api_key: str,
        sample_api_key_record: dict,
    ) -> None:
        """Test that expired API key raises 401."""
        sample_api_key_record["expires_at"] = datetime.now(timezone.utc) - timedelta(days=1)
        mock_request.app.state.db.get_api_key_by_hash.return_value = sample_api_key_record

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request, api_key=sample_api_key)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail

    async def test_verify_valid_api_key(
        self,
        mock_request: MagicMock,
        sample_api_key: str,
        sample_api_key_record: dict,
    ) -> None:
        """Test that valid API key returns context."""
        mock_request.app.state.db.get_api_key_by_hash.return_value = sample_api_key_record
        mock_request.app.state.db.update_api_key_last_used.return_value = None

        result = await verify_api_key(mock_request, api_key=sample_api_key)

        assert isinstance(result, ApiKeyContext)
        assert result.key_id == sample_api_key_record["id"]
        assert result.tenant_id == sample_api_key_record["tenant_id"]
        assert result.scopes == ["read", "write"]

    async def test_verify_stores_context_in_request(
        self,
        mock_request: MagicMock,
        sample_api_key: str,
        sample_api_key_record: dict,
    ) -> None:
        """Test that context is stored in request state."""
        mock_request.app.state.db.get_api_key_by_hash.return_value = sample_api_key_record
        mock_request.state = MagicMock()

        result = await verify_api_key(mock_request, api_key=sample_api_key)

        assert mock_request.state.auth_context == result

    async def test_verify_updates_last_used(
        self,
        mock_request: MagicMock,
        sample_api_key: str,
        sample_api_key_record: dict,
    ) -> None:
        """Test that last_used_at is updated."""
        mock_request.app.state.db.get_api_key_by_hash.return_value = sample_api_key_record

        await verify_api_key(mock_request, api_key=sample_api_key)

        mock_request.app.state.db.update_api_key_last_used.assert_called_once_with(
            sample_api_key_record["id"]
        )

    async def test_verify_handles_last_used_error(
        self,
        mock_request: MagicMock,
        sample_api_key: str,
        sample_api_key_record: dict,
    ) -> None:
        """Test that last_used update failure doesn't fail auth."""
        mock_request.app.state.db.get_api_key_by_hash.return_value = sample_api_key_record
        mock_request.app.state.db.update_api_key_last_used.side_effect = Exception("DB error")

        # Should not raise
        result = await verify_api_key(mock_request, api_key=sample_api_key)
        assert result is not None


class TestRequireScope:
    """Tests for require_scope."""

    @pytest.fixture
    def read_only_context(self) -> ApiKeyContext:
        """Return a read-only API key context."""
        return ApiKeyContext(
            key_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_slug="test",
            tenant_name="Test",
            user_id=None,
            scopes=["read"],
        )

    @pytest.fixture
    def full_access_context(self) -> ApiKeyContext:
        """Return a full access API key context."""
        return ApiKeyContext(
            key_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_slug="test",
            tenant_name="Test",
            user_id=None,
            scopes=["read", "write"],
        )

    @pytest.fixture
    def admin_context(self) -> ApiKeyContext:
        """Return an admin API key context."""
        return ApiKeyContext(
            key_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_slug="test",
            tenant_name="Test",
            user_id=None,
            scopes=["*"],
        )

    async def test_require_scope_passes_with_scope(
        self,
        full_access_context: ApiKeyContext,
    ) -> None:
        """Test that having required scope passes."""
        checker = require_scope("write")

        # Mock the dependency injection
        result = await checker(auth=full_access_context)

        assert result == full_access_context

    async def test_require_scope_fails_without_scope(
        self,
        read_only_context: ApiKeyContext,
    ) -> None:
        """Test that missing required scope raises 403."""
        checker = require_scope("write")

        with pytest.raises(HTTPException) as exc_info:
            await checker(auth=read_only_context)

        assert exc_info.value.status_code == 403
        assert "write" in exc_info.value.detail

    async def test_require_scope_passes_with_wildcard(
        self,
        admin_context: ApiKeyContext,
    ) -> None:
        """Test that wildcard scope passes any check."""
        checker = require_scope("admin")

        result = await checker(auth=admin_context)

        assert result == admin_context


class TestOptionalApiKey:
    """Tests for optional_api_key."""

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Return a mock request."""
        request = MagicMock()
        request.app.state.db = AsyncMock()
        return request

    async def test_returns_none_without_key(
        self,
        mock_request: MagicMock,
    ) -> None:
        """Test returns None when no API key provided."""
        result = await optional_api_key(mock_request, api_key=None)

        assert result is None

    async def test_returns_none_on_invalid_key(
        self,
        mock_request: MagicMock,
    ) -> None:
        """Test returns None when API key is invalid."""
        mock_request.app.state.db.get_api_key_by_hash.return_value = None

        result = await optional_api_key(mock_request, api_key="invalid")

        assert result is None

    async def test_returns_context_on_valid_key(
        self,
        mock_request: MagicMock,
    ) -> None:
        """Test returns context when API key is valid."""
        api_key = "ddr_valid_key"
        mock_request.app.state.db.get_api_key_by_hash.return_value = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "scopes": ["read"],
            "tenant_slug": "test",
            "tenant_name": "Test",
        }

        result = await optional_api_key(mock_request, api_key=api_key)

        assert result is not None
        assert isinstance(result, ApiKeyContext)


class TestApiKeyContext:
    """Tests for ApiKeyContext."""

    def test_create_context(self) -> None:
        """Test creating API key context."""
        context = ApiKeyContext(
            key_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_slug="test-tenant",
            tenant_name="Test Tenant",
            user_id=uuid.uuid4(),
            scopes=["read", "write"],
        )

        assert context.tenant_slug == "test-tenant"
        assert "read" in context.scopes
