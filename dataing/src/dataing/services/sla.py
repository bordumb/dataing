"""SLA breach detection and notification service.

This service runs as a background job to detect issues approaching SLA breaches
and send notifications. It tracks which notifications have been sent to avoid
duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.json_utils import to_json_string
from dataing.core.sla import (
    IssueSLAContext,
    SLAStatus,
    SLAType,
    compute_all_sla_timers,
    get_breach_thresholds_reached,
)

logger = structlog.get_logger()

# Thresholds at which to send notifications (percentage of SLA time elapsed)
BREACH_THRESHOLDS = [50, 75, 90, 100]


@dataclass
class SLABreachResult:
    """Result of SLA breach check for a single issue."""

    issue_id: UUID
    issue_number: int
    sla_type: SLAType
    threshold: int
    elapsed_minutes: int
    target_minutes: int
    percentage: float
    status: SLAStatus


class SLAService:
    """Service for checking and notifying SLA breaches."""

    def __init__(self, db: AppDatabase):
        """Initialize the SLA service.

        Args:
            db: Application database instance.
        """
        self.db = db

    async def check_tenant_sla_breaches(
        self,
        tenant_id: UUID,
        now: datetime | None = None,
    ) -> list[SLABreachResult]:
        """Check all active issues for a tenant for SLA breaches.

        Returns list of new breaches that need notification.
        """
        now = now or datetime.now(UTC)
        results: list[SLABreachResult] = []

        # Get default SLA policy for tenant
        default_policy = await self._get_default_policy(tenant_id)
        if not default_policy:
            # No SLA policy configured
            return results

        # Get all active issues (not closed or resolved)
        active_issues = await self._get_active_issues(tenant_id)

        for issue in active_issues:
            issue_id = issue["id"]

            # Get effective policy (issue-specific or default)
            policy = (
                await self._get_issue_policy(issue["sla_policy_id"])
                if issue["sla_policy_id"]
                else default_policy
            )
            if not policy:
                continue

            # Build issue context
            ctx = await self._build_issue_context(issue)

            # Compute all SLA timers
            timers = compute_all_sla_timers(
                ctx,
                policy["time_to_acknowledge"],
                policy["time_to_progress"],
                policy["time_to_resolve"],
                policy.get("severity_overrides"),
                now,
            )

            # Check each timer for new breaches
            for sla_type, timer in timers.items():
                if timer.status in (
                    SLAStatus.NOT_APPLICABLE,
                    SLAStatus.PAUSED,
                    SLAStatus.COMPLETED,
                ):
                    continue

                # Get thresholds that have been reached
                reached = get_breach_thresholds_reached(timer)

                # Check which haven't been notified yet
                for threshold in reached:
                    already_notified = await self._check_notification_sent(
                        issue_id, sla_type.value, threshold
                    )
                    if not already_notified:
                        results.append(
                            SLABreachResult(
                                issue_id=issue_id,
                                issue_number=issue["number"],
                                sla_type=sla_type,
                                threshold=threshold,
                                elapsed_minutes=timer.elapsed_minutes,
                                target_minutes=timer.target_minutes or 0,
                                percentage=timer.percentage or 0,
                                status=timer.status,
                            )
                        )

        return results

    async def process_breach(
        self,
        breach: SLABreachResult,
        tenant_id: UUID,
    ) -> None:
        """Process a single SLA breach - record event and notification.

        Args:
            breach: Breach details
            tenant_id: Tenant ID for the issue
        """
        # Record the notification to prevent duplicates
        await self._record_notification(
            breach.issue_id,
            breach.sla_type.value,
            breach.threshold,
        )

        # Create an issue event for the breach
        event_payload = {
            "sla_type": breach.sla_type.value,
            "threshold": breach.threshold,
            "elapsed_minutes": breach.elapsed_minutes,
            "target_minutes": breach.target_minutes,
            "percentage": breach.percentage,
            "status": breach.status.value,
        }

        await self._record_issue_event(
            breach.issue_id,
            "sla_breach",
            None,  # System event, no actor
            event_payload,
        )

        # Create in-app notification
        severity = "warning" if breach.threshold < 100 else "error"
        title = (
            f"SLA Breach: Issue #{breach.issue_number}"
            if breach.threshold >= 100
            else f"SLA Warning: Issue #{breach.issue_number} at {breach.threshold}%"
        )
        body = (
            f"{breach.sla_type.value.replace('_', ' ').title()} SLA "
            f"{'breached' if breach.threshold >= 100 else f'at {breach.threshold}%'}. "
            f"Elapsed: {breach.elapsed_minutes}m / Target: {breach.target_minutes}m"
        )

        await self._create_notification(
            tenant_id,
            breach.issue_id,
            title,
            body,
            severity,
            breach.sla_type.value,
            breach.threshold,
        )

        logger.info(
            "sla_breach_processed",
            issue_id=str(breach.issue_id),
            sla_type=breach.sla_type.value,
            threshold=breach.threshold,
            status=breach.status.value,
        )

    async def run_breach_check(self, tenant_id: UUID) -> int:
        """Run SLA breach check for a tenant and process all breaches.

        Returns count of breaches processed.
        """
        breaches = await self.check_tenant_sla_breaches(tenant_id)

        for breach in breaches:
            await self.process_breach(breach, tenant_id)

        if breaches:
            logger.info(
                "sla_breach_check_complete",
                tenant_id=str(tenant_id),
                breach_count=len(breaches),
            )

        return len(breaches)

    async def run_all_tenants_breach_check(self) -> dict[str, int]:
        """Run SLA breach check for all tenants.

        Returns dict mapping tenant_id to breach count.
        """
        results: dict[str, int] = {}

        # Get all tenants
        tenants = await self.db.fetch_all("SELECT id FROM tenants")

        for tenant in tenants:
            tenant_id = tenant["id"]
            count = await self.run_breach_check(tenant_id)
            if count > 0:
                results[str(tenant_id)] = count

        return results

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _get_default_policy(self, tenant_id: UUID) -> dict[str, Any] | None:
        """Get default SLA policy for tenant."""
        result: dict[str, Any] | None = await self.db.fetch_one(
            """
            SELECT id, time_to_acknowledge, time_to_progress, time_to_resolve,
                   severity_overrides
            FROM sla_policies
            WHERE tenant_id = $1 AND is_default = true
            """,
            tenant_id,
        )
        return result

    async def _get_issue_policy(self, policy_id: UUID) -> dict[str, Any] | None:
        """Get SLA policy by ID."""
        result: dict[str, Any] | None = await self.db.fetch_one(
            """
            SELECT id, time_to_acknowledge, time_to_progress, time_to_resolve,
                   severity_overrides
            FROM sla_policies
            WHERE id = $1
            """,
            policy_id,
        )
        return result

    async def _get_active_issues(self, tenant_id: UUID) -> list[dict[str, Any]]:
        """Get all active (non-closed, non-resolved) issues for tenant."""
        result: list[dict[str, Any]] = await self.db.fetch_all(
            """
            SELECT id, number, status, severity, sla_policy_id, created_at
            FROM issues
            WHERE tenant_id = $1
              AND status NOT IN ('closed', 'resolved')
            ORDER BY created_at ASC
            """,
            tenant_id,
        )
        return result

    async def _build_issue_context(self, issue: dict[str, Any]) -> IssueSLAContext:
        """Build SLA context from issue and its events."""
        issue_id = issue["id"]

        # Get state transition timestamps from events
        triaged_at = await self._get_state_transition_time(issue_id, "triaged")
        in_progress_at = await self._get_state_transition_time(issue_id, "in_progress")
        resolved_at = await self._get_state_transition_time(issue_id, "resolved")

        # Calculate total blocked time
        blocked_minutes = await self._calculate_blocked_minutes(issue_id)

        return IssueSLAContext(
            status=issue["status"],
            severity=issue.get("severity"),
            created_at=issue["created_at"],
            triaged_at=triaged_at,
            in_progress_at=in_progress_at,
            resolved_at=resolved_at,
            total_blocked_minutes=blocked_minutes,
        )

    async def _get_state_transition_time(
        self, issue_id: UUID, to_status: str
    ) -> datetime | None:
        """Get first transition time to a specific status."""
        row = await self.db.fetch_one(
            """
            SELECT created_at
            FROM issue_events
            WHERE issue_id = $1
              AND event_type = 'status_changed'
              AND payload->>'to' = $2
            ORDER BY created_at ASC
            LIMIT 1
            """,
            issue_id,
            to_status,
        )
        return row["created_at"] if row else None

    async def _calculate_blocked_minutes(self, issue_id: UUID) -> int:
        """Calculate total minutes issue spent in BLOCKED state."""
        # Get all status_changed events
        events = await self.db.fetch_all(
            """
            SELECT payload, created_at
            FROM issue_events
            WHERE issue_id = $1
              AND event_type = 'status_changed'
            ORDER BY created_at ASC
            """,
            issue_id,
        )

        total_minutes = 0
        blocked_since: datetime | None = None

        for event in events:
            payload = event["payload"] or {}
            to_status = payload.get("to", "")
            from_status = payload.get("from", "")

            if to_status == "blocked":
                # Entering blocked state
                blocked_since = event["created_at"]
            elif from_status == "blocked" and blocked_since:
                # Leaving blocked state
                delta = event["created_at"] - blocked_since
                total_minutes += int(delta.total_seconds() / 60)
                blocked_since = None

        # If currently blocked, add time until now
        if blocked_since:
            delta = datetime.now(UTC) - blocked_since
            total_minutes += int(delta.total_seconds() / 60)

        return total_minutes

    async def _check_notification_sent(
        self, issue_id: UUID, sla_type: str, threshold: int
    ) -> bool:
        """Check if a breach notification has already been sent."""
        row = await self.db.fetch_one(
            """
            SELECT 1 FROM sla_breach_notifications
            WHERE issue_id = $1 AND sla_type = $2 AND threshold = $3
            """,
            issue_id,
            sla_type,
            threshold,
        )
        return row is not None

    async def _record_notification(
        self, issue_id: UUID, sla_type: str, threshold: int
    ) -> None:
        """Record that a breach notification was sent."""
        await self.db.execute(
            """
            INSERT INTO sla_breach_notifications (issue_id, sla_type, threshold, notified_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (issue_id, sla_type, threshold) DO NOTHING
            """,
            issue_id,
            sla_type,
            threshold,
        )

    async def _record_issue_event(
        self,
        issue_id: UUID,
        event_type: str,
        actor_user_id: UUID | None,
        payload: dict[str, Any],
    ) -> None:
        """Record an issue event."""
        await self.db.execute(
            """
            INSERT INTO issue_events (issue_id, event_type, actor_user_id, payload)
            VALUES ($1, $2, $3, $4)
            """,
            issue_id,
            event_type,
            actor_user_id,
            to_json_string(payload),
        )

    async def _create_notification(
        self,
        tenant_id: UUID,
        issue_id: UUID,
        title: str,
        body: str,
        severity: str,
        sla_type: str,
        threshold: int,
    ) -> None:
        """Create an in-app notification for SLA breach."""
        await self.db.execute(
            """
            INSERT INTO notifications
                (tenant_id, type, title, body, resource_kind, resource_id, severity)
            VALUES ($1, $2, $3, $4, 'issue', $5, $6)
            """,
            tenant_id,
            f"sla_breach_{sla_type}_{threshold}",
            title,
            body,
            issue_id,
            severity,
        )
