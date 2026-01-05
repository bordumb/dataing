"""Tests for OpenCore entitlements adapter."""

import pytest
from dataing.adapters.entitlements.opencore import OpenCoreAdapter
from dataing.core.entitlements import EntitlementsAdapter, Feature, Plan


class TestOpenCoreAdapter:
    """Test OpenCoreAdapter implementation."""

    @pytest.fixture
    def adapter(self) -> OpenCoreAdapter:
        """Create adapter instance."""
        return OpenCoreAdapter()

    def test_implements_protocol(self, adapter: OpenCoreAdapter) -> None:
        """Adapter should implement EntitlementsAdapter protocol."""
        assert isinstance(adapter, EntitlementsAdapter)

    @pytest.mark.asyncio
    async def test_get_plan_always_free(self, adapter: OpenCoreAdapter) -> None:
        """OpenCore always returns FREE plan."""
        plan = await adapter.get_plan("any-org-id")
        assert plan == Plan.FREE

    @pytest.mark.asyncio
    async def test_has_feature_enterprise_features_false(self, adapter: OpenCoreAdapter) -> None:
        """Enterprise features should return False."""
        assert await adapter.has_feature("org", Feature.SSO_OIDC) is False
        assert await adapter.has_feature("org", Feature.SSO_SAML) is False
        assert await adapter.has_feature("org", Feature.SCIM) is False
        assert await adapter.has_feature("org", Feature.AUDIT_LOGS) is False

    @pytest.mark.asyncio
    async def test_get_limit_returns_free_tier(self, adapter: OpenCoreAdapter) -> None:
        """Limits should return FREE tier values."""
        assert await adapter.get_limit("org", Feature.MAX_SEATS) == 3
        assert await adapter.get_limit("org", Feature.MAX_DATASOURCES) == 2
        assert await adapter.get_limit("org", Feature.MAX_INVESTIGATIONS_PER_MONTH) == 10

    @pytest.mark.asyncio
    async def test_get_usage_returns_zero(self, adapter: OpenCoreAdapter) -> None:
        """Usage should return 0 (no tracking in open core)."""
        assert await adapter.get_usage("org", Feature.MAX_SEATS) == 0

    @pytest.mark.asyncio
    async def test_check_limit_always_true(self, adapter: OpenCoreAdapter) -> None:
        """Check limit should always return True (no enforcement in open core)."""
        assert await adapter.check_limit("org", Feature.MAX_SEATS) is True
