"""Usage and cost tracking service."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()

# LLM pricing per 1K tokens (approximate)
LLM_PRICING = {
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
    "default": {"input": 0.01, "output": 0.03},
}


@dataclass
class UsageSummary:
    """Usage summary for a time period."""

    llm_tokens: int
    llm_cost: float
    query_executions: int
    investigations: int
    total_cost: float


class UsageTracker:
    """Track usage for billing and quotas."""

    def __init__(self, db: AppDatabase):
        """Initialize the usage tracker.

        Args:
            db: Application database instance.
        """
        self.db = db

    async def record_llm_usage(
        self,
        tenant_id: UUID,
        model: str,
        input_tokens: int,
        output_tokens: int,
        investigation_id: UUID | None = None,
    ) -> float:
        """Record LLM token usage and return cost."""
        pricing = LLM_PRICING.get(model, LLM_PRICING["default"])

        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000

        await self.db.record_usage(
            tenant_id=tenant_id,
            resource_type="llm_tokens",
            quantity=input_tokens + output_tokens,
            unit_cost=cost,
            metadata={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "investigation_id": str(investigation_id) if investigation_id else None,
            },
        )

        logger.debug(
            "llm_usage_recorded",
            tenant_id=str(tenant_id),
            model=model,
            tokens=input_tokens + output_tokens,
            cost=cost,
        )

        return cost

    async def record_query_execution(
        self,
        tenant_id: UUID,
        data_source_type: str,
        rows_scanned: int | None = None,
        investigation_id: UUID | None = None,
    ) -> None:
        """Record a query execution."""
        # Simple flat cost per query for now
        cost = 0.001  # $0.001 per query

        await self.db.record_usage(
            tenant_id=tenant_id,
            resource_type="query_execution",
            quantity=1,
            unit_cost=cost,
            metadata={
                "data_source_type": data_source_type,
                "rows_scanned": rows_scanned,
                "investigation_id": str(investigation_id) if investigation_id else None,
            },
        )

    async def record_investigation(
        self,
        tenant_id: UUID,
        investigation_id: UUID,
        status: str,
    ) -> None:
        """Record an investigation completion."""
        # Cost per investigation based on status
        cost = 0.05 if status == "completed" else 0.01

        await self.db.record_usage(
            tenant_id=tenant_id,
            resource_type="investigation",
            quantity=1,
            unit_cost=cost,
            metadata={
                "investigation_id": str(investigation_id),
                "status": status,
            },
        )

    async def get_monthly_usage(
        self,
        tenant_id: UUID,
        year: int | None = None,
        month: int | None = None,
    ) -> UsageSummary:
        """Get usage summary for a specific month."""
        now = datetime.utcnow()
        year = year or now.year
        month = month or now.month

        records = await self.db.get_monthly_usage(tenant_id, year, month)

        # Initialize summary
        llm_tokens = 0
        llm_cost = 0.0
        query_executions = 0
        investigations = 0
        total_cost = 0.0

        for record in records:
            resource_type = record["resource_type"]
            quantity = record["total_quantity"] or 0
            cost = record["total_cost"] or 0.0

            if resource_type == "llm_tokens":
                llm_tokens = quantity
                llm_cost = cost
            elif resource_type == "query_execution":
                query_executions = quantity
            elif resource_type == "investigation":
                investigations = quantity

            total_cost += cost

        return UsageSummary(
            llm_tokens=llm_tokens,
            llm_cost=llm_cost,
            query_executions=query_executions,
            investigations=investigations,
            total_cost=total_cost,
        )

    async def check_quota(
        self,
        tenant_id: UUID,
        resource_type: str,
        quantity: int = 1,
    ) -> bool:
        """Check if tenant has quota remaining for a resource.

        This is a placeholder for implementing actual quota limits.
        In production, you'd check against tenant settings/plan limits.
        """
        # For now, always allow
        return True

    async def get_daily_trend(
        self,
        tenant_id: UUID,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get daily usage trend for the last N days."""
        result: list[dict[str, Any]] = await self.db.fetch_all(
            f"""SELECT DATE(timestamp) as date,
                      SUM(quantity) as quantity,
                      SUM(unit_cost) as cost
               FROM usage_records
               WHERE tenant_id = $1
                 AND timestamp >= NOW() - INTERVAL '{days} days'
               GROUP BY DATE(timestamp)
               ORDER BY date DESC""",
            tenant_id,
        )
        return result
