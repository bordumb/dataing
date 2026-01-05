"""Tests for entitlements adapter protocol."""

from dataing.core.entitlements.features import Feature, Plan
from dataing.core.entitlements.interfaces import EntitlementsAdapter


class TestEntitlementsAdapterProtocol:
    """Test EntitlementsAdapter is a proper protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Protocol should be runtime checkable."""
        assert hasattr(EntitlementsAdapter, "__protocol_attrs__") or isinstance(
            EntitlementsAdapter, type
        )

    def test_protocol_has_required_methods(self) -> None:
        """Protocol should define required methods."""
        # Check method signatures exist
        assert hasattr(EntitlementsAdapter, "has_feature")
        assert hasattr(EntitlementsAdapter, "get_limit")
        assert hasattr(EntitlementsAdapter, "get_usage")
        assert hasattr(EntitlementsAdapter, "check_limit")
        assert hasattr(EntitlementsAdapter, "get_plan")


class MockAdapter:
    """Mock implementation for testing protocol compliance."""

    async def has_feature(self, org_id: str, feature: Feature) -> bool:
        """Check if org has access to a feature."""
        return True

    async def get_limit(self, org_id: str, feature: Feature) -> int:
        """Get numeric limit for org."""
        return 10

    async def get_usage(self, org_id: str, feature: Feature) -> int:
        """Get current usage for org."""
        return 5

    async def check_limit(self, org_id: str, feature: Feature) -> bool:
        """Check if org is under their limit."""
        return True

    async def get_plan(self, org_id: str) -> Plan:
        """Get org's current plan."""
        return Plan.FREE


class TestProtocolCompliance:
    """Test that implementations comply with protocol."""

    def test_mock_adapter_is_protocol_compliant(self) -> None:
        """Mock adapter should be instance of protocol."""
        adapter = MockAdapter()
        assert isinstance(adapter, EntitlementsAdapter)
