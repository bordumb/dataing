"""Fix Proposal Feedback Service - Collect and analyze feedback on applied fixes.

This service handles:
- Recording user feedback on fix proposals (worked/didn't work/partially)
- Aggregating success rates by fix_type, root_cause_category
- Alerting on low success rates
- Exporting feedback for fine-tuning analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from dataing.adapters.investigation_feedback.types import EventType

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase
    from dataing.adapters.investigation_feedback.adapter import InvestigationFeedbackAdapter

logger = structlog.get_logger()

# Default threshold for alerting on low success rates
DEFAULT_LOW_SUCCESS_THRESHOLD = 0.5

# Minimum samples needed before alerting
MIN_SAMPLES_FOR_ALERT = 10

# Time window for aggregating success rates
DEFAULT_AGGREGATION_WINDOW_DAYS = 30


class FixFeedbackRating(str, Enum):
    """User rating for a fix proposal."""

    YES = "yes"  # Fix worked as expected
    NO = "no"  # Fix did not work
    PARTIALLY = "partially"  # Fix partially worked


@dataclass
class FixFeedback:
    """User feedback on a fix proposal.

    Attributes:
        id: Unique feedback identifier.
        fix_execution_id: ID of the fix execution this feedback relates to.
        investigation_id: ID of the investigation.
        tenant_id: Tenant ID.
        user_id: User who provided feedback.
        rating: User's rating of the fix.
        comment: Optional free-text comment.
        fix_type: Type of fix (sql_dml, sql_ddl, etc.).
        root_cause_category: Category of root cause (if known).
        created_at: When feedback was submitted.
    """

    fix_execution_id: UUID
    investigation_id: UUID
    tenant_id: UUID
    user_id: UUID
    rating: FixFeedbackRating
    fix_type: str
    id: UUID = field(default_factory=uuid4)
    comment: str | None = None
    root_cause_category: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FixSuccessStats:
    """Aggregated success statistics for fixes.

    Attributes:
        total_fixes: Total number of fixes with feedback.
        successful: Number of fixes rated "yes".
        failed: Number of fixes rated "no".
        partial: Number of fixes rated "partially".
        success_rate: Percentage of successful fixes (yes / total).
        effective_rate: Percentage of at least partially working fixes.
        period_start: Start of the aggregation period.
        period_end: End of the aggregation period.
    """

    total_fixes: int
    successful: int
    failed: int
    partial: int
    success_rate: float
    effective_rate: float
    period_start: datetime
    period_end: datetime


@dataclass
class FixSuccessAlert:
    """Alert triggered when success rate is below threshold.

    Attributes:
        id: Alert identifier.
        tenant_id: Tenant ID.
        category: The category (fix_type or root_cause) with low success.
        category_type: Whether this is "fix_type" or "root_cause".
        success_rate: Current success rate.
        threshold: Threshold that was breached.
        sample_count: Number of samples in the calculation.
        message: Human-readable alert message.
        created_at: When alert was generated.
    """

    tenant_id: UUID
    category: str
    category_type: str
    success_rate: float
    threshold: float
    sample_count: int
    message: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FeedbackExportRecord:
    """Record for fine-tuning export.

    Attributes:
        fix_execution_id: Fix execution ID.
        investigation_id: Investigation ID.
        fix_type: Type of fix.
        fix_code: The fix code that was executed.
        rating: User's rating.
        comment: User's comment.
        root_cause_category: Root cause category.
        context: Additional context for fine-tuning.
    """

    fix_execution_id: UUID
    investigation_id: UUID
    fix_type: str
    fix_code: str
    rating: str
    comment: str | None
    root_cause_category: str | None
    context: dict[str, Any]


class FixFeedbackService:
    """Service for collecting and analyzing fix proposal feedback."""

    def __init__(
        self,
        db: AppDatabase | None = None,
        feedback_adapter: InvestigationFeedbackAdapter | None = None,
        low_success_threshold: float = DEFAULT_LOW_SUCCESS_THRESHOLD,
        min_samples_for_alert: int = MIN_SAMPLES_FOR_ALERT,
    ) -> None:
        """Initialize the fix feedback service.

        Args:
            db: Application database for storing feedback.
            feedback_adapter: Adapter for emitting feedback events.
            low_success_threshold: Threshold below which to alert.
            min_samples_for_alert: Minimum samples needed before alerting.
        """
        self.db = db
        self.feedback_adapter = feedback_adapter
        self.low_success_threshold = low_success_threshold
        self.min_samples_for_alert = min_samples_for_alert
        self._feedback_cache: dict[UUID, FixFeedback] = {}

    async def record_feedback(
        self,
        *,
        fix_execution_id: UUID,
        investigation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        rating: FixFeedbackRating,
        fix_type: str,
        comment: str | None = None,
        root_cause_category: str | None = None,
    ) -> FixFeedback:
        """Record user feedback on a fix.

        Args:
            fix_execution_id: ID of the fix execution.
            investigation_id: ID of the investigation.
            tenant_id: Tenant ID.
            user_id: User providing feedback.
            rating: User's rating of the fix.
            fix_type: Type of fix (sql_dml, sql_ddl, etc.).
            comment: Optional comment explaining the rating.
            root_cause_category: Category of root cause.

        Returns:
            The created FixFeedback record.
        """
        feedback = FixFeedback(
            fix_execution_id=fix_execution_id,
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            rating=rating,
            fix_type=fix_type,
            comment=comment,
            root_cause_category=root_cause_category,
        )

        # Store in database
        await self._store_feedback(feedback)

        # Cache for quick access
        self._feedback_cache[feedback.id] = feedback

        # Emit event
        if self.feedback_adapter:
            await self.feedback_adapter.emit(
                tenant_id=tenant_id,
                event_type=EventType.FEEDBACK_FIX,
                event_data={
                    "fix_execution_id": str(fix_execution_id),
                    "rating": rating.value,
                    "fix_type": fix_type,
                    "comment": comment,
                    "root_cause_category": root_cause_category,
                },
                investigation_id=investigation_id,
                actor_id=user_id,
                actor_type="user",
            )

        logger.info(
            "fix_feedback_recorded",
            feedback_id=str(feedback.id),
            fix_execution_id=str(fix_execution_id),
            rating=rating.value,
            fix_type=fix_type,
        )

        return feedback

    async def _store_feedback(self, feedback: FixFeedback) -> None:
        """Store feedback in the database.

        Args:
            feedback: The feedback to store.
        """
        if not self.db:
            return

        query = """
            INSERT INTO fix_feedback (
                id, fix_execution_id, investigation_id, tenant_id, user_id,
                rating, comment, fix_type, root_cause_category, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """

        try:
            await self.db.execute(
                query,
                feedback.id,
                feedback.fix_execution_id,
                feedback.investigation_id,
                feedback.tenant_id,
                feedback.user_id,
                feedback.rating.value,
                feedback.comment,
                feedback.fix_type,
                feedback.root_cause_category,
                feedback.created_at,
            )
        except Exception as e:
            logger.error(
                "fix_feedback_store_failed",
                feedback_id=str(feedback.id),
                error=str(e),
            )
            raise

    async def get_success_stats(
        self,
        tenant_id: UUID,
        *,
        fix_type: str | None = None,
        root_cause_category: str | None = None,
        days: int = DEFAULT_AGGREGATION_WINDOW_DAYS,
    ) -> FixSuccessStats:
        """Get aggregated success statistics.

        Args:
            tenant_id: Tenant ID.
            fix_type: Optional filter by fix type.
            root_cause_category: Optional filter by root cause category.
            days: Number of days to aggregate over.

        Returns:
            Aggregated success statistics.
        """
        period_end = datetime.now(UTC)
        period_start = period_end - timedelta(days=days)

        if not self.db:
            return FixSuccessStats(
                total_fixes=0,
                successful=0,
                failed=0,
                partial=0,
                success_rate=0.0,
                effective_rate=0.0,
                period_start=period_start,
                period_end=period_end,
            )

        # Build query with optional filters
        conditions = ["tenant_id = $1", "created_at >= $2", "created_at <= $3"]
        params: list[Any] = [tenant_id, period_start, period_end]

        if fix_type:
            conditions.append(f"fix_type = ${len(params) + 1}")
            params.append(fix_type)

        if root_cause_category:
            conditions.append(f"root_cause_category = ${len(params) + 1}")
            params.append(root_cause_category)

        query = f"""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE rating = 'yes') as successful,
                COUNT(*) FILTER (WHERE rating = 'no') as failed,
                COUNT(*) FILTER (WHERE rating = 'partially') as partial
            FROM fix_feedback
            WHERE {' AND '.join(conditions)}
        """

        row = await self.db.fetch_one(query, *params)

        if not row or row["total"] == 0:
            return FixSuccessStats(
                total_fixes=0,
                successful=0,
                failed=0,
                partial=0,
                success_rate=0.0,
                effective_rate=0.0,
                period_start=period_start,
                period_end=period_end,
            )

        total = row["total"]
        successful = row["successful"] or 0
        partial = row["partial"] or 0

        return FixSuccessStats(
            total_fixes=total,
            successful=successful,
            failed=row["failed"] or 0,
            partial=partial,
            success_rate=successful / total if total > 0 else 0.0,
            effective_rate=(successful + partial) / total if total > 0 else 0.0,
            period_start=period_start,
            period_end=period_end,
        )

    async def get_success_stats_by_fix_type(
        self,
        tenant_id: UUID,
        days: int = DEFAULT_AGGREGATION_WINDOW_DAYS,
    ) -> dict[str, FixSuccessStats]:
        """Get success statistics grouped by fix type.

        Args:
            tenant_id: Tenant ID.
            days: Number of days to aggregate over.

        Returns:
            Dictionary mapping fix_type to success stats.
        """
        if not self.db:
            return {}

        period_end = datetime.now(UTC)
        period_start = period_end - timedelta(days=days)

        query = """
            SELECT
                fix_type,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE rating = 'yes') as successful,
                COUNT(*) FILTER (WHERE rating = 'no') as failed,
                COUNT(*) FILTER (WHERE rating = 'partially') as partial
            FROM fix_feedback
            WHERE tenant_id = $1 AND created_at >= $2 AND created_at <= $3
            GROUP BY fix_type
        """

        rows = await self.db.fetch_all(query, tenant_id, period_start, period_end)

        results = {}
        for row in rows:
            total = row["total"]
            successful = row["successful"] or 0
            partial = row["partial"] or 0

            results[row["fix_type"]] = FixSuccessStats(
                total_fixes=total,
                successful=successful,
                failed=row["failed"] or 0,
                partial=partial,
                success_rate=successful / total if total > 0 else 0.0,
                effective_rate=(successful + partial) / total if total > 0 else 0.0,
                period_start=period_start,
                period_end=period_end,
            )

        return results

    async def check_for_alerts(
        self,
        tenant_id: UUID,
        days: int = DEFAULT_AGGREGATION_WINDOW_DAYS,
    ) -> list[FixSuccessAlert]:
        """Check for low success rate alerts.

        Args:
            tenant_id: Tenant ID.
            days: Number of days to check.

        Returns:
            List of alerts for categories below threshold.
        """
        alerts: list[FixSuccessAlert] = []

        # Check by fix type
        stats_by_type = await self.get_success_stats_by_fix_type(tenant_id, days)
        for fix_type, stats in stats_by_type.items():
            if (
                stats.total_fixes >= self.min_samples_for_alert
                and stats.success_rate < self.low_success_threshold
            ):
                alerts.append(
                    FixSuccessAlert(
                        tenant_id=tenant_id,
                        category=fix_type,
                        category_type="fix_type",
                        success_rate=stats.success_rate,
                        threshold=self.low_success_threshold,
                        sample_count=stats.total_fixes,
                        message=(
                            f"Fix type '{fix_type}' has a low success rate of "
                            f"{stats.success_rate:.1%} ({stats.total_fixes} samples). "
                            f"Consider reviewing prompts for this fix type."
                        ),
                    )
                )

        # Log alerts
        for alert in alerts:
            logger.warning(
                "fix_success_rate_alert",
                alert_id=str(alert.id),
                tenant_id=str(tenant_id),
                category=alert.category,
                category_type=alert.category_type,
                success_rate=alert.success_rate,
                sample_count=alert.sample_count,
            )

        return alerts

    async def export_feedback_for_finetuning(
        self,
        tenant_id: UUID,
        *,
        since: datetime | None = None,
        include_context: bool = True,
    ) -> list[FeedbackExportRecord]:
        """Export feedback records for fine-tuning analysis.

        Args:
            tenant_id: Tenant ID.
            since: Only export feedback since this date.
            include_context: Whether to include investigation context.

        Returns:
            List of feedback records ready for export.
        """
        if not self.db:
            return []

        if since is None:
            since = datetime.now(UTC) - timedelta(days=90)

        query = """
            SELECT
                ff.fix_execution_id,
                ff.investigation_id,
                ff.fix_type,
                ff.rating,
                ff.comment,
                ff.root_cause_category,
                fe.fix_code
            FROM fix_feedback ff
            LEFT JOIN fix_executions fe ON fe.id = ff.fix_execution_id
            WHERE ff.tenant_id = $1 AND ff.created_at >= $2
            ORDER BY ff.created_at DESC
        """

        rows = await self.db.fetch_all(query, tenant_id, since)

        records = []
        for row in rows:
            context: dict[str, Any] = {}

            if include_context:
                context = await self.investigation_context(row["investigation_id"])

            records.append(
                FeedbackExportRecord(
                    fix_execution_id=row["fix_execution_id"],
                    investigation_id=row["investigation_id"],
                    fix_type=row["fix_type"],
                    fix_code=row["fix_code"] or "",
                    rating=row["rating"],
                    comment=row["comment"],
                    root_cause_category=row["root_cause_category"],
                    context=context,
                )
            )

        logger.info(
            "fix_feedback_exported",
            tenant_id=str(tenant_id),
            record_count=len(records),
            since=since.isoformat(),
        )

        return records

    async def investigation_context(self, investigation_id: UUID) -> dict[str, Any]:
        """Context an exported feedback record carries about its investigation.

        Names the issue the investigation was most recently spawned from, if any.

        Args:
            investigation_id: The investigation the feedback is about.

        Returns:
            investigation_created_at, plus issue_id when an issue spawned it.
        """
        if not self.db:
            return {}

        row = await self.db.fetch_one(
            """
            SELECT i.created_at AS investigation_created_at, run.issue_id
            FROM investigations i
            LEFT JOIN LATERAL (
                SELECT issue_id FROM issue_investigation_runs
                WHERE investigation_id = i.id
                ORDER BY created_at DESC
                LIMIT 1
            ) run ON true
            WHERE i.id = $1
            """,
            investigation_id,
        )
        if row is None:
            return {}

        context: dict[str, Any] = {
            "investigation_created_at": row["investigation_created_at"].isoformat()
        }
        if row["issue_id"] is not None:
            context["issue_id"] = str(row["issue_id"])
        return context

    def get_feedback(self, feedback_id: UUID) -> FixFeedback | None:
        """Get feedback by ID from cache.

        Args:
            feedback_id: The feedback ID.

        Returns:
            FixFeedback if found, None otherwise.
        """
        return self._feedback_cache.get(feedback_id)
