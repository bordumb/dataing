"""Usage metrics routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dataing.entrypoints.api.deps import get_usage_tracker
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.services.usage import UsageTracker

router = APIRouter(prefix="/usage", tags=["usage"])

# Annotated types for dependency injection
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
UsageTrackerDep = Annotated[UsageTracker, Depends(get_usage_tracker)]


class UsageMetricsResponse(BaseModel):
    """Usage metrics response."""

    llm_tokens: int
    llm_cost: float
    query_executions: int
    investigations: int
    total_cost: float


@router.get("/metrics", response_model=UsageMetricsResponse)
async def get_usage_metrics(
    auth: AuthDep,
    usage_tracker: UsageTrackerDep,
) -> UsageMetricsResponse:
    """Get current usage metrics for tenant."""
    summary = await usage_tracker.get_monthly_usage(auth.tenant_id)
    return UsageMetricsResponse(
        llm_tokens=summary.llm_tokens,
        llm_cost=summary.llm_cost,
        query_executions=summary.query_executions,
        investigations=summary.investigations,
        total_cost=summary.total_cost,
    )
