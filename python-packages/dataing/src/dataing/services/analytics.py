"""Analytics service for activation and usage tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


class AnalyticsEventType(str, Enum):
    """Types of analytics events."""

    ISSUE_CREATED = "issue_created"
    INVESTIGATION_STARTED = "investigation_started"
    INVESTIGATION_COMPLETED = "investigation_completed"
    ISSUE_RESOLVED = "issue_resolved"


class EntityType(str, Enum):
    """Types of entities for analytics events."""

    ISSUE = "issue"
    INVESTIGATION = "investigation"


@dataclass
class WeeklyUsageStats:
    """Weekly usage statistics."""

    week_start: datetime
    issues_created: int
    investigations_started: int
    investigations_completed: int
    issues_resolved: int
    active_teams: int
    resolution_rate: float  # issues_resolved / issues_created


@dataclass
class ActivationStatus:
    """Tenant activation status."""

    tenant_id: UUID
    created_at: datetime
    first_issue_at: datetime | None
    first_investigation_at: datetime | None
    activated_at: datetime | None
    is_activated: bool
    days_to_activation: int | None


@dataclass
class ActivationFunnelStats:
    """Activation funnel statistics."""

    total_tenants: int
    tenants_with_issue: int
    tenants_with_investigation: int
    tenants_activated: int
    issue_rate: float
    investigation_rate: float
    activation_rate: float


class AnalyticsService:
    """Service for recording and querying analytics events."""

    def __init__(self, db: AppDatabase):
        """Initialize the analytics service."""
        self.db = db

    async def record_event(
        self,
        tenant_id: UUID,
        event_type: AnalyticsEventType,
        entity_type: EntityType,
        entity_id: UUID,
        team_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> UUID | None:
        """Record an analytics event.

        Args:
            tenant_id: Tenant ID.
            event_type: Type of event.
            entity_type: Type of entity.
            entity_id: ID of the entity.
            team_id: Optional team ID.
            payload: Optional additional data.

        Returns:
            UUID of the created event.
        """
        result = await self.db.fetch_one(
            """SELECT record_analytics_event($1, $2, $3, $4, $5, $6) as event_id""",
            tenant_id,
            team_id,
            event_type.value,
            entity_type.value,
            entity_id,
            payload or {},
        )

        event_id = result["event_id"] if result else None
        logger.info(
            "analytics_event_recorded",
            event_id=str(event_id),
            tenant_id=str(tenant_id),
            event_type=event_type.value,
            entity_type=entity_type.value,
            entity_id=str(entity_id),
        )

        return event_id

    async def get_weekly_usage(
        self,
        tenant_id: UUID,
        weeks: int = 4,
        team_id: UUID | None = None,
    ) -> list[WeeklyUsageStats]:
        """Get weekly usage statistics.

        Args:
            tenant_id: Tenant ID.
            weeks: Number of weeks to return.
            team_id: Optional team ID to filter by.

        Returns:
            List of weekly usage stats.
        """
        # First try materialized view, fallback to direct query
        if team_id:
            query = """
                SELECT
                    week_start,
                    issues_created,
                    investigations_started,
                    investigations_completed,
                    issues_resolved,
                    active_teams
                FROM weekly_usage_stats
                WHERE tenant_id = $1 AND team_id = $2
                  AND week_start >= NOW() - ($3 || ' weeks')::INTERVAL
                ORDER BY week_start DESC
            """
            rows = await self.db.fetch_all(query, tenant_id, team_id, str(weeks))
        else:
            query = """
                SELECT
                    week_start,
                    SUM(issues_created) as issues_created,
                    SUM(investigations_started) as investigations_started,
                    SUM(investigations_completed) as investigations_completed,
                    SUM(issues_resolved) as issues_resolved,
                    COUNT(DISTINCT team_id) as active_teams
                FROM weekly_usage_stats
                WHERE tenant_id = $1
                  AND week_start >= NOW() - ($2 || ' weeks')::INTERVAL
                GROUP BY week_start
                ORDER BY week_start DESC
            """
            rows = await self.db.fetch_all(query, tenant_id, str(weeks))

        # If materialized view is empty, query directly
        if not rows:
            rows = await self._query_weekly_usage_direct(tenant_id, weeks, team_id)

        return [
            WeeklyUsageStats(
                week_start=row["week_start"],
                issues_created=row["issues_created"] or 0,
                investigations_started=row["investigations_started"] or 0,
                investigations_completed=row["investigations_completed"] or 0,
                issues_resolved=row["issues_resolved"] or 0,
                active_teams=row["active_teams"] or 0,
                resolution_rate=(
                    (row["issues_resolved"] or 0) / (row["issues_created"] or 1)
                    if row["issues_created"]
                    else 0.0
                ),
            )
            for row in rows
        ]

    async def _query_weekly_usage_direct(
        self,
        tenant_id: UUID,
        weeks: int,
        team_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Query weekly usage directly from analytics_events table."""
        if team_id:
            query = """
                SELECT
                    date_trunc('week', created_at) AS week_start,
                    COUNT(*) FILTER (WHERE event_type = 'issue_created') AS issues_created,
                    COUNT(*) FILTER (WHERE event_type = 'investigation_started')
                        AS investigations_started,
                    COUNT(*) FILTER (WHERE event_type = 'investigation_completed')
                        AS investigations_completed,
                    COUNT(*) FILTER (WHERE event_type = 'issue_resolved') AS issues_resolved,
                    1 AS active_teams
                FROM analytics_events
                WHERE tenant_id = $1 AND team_id = $2
                  AND created_at >= NOW() - ($3 || ' weeks')::INTERVAL
                GROUP BY date_trunc('week', created_at)
                ORDER BY week_start DESC
            """
            return await self.db.fetch_all(query, tenant_id, team_id, str(weeks))
        else:
            query = """
                SELECT
                    date_trunc('week', created_at) AS week_start,
                    COUNT(*) FILTER (WHERE event_type = 'issue_created') AS issues_created,
                    COUNT(*) FILTER (WHERE event_type = 'investigation_started')
                        AS investigations_started,
                    COUNT(*) FILTER (WHERE event_type = 'investigation_completed')
                        AS investigations_completed,
                    COUNT(*) FILTER (WHERE event_type = 'issue_resolved') AS issues_resolved,
                    COUNT(DISTINCT team_id) AS active_teams
                FROM analytics_events
                WHERE tenant_id = $1
                  AND created_at >= NOW() - ($2 || ' weeks')::INTERVAL
                GROUP BY date_trunc('week', created_at)
                ORDER BY week_start DESC
            """
            return await self.db.fetch_all(query, tenant_id, str(weeks))

    async def get_activation_status(self, tenant_id: UUID) -> ActivationStatus | None:
        """Get activation status for a tenant.

        Args:
            tenant_id: Tenant ID.

        Returns:
            Activation status or None if not tracked.
        """
        row = await self.db.fetch_one(
            """
            SELECT
                ta.tenant_id,
                ta.created_at,
                ta.first_issue_at,
                ta.first_investigation_at,
                ta.activated_at
            FROM tenant_activation ta
            WHERE ta.tenant_id = $1
            """,
            tenant_id,
        )

        if not row:
            # Check if tenant exists and create activation record
            tenant = await self.db.fetch_one(
                "SELECT id, created_at FROM tenants WHERE id = $1", tenant_id
            )
            if not tenant:
                return None

            await self.db.execute(
                """
                INSERT INTO tenant_activation (tenant_id, created_at, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                tenant_id,
                tenant["created_at"],
            )

            return ActivationStatus(
                tenant_id=tenant_id,
                created_at=tenant["created_at"],
                first_issue_at=None,
                first_investigation_at=None,
                activated_at=None,
                is_activated=False,
                days_to_activation=None,
            )

        is_activated = row["activated_at"] is not None
        days_to_activation = None
        if is_activated and row["created_at"]:
            days_to_activation = (row["activated_at"] - row["created_at"]).days

        return ActivationStatus(
            tenant_id=row["tenant_id"],
            created_at=row["created_at"],
            first_issue_at=row["first_issue_at"],
            first_investigation_at=row["first_investigation_at"],
            activated_at=row["activated_at"],
            is_activated=is_activated,
            days_to_activation=days_to_activation,
        )

    async def get_activation_funnel(
        self,
        since: datetime | None = None,
    ) -> ActivationFunnelStats:
        """Get activation funnel statistics.

        Args:
            since: Only include tenants created since this date.

        Returns:
            Activation funnel statistics.
        """
        if since is None:
            since = datetime.now(UTC) - timedelta(days=90)

        row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_tenants,
                COUNT(first_issue_at) as tenants_with_issue,
                COUNT(first_investigation_at) as tenants_with_investigation,
                COUNT(activated_at) as tenants_activated
            FROM tenant_activation
            WHERE created_at >= $1
            """,
            since,
        )

        if not row:
            return ActivationFunnelStats(
                total_tenants=0,
                tenants_with_issue=0,
                tenants_with_investigation=0,
                tenants_activated=0,
                issue_rate=0.0,
                investigation_rate=0.0,
                activation_rate=0.0,
            )

        total = row["total_tenants"] or 1  # Avoid division by zero

        return ActivationFunnelStats(
            total_tenants=row["total_tenants"],
            tenants_with_issue=row["tenants_with_issue"],
            tenants_with_investigation=row["tenants_with_investigation"],
            tenants_activated=row["tenants_activated"],
            issue_rate=row["tenants_with_issue"] / total,
            investigation_rate=row["tenants_with_investigation"] / total,
            activation_rate=row["tenants_activated"] / total,
        )

    async def refresh_weekly_stats(self) -> None:
        """Refresh the weekly usage stats materialized view."""
        await self.db.execute("SELECT refresh_weekly_usage_stats()")
        logger.info("weekly_usage_stats_refreshed")
