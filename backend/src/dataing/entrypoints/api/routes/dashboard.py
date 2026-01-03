"""Dashboard routes for overview and metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    """Dashboard statistics."""

    active_investigations: int
    completed_today: int
    data_sources: int
    pending_approvals: int


class RecentInvestigation(BaseModel):
    """Summary of a recent investigation."""

    id: str
    dataset_id: str
    metric_name: str
    status: str
    severity: str | None = None
    created_at: datetime


class DashboardResponse(BaseModel):
    """Full dashboard response."""

    stats: DashboardStats
    recent_investigations: list[RecentInvestigation]


@router.get("/", response_model=DashboardResponse)
async def get_dashboard(
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> DashboardResponse:
    """Get dashboard overview for the current tenant."""
    # Get stats
    stats = await app_db.get_dashboard_stats(auth.tenant_id)

    # Get recent investigations
    recent = await app_db.list_investigations(auth.tenant_id, limit=10)

    return DashboardResponse(
        stats=DashboardStats(
            active_investigations=stats["activeInvestigations"],
            completed_today=stats["completedToday"],
            data_sources=stats["dataSources"],
            pending_approvals=stats["pendingApprovals"],
        ),
        recent_investigations=[
            RecentInvestigation(
                id=str(inv["id"]),
                dataset_id=inv["dataset_id"],
                metric_name=inv["metric_name"],
                status=inv["status"],
                severity=inv.get("severity"),
                created_at=inv["created_at"],
            )
            for inv in recent
        ],
    )


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    auth: ApiKeyContext = Depends(verify_api_key),
    app_db: AppDatabase = Depends(get_app_db),
) -> DashboardStats:
    """Get just the dashboard statistics."""
    stats = await app_db.get_dashboard_stats(auth.tenant_id)

    return DashboardStats(
        active_investigations=stats["activeInvestigations"],
        completed_today=stats["completedToday"],
        data_sources=stats["dataSources"],
        pending_approvals=stats["pendingApprovals"],
    )
