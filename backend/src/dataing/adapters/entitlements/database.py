"""Database-backed entitlements adapter - reads plan from organizations table."""

from asyncpg import Pool

from dataing.core.entitlements.features import PLAN_FEATURES, Feature, Plan


class DatabaseEntitlementsAdapter:
    """Entitlements adapter that reads org plan from database.

    Checks organizations.plan column and tenant_entitlements for overrides.
    This is the production adapter for enforcing plan-based feature gates.
    """

    def __init__(self, pool: Pool) -> None:
        """Initialize with database pool.

        Args:
            pool: asyncpg connection pool for app database.
        """
        self._pool = pool

    async def get_plan(self, org_id: str) -> Plan:
        """Get org's current plan from database.

        Args:
            org_id: Organization UUID as string.

        Returns:
            Plan enum value, defaults to FREE if not found.
        """
        query = "SELECT plan FROM organizations WHERE id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, str(org_id))

        if not row or not row["plan"]:
            return Plan.FREE

        plan_str = row["plan"]
        try:
            return Plan(plan_str)
        except ValueError:
            return Plan.FREE

    async def _get_entitlement_override(self, org_id: str, feature: Feature) -> int | bool | None:
        """Check for custom entitlement override.

        Args:
            org_id: Organization UUID.
            feature: Feature to check.

        Returns:
            Override value if exists and not expired, None otherwise.
        """
        query = """
            SELECT value FROM tenant_entitlements
            WHERE org_id = $1 AND feature = $2
            AND (expires_at IS NULL OR expires_at > NOW())
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, str(org_id), feature.value)

        if not row:
            return None

        # value is JSONB - could be {"enabled": true} or {"limit": 100}
        value = row["value"]
        if isinstance(value, dict):
            if "enabled" in value:
                enabled: bool = value["enabled"]
                return enabled
            if "limit" in value:
                limit: int = value["limit"]
                return limit
        return None

    async def has_feature(self, org_id: str, feature: Feature) -> bool:
        """Check if org has access to a boolean feature.

        Checks entitlement override first, then falls back to plan features.

        Args:
            org_id: Organization UUID.
            feature: Feature to check (SSO, SCIM, audit logs, etc.).

        Returns:
            True if org has access to the feature.
        """
        # Check for custom override first
        override = await self._get_entitlement_override(org_id, feature)
        if override is not None:
            return bool(override)

        # Fall back to plan-based features
        plan = await self.get_plan(org_id)
        plan_features = PLAN_FEATURES.get(plan, {})
        feature_value = plan_features.get(feature)

        # Boolean features return True/False, numeric features aren't boolean
        return feature_value is True

    async def get_limit(self, org_id: str, feature: Feature) -> int:
        """Get numeric limit for org (-1 = unlimited).

        Checks entitlement override first, then falls back to plan limits.

        Args:
            org_id: Organization UUID.
            feature: Feature limit (max_seats, max_datasources, etc.).

        Returns:
            Limit value, -1 for unlimited, 0 if not available.
        """
        # Check for custom override first
        override = await self._get_entitlement_override(org_id, feature)
        if override is not None and isinstance(override, int):
            return override

        # Fall back to plan-based limits
        plan = await self.get_plan(org_id)
        plan_features = PLAN_FEATURES.get(plan, {})
        limit = plan_features.get(feature)

        if isinstance(limit, int):
            return limit
        return 0

    async def get_usage(self, org_id: str, feature: Feature) -> int:
        """Get current usage count for a limited feature.

        Args:
            org_id: Organization UUID.
            feature: Feature to get usage for.

        Returns:
            Current usage count.
        """
        async with self._pool.acquire() as conn:
            if feature == Feature.MAX_SEATS:
                # Count org members
                query = "SELECT COUNT(*) FROM org_memberships WHERE org_id = $1"
                count = await conn.fetchval(query, str(org_id))
                return count or 0

            elif feature == Feature.MAX_DATASOURCES:
                # Count datasources for org's tenant
                query = "SELECT COUNT(*) FROM data_sources WHERE tenant_id = $1"
                count = await conn.fetchval(query, str(org_id))
                return count or 0

            elif feature == Feature.MAX_INVESTIGATIONS_PER_MONTH:
                # Count investigations this month
                query = """
                    SELECT COUNT(*) FROM investigations
                    WHERE tenant_id = $1
                    AND created_at >= date_trunc('month', NOW())
                """
                count = await conn.fetchval(query, str(org_id))
                return count or 0

        return 0

    async def check_limit(self, org_id: str, feature: Feature) -> bool:
        """Check if org is under their limit.

        Args:
            org_id: Organization UUID.
            feature: Feature limit to check.

        Returns:
            True if under limit or unlimited (-1).
        """
        limit = await self.get_limit(org_id, feature)
        if limit == -1:
            return True  # Unlimited

        usage = await self.get_usage(org_id, feature)
        return usage < limit
