"""Protocol definitions for entitlements adapters."""

from typing import Protocol, runtime_checkable

from dataing.core.entitlements.features import Feature, Plan


@runtime_checkable
class EntitlementsAdapter(Protocol):
    """Protocol for pluggable entitlements backend.

    Implementations:
    - OpenCoreAdapter: Default free tier (no external dependencies)
    - EnterpriseAdapter: License key validation + DB entitlements
    - StripeAdapter: Stripe subscription management
    """

    async def has_feature(self, org_id: str, feature: Feature) -> bool:
        """Check if org has access to a boolean feature (SSO, SCIM, etc.).

        Args:
            org_id: Organization identifier
            feature: Feature to check

        Returns:
            True if org has access to feature
        """
        ...

    async def get_limit(self, org_id: str, feature: Feature) -> int:
        """Get numeric limit for org (-1 = unlimited).

        Args:
            org_id: Organization identifier
            feature: Feature limit to get

        Returns:
            Limit value, -1 for unlimited
        """
        ...

    async def get_usage(self, org_id: str, feature: Feature) -> int:
        """Get current usage count for a limited feature.

        Args:
            org_id: Organization identifier
            feature: Feature to get usage for

        Returns:
            Current usage count
        """
        ...

    async def check_limit(self, org_id: str, feature: Feature) -> bool:
        """Check if org is under their limit (usage < limit or unlimited).

        Args:
            org_id: Organization identifier
            feature: Feature limit to check

        Returns:
            True if under limit or unlimited
        """
        ...

    async def get_plan(self, org_id: str) -> Plan:
        """Get org's current plan.

        Args:
            org_id: Organization identifier

        Returns:
            Current plan
        """
        ...
