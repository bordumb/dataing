"""Tests for entitlements middleware decorators."""

from unittest.mock import AsyncMock, patch

import pytest
from dataing.core.entitlements import Feature
from dataing.entrypoints.api.middleware.entitlements import (
    require_feature,
    require_under_limit,
)
from fastapi import HTTPException


class TestRequireFeature:
    """Test require_feature decorator."""

    @pytest.mark.asyncio
    async def test_allows_when_feature_enabled(self) -> None:
        """Should allow request when feature is enabled."""
        mock_adapter = AsyncMock()
        mock_adapter.has_feature.return_value = True

        @require_feature(Feature.SSO_OIDC)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            result = await endpoint(org_id="org-123")

        assert result == "success"
        mock_adapter.has_feature.assert_called_once_with("org-123", Feature.SSO_OIDC)

    @pytest.mark.asyncio
    async def test_raises_403_when_feature_disabled(self) -> None:
        """Should raise 403 when feature is not enabled."""
        mock_adapter = AsyncMock()
        mock_adapter.has_feature.return_value = False

        @require_feature(Feature.SSO_OIDC)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await endpoint(org_id="org-123")

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "feature_not_available"
        assert exc_info.value.detail["feature"] == "sso_oidc"


class TestRequireUnderLimit:
    """Test require_under_limit decorator."""

    @pytest.mark.asyncio
    async def test_allows_when_under_limit(self) -> None:
        """Should allow request when under limit."""
        mock_adapter = AsyncMock()
        mock_adapter.check_limit.return_value = True

        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            result = await endpoint(org_id="org-123")

        assert result == "success"

    @pytest.mark.asyncio
    async def test_raises_403_when_over_limit(self) -> None:
        """Should raise 403 when over limit."""
        mock_adapter = AsyncMock()
        mock_adapter.check_limit.return_value = False
        mock_adapter.get_limit.return_value = 10

        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def endpoint(org_id: str) -> str:
            return "success"

        with patch(
            "dataing.entrypoints.api.middleware.entitlements.get_entitlements_adapter",
            return_value=mock_adapter,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await endpoint(org_id="org-123")

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "limit_exceeded"
        assert exc_info.value.detail["limit"] == 10
