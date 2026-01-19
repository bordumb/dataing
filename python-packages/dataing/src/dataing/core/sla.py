"""SLA computation helpers.

This module provides utilities for calculating SLA timers and breach status
for issues. SLA timers are derived fields computed on-demand based on
issue state and timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class SLAType(str, Enum):
    """Types of SLA timers."""

    ACKNOWLEDGE = "acknowledge"  # OPEN -> TRIAGED
    PROGRESS = "progress"  # TRIAGED -> IN_PROGRESS
    RESOLVE = "resolve"  # any -> RESOLVED


class SLAStatus(str, Enum):
    """SLA timer status."""

    NOT_APPLICABLE = "not_applicable"  # Timer not relevant for current state
    ON_TRACK = "on_track"  # Within SLA
    AT_RISK = "at_risk"  # Past warning threshold (50%)
    CRITICAL = "critical"  # Past critical threshold (90%)
    BREACHED = "breached"  # Past 100%
    PAUSED = "paused"  # Issue is BLOCKED
    COMPLETED = "completed"  # Timer completed successfully


@dataclass
class SLATimer:
    """Computed SLA timer state."""

    sla_type: SLAType
    status: SLAStatus
    target_minutes: int | None
    elapsed_minutes: int
    remaining_minutes: int | None
    breach_at: datetime | None
    percentage: float | None


@dataclass
class IssueSLAContext:
    """Issue context needed for SLA computation."""

    status: str
    severity: str | None
    created_at: datetime
    # Timestamps for state transitions (from issue_events)
    triaged_at: datetime | None
    in_progress_at: datetime | None
    resolved_at: datetime | None
    # Accumulated blocked time in minutes
    total_blocked_minutes: int


def get_effective_sla_time(
    sla_type: SLAType,
    severity: str | None,
    base_time: int | None,
    severity_overrides: dict[str, Any] | None,
) -> int | None:
    """Get effective SLA time considering severity overrides.

    Args:
        sla_type: Type of SLA timer
        severity: Issue severity (low, medium, high, critical)
        base_time: Base SLA time in minutes from policy
        severity_overrides: Per-severity override dict

    Returns:
        Effective time limit in minutes, or None if not tracked
    """
    if not severity_overrides or not severity:
        return base_time

    override = severity_overrides.get(severity, {})
    if not override:
        return base_time

    # Map SLA type to override field
    field_map = {
        SLAType.ACKNOWLEDGE: "time_to_acknowledge",
        SLAType.PROGRESS: "time_to_progress",
        SLAType.RESOLVE: "time_to_resolve",
    }

    override_time = override.get(field_map.get(sla_type, ""))
    return override_time if override_time is not None else base_time


def compute_sla_timer(
    sla_type: SLAType,
    ctx: IssueSLAContext,
    target_minutes: int | None,
    now: datetime | None = None,
) -> SLATimer:
    """Compute SLA timer state for an issue.

    Args:
        sla_type: Type of SLA timer to compute
        ctx: Issue context with state and timestamps
        target_minutes: Target time in minutes from policy
        now: Current time (defaults to utcnow)

    Returns:
        Computed SLA timer state
    """
    now = now or datetime.now(UTC)

    # Handle no target configured
    if target_minutes is None:
        return SLATimer(
            sla_type=sla_type,
            status=SLAStatus.NOT_APPLICABLE,
            target_minutes=None,
            elapsed_minutes=0,
            remaining_minutes=None,
            breach_at=None,
            percentage=None,
        )

    # Determine start time and completion time based on SLA type
    start_at: datetime | None = None
    completed_at: datetime | None = None

    if sla_type == SLAType.ACKNOWLEDGE:
        # OPEN -> TRIAGED
        start_at = ctx.created_at
        completed_at = ctx.triaged_at
        # Not applicable if already past TRIAGED
        if ctx.status not in ("open",):
            if completed_at:
                # Was completed
                elapsed = _minutes_between(start_at, completed_at, ctx.total_blocked_minutes)
                return SLATimer(
                    sla_type=sla_type,
                    status=SLAStatus.COMPLETED,
                    target_minutes=target_minutes,
                    elapsed_minutes=elapsed,
                    remaining_minutes=max(0, target_minutes - elapsed),
                    breach_at=None,
                    percentage=(elapsed / target_minutes) * 100 if target_minutes else 0,
                )

    elif sla_type == SLAType.PROGRESS:
        # TRIAGED -> IN_PROGRESS
        start_at = ctx.triaged_at
        completed_at = ctx.in_progress_at
        # Not applicable if not yet triaged
        if ctx.status == "open":
            return SLATimer(
                sla_type=sla_type,
                status=SLAStatus.NOT_APPLICABLE,
                target_minutes=target_minutes,
                elapsed_minutes=0,
                remaining_minutes=target_minutes,
                breach_at=None,
                percentage=0,
            )
        # Completed if past triaged
        if ctx.status not in ("triaged",):
            if start_at and completed_at:
                elapsed = _minutes_between(start_at, completed_at, ctx.total_blocked_minutes)
                return SLATimer(
                    sla_type=sla_type,
                    status=SLAStatus.COMPLETED,
                    target_minutes=target_minutes,
                    elapsed_minutes=elapsed,
                    remaining_minutes=max(0, target_minutes - elapsed),
                    breach_at=None,
                    percentage=(elapsed / target_minutes) * 100 if target_minutes else 0,
                )

    elif sla_type == SLAType.RESOLVE:
        # any -> RESOLVED (tracks from creation)
        start_at = ctx.created_at
        completed_at = ctx.resolved_at
        # Completed if resolved or closed
        if ctx.status in ("resolved", "closed"):
            if completed_at:
                elapsed = _minutes_between(start_at, completed_at, ctx.total_blocked_minutes)
                return SLATimer(
                    sla_type=sla_type,
                    status=SLAStatus.COMPLETED,
                    target_minutes=target_minutes,
                    elapsed_minutes=elapsed,
                    remaining_minutes=max(0, target_minutes - elapsed),
                    breach_at=None,
                    percentage=(elapsed / target_minutes) * 100 if target_minutes else 0,
                )

    # Handle missing start time
    if start_at is None:
        return SLATimer(
            sla_type=sla_type,
            status=SLAStatus.NOT_APPLICABLE,
            target_minutes=target_minutes,
            elapsed_minutes=0,
            remaining_minutes=target_minutes,
            breach_at=None,
            percentage=0,
        )

    # Check if paused (BLOCKED status)
    if ctx.status == "blocked":
        elapsed = _minutes_between(start_at, now, ctx.total_blocked_minutes)
        return SLATimer(
            sla_type=sla_type,
            status=SLAStatus.PAUSED,
            target_minutes=target_minutes,
            elapsed_minutes=elapsed,
            remaining_minutes=max(0, target_minutes - elapsed),
            breach_at=None,
            percentage=(elapsed / target_minutes) * 100 if target_minutes else 0,
        )

    # Compute elapsed time (excluding blocked time)
    elapsed = _minutes_between(start_at, now, ctx.total_blocked_minutes)
    remaining = max(0, target_minutes - elapsed)
    percentage = (elapsed / target_minutes) * 100 if target_minutes else 0
    breach_at = start_at + timedelta(minutes=target_minutes + ctx.total_blocked_minutes)

    # Determine status based on percentage
    if elapsed >= target_minutes:
        status = SLAStatus.BREACHED
    elif percentage >= 90:
        status = SLAStatus.CRITICAL
    elif percentage >= 50:
        status = SLAStatus.AT_RISK
    else:
        status = SLAStatus.ON_TRACK

    return SLATimer(
        sla_type=sla_type,
        status=status,
        target_minutes=target_minutes,
        elapsed_minutes=elapsed,
        remaining_minutes=remaining,
        breach_at=breach_at,
        percentage=percentage,
    )


def compute_all_sla_timers(
    ctx: IssueSLAContext,
    time_to_acknowledge: int | None,
    time_to_progress: int | None,
    time_to_resolve: int | None,
    severity_overrides: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[SLAType, SLATimer]:
    """Compute all SLA timers for an issue.

    Args:
        ctx: Issue context with state and timestamps
        time_to_acknowledge: Policy time to acknowledge in minutes
        time_to_progress: Policy time to progress in minutes
        time_to_resolve: Policy time to resolve in minutes
        severity_overrides: Per-severity override dict from policy
        now: Current time (defaults to utcnow)

    Returns:
        Dict mapping SLA type to computed timer state
    """
    now = now or datetime.now(UTC)

    return {
        SLAType.ACKNOWLEDGE: compute_sla_timer(
            SLAType.ACKNOWLEDGE,
            ctx,
            get_effective_sla_time(
                SLAType.ACKNOWLEDGE, ctx.severity, time_to_acknowledge, severity_overrides
            ),
            now,
        ),
        SLAType.PROGRESS: compute_sla_timer(
            SLAType.PROGRESS,
            ctx,
            get_effective_sla_time(
                SLAType.PROGRESS, ctx.severity, time_to_progress, severity_overrides
            ),
            now,
        ),
        SLAType.RESOLVE: compute_sla_timer(
            SLAType.RESOLVE,
            ctx,
            get_effective_sla_time(
                SLAType.RESOLVE, ctx.severity, time_to_resolve, severity_overrides
            ),
            now,
        ),
    }


def get_breach_thresholds_reached(timer: SLATimer) -> list[int]:
    """Get list of breach threshold percentages that have been reached.

    Returns thresholds 50, 75, 90, 100 that the timer has passed.
    """
    if timer.percentage is None:
        return []

    thresholds = []
    for t in [50, 75, 90, 100]:
        if timer.percentage >= t:
            thresholds.append(t)

    return thresholds


def _minutes_between(start: datetime, end: datetime, blocked_minutes: int = 0) -> int:
    """Calculate minutes between two timestamps, excluding blocked time.

    Args:
        start: Start timestamp
        end: End timestamp
        blocked_minutes: Total minutes the issue was in BLOCKED state

    Returns:
        Elapsed minutes excluding blocked time
    """
    if start is None:
        return 0

    # Ensure both are timezone-aware
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    delta = end - start
    total_minutes = int(delta.total_seconds() / 60)

    # Subtract blocked time
    return max(0, total_minutes - blocked_minutes)
