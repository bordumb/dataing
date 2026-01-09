"""Tests for entitlements middleware decorators."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from dataing.core.entitlements import Feature
from dataing.entrypoints.api.middleware.auth import ApiKeyContext
from dataing.entrypoints.api.middleware.entitlements import (
    require_feature,
    require_under_limit,
)
from fastapi import HTTPException, Request


def create_mock_request(adapter: AsyncMock) -> MagicMock:
    """Create a mock request with app state containing entitlements adapter."""
    request = MagicMock(spec=Request)
    request.app.state.entitlements_adapter = adapter
    return request


def create_mock_auth(tenant_id: str = "00000000-0000-0000-0000-000000000123") -> ApiKeyContext:
    """Create a mock auth context."""
    return ApiKeyContext(
        key_id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=UUID(tenant_id),
        tenant_slug="test-org",
        tenant_name="Test Organization",
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        scopes=["admin"],
    )


class TestRequireFeature:
    """Test require_feature decorator."""

    @pytest.mark.asyncio
    async def test_allows_when_feature_enabled(self) -> None:
        """Should allow request when feature is enabled."""
        mock_adapter = AsyncMock()
        mock_adapter.has_feature.return_value = True
        mock_request = create_mock_request(mock_adapter)
        mock_auth = create_mock_auth()

        @require_feature(Feature.SSO_OIDC)
        async def endpoint(request: Request, auth: ApiKeyContext) -> str:
            return "success"

        result = await endpoint(request=mock_request, auth=mock_auth)

        assert result == "success"
        mock_adapter.has_feature.assert_called_once_with(str(mock_auth.tenant_id), Feature.SSO_OIDC)

    @pytest.mark.asyncio
    async def test_raises_403_when_feature_disabled(self) -> None:
        """Should raise 403 when feature is not enabled."""
        mock_adapter = AsyncMock()
        mock_adapter.has_feature.return_value = False
        mock_request = create_mock_request(mock_adapter)
        mock_auth = create_mock_auth()

        @require_feature(Feature.SSO_OIDC)
        async def endpoint(request: Request, auth: ApiKeyContext) -> str:
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await endpoint(request=mock_request, auth=mock_auth)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "feature_not_available"
        assert exc_info.value.detail["feature"] == "sso_oidc"

    @pytest.mark.asyncio
    async def test_skips_check_without_request_or_auth(self) -> None:
        """Should skip feature check if request or auth not provided."""

        @require_feature(Feature.SSO_OIDC)
        async def endpoint() -> str:
            return "success"

        # Should not raise, just pass through
        result = await endpoint()
        assert result == "success"


class TestRequireUnderLimit:
    """Test require_under_limit decorator."""

    @pytest.mark.asyncio
    async def test_allows_when_under_limit(self) -> None:
        """Should allow request when under limit."""
        mock_adapter = AsyncMock()
        mock_adapter.check_limit.return_value = True
        mock_request = create_mock_request(mock_adapter)
        mock_auth = create_mock_auth()

        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def endpoint(request: Request, auth: ApiKeyContext) -> str:
            return "success"

        result = await endpoint(request=mock_request, auth=mock_auth)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_raises_403_when_over_limit(self) -> None:
        """Should raise 403 when over limit."""
        mock_adapter = AsyncMock()
        mock_adapter.check_limit.return_value = False
        mock_adapter.get_limit.return_value = 10
        mock_adapter.get_usage.return_value = 12
        mock_request = create_mock_request(mock_adapter)
        mock_auth = create_mock_auth()

        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def endpoint(request: Request, auth: ApiKeyContext) -> str:
            return "success"

        with pytest.raises(HTTPException) as exc_info:
            await endpoint(request=mock_request, auth=mock_auth)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "limit_exceeded"
        assert exc_info.value.detail["limit"] == 10
        assert exc_info.value.detail["usage"] == 12

    @pytest.mark.asyncio
    async def test_skips_check_without_request_or_auth(self) -> None:
        """Should skip limit check if request or auth not provided."""

        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def endpoint() -> str:
            return "success"

        # Should not raise, just pass through
        result = await endpoint()
        assert result == "success"
