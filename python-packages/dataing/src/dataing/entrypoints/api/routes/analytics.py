r"""Analytics routes for activation and usage metrics.

Endpoints:
    GET /api/v1/analytics/weekly-usage
        Query weekly usage statistics. Returns issues created, investigations
        started/completed, issues resolved, active teams count, and resolution rate.
        Supports filtering by team_id and configuring the number of weeks (1-52).

    GET /api/v1/analytics/activation
        Get activation status for the current tenant. Activation is defined as
        creating an issue AND completing an investigation within 7 days of signup.

    GET /api/v1/analytics/activation/funnel
        Get aggregated activation funnel metrics across all tenants. Shows conversion
        rates through the activation funnel.

    POST /api/v1/analytics/refresh
        Manually refresh the weekly usage statistics materialized view. Typically
        called by a scheduled job but can be triggered manually.

How to View Metrics:
    1. API Queries:
       curl -H "Authorization: Bearer <api_key>" \
            "https://api.dataing.io/api/v1/analytics/weekly-usage?weeks=4"

    2. Direct SQL Queries (for admins):
       -- Weekly usage from materialized view
       SELECT * FROM weekly_usage_stats
       WHERE tenant_id = '<tenant-uuid>'
       ORDER BY week_start DESC;

       -- Activation funnel
       SELECT * FROM tenant_activation
       WHERE activated_at IS NOT NULL;

       -- Raw events
       SELECT event_type, COUNT(*), date_trunc('day', created_at) as day
       FROM analytics_events
       WHERE tenant_id = '<tenant-uuid>'
       GROUP BY event_type, day
       ORDER BY day DESC;
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, require_scope, verify_api_key
from dataing.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Annotated types for dependency injection
AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
AdminScopeDep = Annotated[ApiKeyContext, Depends(require_scope("admin"))]


class WeeklyUsageResponse(BaseModel):
    """Weekly usage statistics response."""

    week_start: datetime
    issues_created: int
    investigations_started: int
    investigations_completed: int
    issues_resolved: int
    active_teams: int
    resolution_rate: float


class WeeklyUsageListResponse(BaseModel):
    """List of weekly usage statistics."""

    weeks: list[WeeklyUsageResponse]


class ActivationStatusResponse(BaseModel):
    """Activation status response."""

    tenant_id: str
    created_at: datetime
    first_issue_at: datetime | None
    first_investigation_at: datetime | None
    activated_at: datetime | None
    is_activated: bool
    days_to_activation: int | None


class ActivationFunnelResponse(BaseModel):
    """Activation funnel statistics response."""

    total_tenants: int
    tenants_with_issue: int
    tenants_with_investigation: int
    tenants_activated: int
    issue_rate: float
    investigation_rate: float
    activation_rate: float


@router.get("/weekly-usage", response_model=WeeklyUsageListResponse)
async def get_weekly_usage(
    auth: AuthDep,
    app_db: AppDbDep,
    weeks: int = Query(default=4, ge=1, le=52, description="Number of weeks to return"),
    team_id: str | None = Query(default=None, description="Filter by team ID"),
) -> WeeklyUsageListResponse:
    """Get weekly usage statistics for the current tenant.

    Returns aggregated metrics per week including:
    - Issues created
    - Investigations started and completed
    - Issues resolved
    - Active teams count
    - Issue resolution rate
    """
    from uuid import UUID

    service = AnalyticsService(app_db)
    team_uuid = UUID(team_id) if team_id else None
    stats = await service.get_weekly_usage(auth.tenant_id, weeks, team_uuid)

    return WeeklyUsageListResponse(
        weeks=[
            WeeklyUsageResponse(
                week_start=s.week_start,
                issues_created=s.issues_created,
                investigations_started=s.investigations_started,
                investigations_completed=s.investigations_completed,
                issues_resolved=s.issues_resolved,
                active_teams=s.active_teams,
                resolution_rate=s.resolution_rate,
            )
            for s in stats
        ]
    )


@router.get("/activation", response_model=ActivationStatusResponse)
async def get_activation_status(
    auth: AuthDep,
    app_db: AppDbDep,
) -> ActivationStatusResponse:
    """Get activation status for the current tenant.

    Activation is defined as having both:
    - Created at least one issue
    - Completed at least one investigation

    Within the first 7 days of account creation.
    """
    service = AnalyticsService(app_db)
    status = await service.get_activation_status(auth.tenant_id)

    if not status:
        return ActivationStatusResponse(
            tenant_id=str(auth.tenant_id),
            created_at=datetime.utcnow(),
            first_issue_at=None,
            first_investigation_at=None,
            activated_at=None,
            is_activated=False,
            days_to_activation=None,
        )

    return ActivationStatusResponse(
        tenant_id=str(status.tenant_id),
        created_at=status.created_at,
        first_issue_at=status.first_issue_at,
        first_investigation_at=status.first_investigation_at,
        activated_at=status.activated_at,
        is_activated=status.is_activated,
        days_to_activation=status.days_to_activation,
    )


@router.get("/activation/funnel", response_model=ActivationFunnelResponse)
async def get_activation_funnel(
    auth: AuthDep,
    app_db: AppDbDep,
    days: int = Query(default=90, ge=1, le=365, description="Look back period in days"),
) -> ActivationFunnelResponse:
    """Get activation funnel statistics.

    Returns aggregated funnel metrics showing:
    - Total tenants created in period
    - Tenants that created at least one issue
    - Tenants that completed at least one investigation
    - Tenants that achieved activation

    Note: This endpoint requires admin permissions in production.
    """
    from datetime import UTC, timedelta

    service = AnalyticsService(app_db)
    since = datetime.now(UTC) - timedelta(days=days)
    funnel = await service.get_activation_funnel(since)

    return ActivationFunnelResponse(
        total_tenants=funnel.total_tenants,
        tenants_with_issue=funnel.tenants_with_issue,
        tenants_with_investigation=funnel.tenants_with_investigation,
        tenants_activated=funnel.tenants_activated,
        issue_rate=funnel.issue_rate,
        investigation_rate=funnel.investigation_rate,
        activation_rate=funnel.activation_rate,
    )


@router.post("/refresh", status_code=204)
async def refresh_weekly_stats(
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> None:
    """Refresh the weekly usage statistics materialized view.

    This is typically called by a scheduled job but can be triggered manually.
    """
    service = AnalyticsService(app_db)
    await service.refresh_weekly_stats()
