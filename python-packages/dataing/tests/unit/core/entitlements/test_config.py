"""Tests for entitlements configuration."""

from unittest.mock import patch

from dataing.adapters.entitlements.opencore import OpenCoreAdapter
from dataing.core.entitlements import EntitlementsAdapter
from dataing.core.entitlements.config import get_entitlements_adapter


class TestGetEntitlementsAdapter:
    """Test adapter factory function."""

    def test_returns_opencore_by_default(self) -> None:
        """Should return OpenCoreAdapter when no config is set."""
        adapter = get_entitlements_adapter()
        assert isinstance(adapter, OpenCoreAdapter)
        assert isinstance(adapter, EntitlementsAdapter)

    @patch.dict("os.environ", {"LICENSE_KEY": ""})
    def test_returns_opencore_with_empty_license(self) -> None:
        """Should return OpenCoreAdapter when license key is empty."""
        adapter = get_entitlements_adapter()
        assert isinstance(adapter, OpenCoreAdapter)

    @patch.dict("os.environ", {"STRIPE_SECRET_KEY": ""})
    def test_returns_opencore_with_empty_stripe(self) -> None:
        """Should return OpenCoreAdapter when stripe key is empty."""
        adapter = get_entitlements_adapter()
        assert isinstance(adapter, OpenCoreAdapter)
