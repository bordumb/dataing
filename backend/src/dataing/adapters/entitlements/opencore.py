"""OpenCore entitlements adapter - default free tier with no external dependencies."""

from dataing.core.entitlements import PLAN_FEATURES, Feature, Plan


class OpenCoreAdapter:
    """Default entitlements adapter for open source deployments.

    Always returns FREE tier limits. No usage tracking or enforcement.
    This allows the open source version to run without any license or billing.
    """

    async def has_feature(self, org_id: str, feature: Feature) -> bool:
        """Check if org has access to a feature.

        In open core, only features included in FREE plan are available.
        """
        free_features = PLAN_FEATURES[Plan.FREE]
        return feature in free_features and free_features[feature] is True

    async def get_limit(self, org_id: str, feature: Feature) -> int:
        """Get numeric limit for org.

        Returns FREE tier limits.
        """
        free_features = PLAN_FEATURES[Plan.FREE]
        limit = free_features.get(feature)
        if isinstance(limit, int):
            return limit
        return 0

    async def get_usage(self, org_id: str, feature: Feature) -> int:
        """Get current usage for org.

        Open core doesn't track usage - always returns 0.
        """
        return 0

    async def check_limit(self, org_id: str, feature: Feature) -> bool:
        """Check if org is under their limit.

        Open core doesn't enforce limits - always returns True.
        """
        return True

    async def get_plan(self, org_id: str) -> Plan:
        """Get org's current plan.

        Open core always returns FREE.
        """
        return Plan.FREE
