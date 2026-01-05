"""Entitlements adapter factory configuration."""

import os
from functools import lru_cache

from dataing.adapters.entitlements.opencore import OpenCoreAdapter
from dataing.core.entitlements.interfaces import EntitlementsAdapter


@lru_cache
def get_entitlements_adapter() -> EntitlementsAdapter:
    """Get the configured entitlements adapter.

    Selection priority:
    1. STRIPE_SECRET_KEY set -> StripeAdapter (SaaS billing)
    2. LICENSE_KEY set -> EnterpriseAdapter (self-hosted licensed)
    3. Neither set -> OpenCoreAdapter (free tier)

    Returns:
        Configured entitlements adapter instance
    """
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    license_key = os.environ.get("LICENSE_KEY", "").strip()

    if stripe_key:
        # TODO: Return StripeAdapter when implemented
        # return StripeAdapter(stripe_key)
        pass

    if license_key:
        # TODO: Return EnterpriseAdapter when implemented
        # return EnterpriseAdapter(license_key)
        pass

    return OpenCoreAdapter()
