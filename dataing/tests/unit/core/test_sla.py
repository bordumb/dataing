"""Unit tests for SLA computation helpers."""

from datetime import UTC, datetime, timedelta

from dataing.core.sla import (
    IssueSLAContext,
    SLAStatus,
    SLAType,
    compute_all_sla_timers,
    compute_sla_timer,
    get_breach_thresholds_reached,
    get_effective_sla_time,
)


class TestGetEffectiveSLATime:
    """Test severity override logic."""

    def test_no_overrides_returns_base(self) -> None:
        """Test returns base time when no overrides."""
        result = get_effective_sla_time(SLAType.ACKNOWLEDGE, "critical", 60, None)
        assert result == 60

    def test_no_severity_returns_base(self) -> None:
        """Test returns base time when no severity."""
        overrides = {"critical": {"time_to_acknowledge": 15}}
        result = get_effective_sla_time(SLAType.ACKNOWLEDGE, None, 60, overrides)
        assert result == 60

    def test_override_applied(self) -> None:
        """Test severity override is applied."""
        overrides = {"critical": {"time_to_acknowledge": 15}}
        result = get_effective_sla_time(SLAType.ACKNOWLEDGE, "critical", 60, overrides)
        assert result == 15

    def test_override_not_found_returns_base(self) -> None:
        """Test returns base when override not found for severity."""
        overrides = {"critical": {"time_to_acknowledge": 15}}
        result = get_effective_sla_time(SLAType.ACKNOWLEDGE, "medium", 60, overrides)
        assert result == 60

    def test_override_field_not_found_returns_base(self) -> None:
        """Test returns base when specific field not in override."""
        overrides = {"critical": {"time_to_resolve": 120}}
        result = get_effective_sla_time(SLAType.ACKNOWLEDGE, "critical", 60, overrides)
        assert result == 60


class TestComputeSLATimer:
    """Test individual SLA timer computation."""

    def test_no_target_returns_not_applicable(self) -> None:
        """Test returns NOT_APPLICABLE when no target time configured."""
        ctx = IssueSLAContext(
            status="open",
            severity="high",
            created_at=datetime.now(UTC),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.ACKNOWLEDGE, ctx, None)
        assert timer.status == SLAStatus.NOT_APPLICABLE
        assert timer.target_minutes is None

    def test_acknowledge_on_track(self) -> None:
        """Test acknowledge timer on track."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="open",
            severity="high",
            created_at=now - timedelta(minutes=10),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.ACKNOWLEDGE, ctx, 60, now)
        assert timer.status == SLAStatus.ON_TRACK
        assert timer.elapsed_minutes == 10
        assert timer.remaining_minutes == 50
        assert timer.percentage is not None
        assert timer.percentage < 50

    def test_acknowledge_at_risk(self) -> None:
        """Test acknowledge timer at risk (50-90%)."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="open",
            severity="high",
            created_at=now - timedelta(minutes=35),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.ACKNOWLEDGE, ctx, 60, now)
        assert timer.status == SLAStatus.AT_RISK
        assert timer.percentage is not None
        assert 50 <= timer.percentage < 90

    def test_acknowledge_critical(self) -> None:
        """Test acknowledge timer critical (90-100%)."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="open",
            severity="high",
            created_at=now - timedelta(minutes=55),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.ACKNOWLEDGE, ctx, 60, now)
        assert timer.status == SLAStatus.CRITICAL
        assert timer.percentage is not None
        assert timer.percentage >= 90

    def test_acknowledge_breached(self) -> None:
        """Test acknowledge timer breached."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="open",
            severity="high",
            created_at=now - timedelta(minutes=70),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.ACKNOWLEDGE, ctx, 60, now)
        assert timer.status == SLAStatus.BREACHED
        assert timer.elapsed_minutes >= 60

    def test_acknowledge_completed(self) -> None:
        """Test acknowledge timer completed."""
        now = datetime.now(UTC)
        created = now - timedelta(minutes=30)
        triaged = now - timedelta(minutes=10)
        ctx = IssueSLAContext(
            status="triaged",
            severity="high",
            created_at=created,
            triaged_at=triaged,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.ACKNOWLEDGE, ctx, 60, now)
        assert timer.status == SLAStatus.COMPLETED
        assert timer.elapsed_minutes == 20  # 30 - 10 = 20 minutes

    def test_blocked_pauses_timer(self) -> None:
        """Test timer is paused when issue is blocked."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="blocked",
            severity="high",
            created_at=now - timedelta(minutes=30),
            triaged_at=now - timedelta(minutes=20),
            in_progress_at=now - timedelta(minutes=10),
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.RESOLVE, ctx, 120, now)
        assert timer.status == SLAStatus.PAUSED

    def test_blocked_time_excluded(self) -> None:
        """Test blocked time is excluded from elapsed time."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="in_progress",
            severity="high",
            created_at=now - timedelta(minutes=60),
            triaged_at=now - timedelta(minutes=50),
            in_progress_at=now - timedelta(minutes=40),
            resolved_at=None,
            total_blocked_minutes=20,  # 20 minutes of blocked time
        )
        timer = compute_sla_timer(SLAType.RESOLVE, ctx, 120, now)
        # 60 minutes elapsed minus 20 blocked = 40 effective
        assert timer.elapsed_minutes == 40

    def test_progress_not_applicable_when_open(self) -> None:
        """Test progress timer not applicable when issue is still open."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="open",
            severity="high",
            created_at=now - timedelta(minutes=30),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timer = compute_sla_timer(SLAType.PROGRESS, ctx, 30, now)
        assert timer.status == SLAStatus.NOT_APPLICABLE


class TestComputeAllSLATimers:
    """Test computing all SLA timers at once."""

    def test_all_timers_computed(self) -> None:
        """Test all three timers are computed."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="open",
            severity="high",
            created_at=now - timedelta(minutes=10),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        timers = compute_all_sla_timers(ctx, 60, 30, 120, None, now)

        assert SLAType.ACKNOWLEDGE in timers
        assert SLAType.PROGRESS in timers
        assert SLAType.RESOLVE in timers

    def test_severity_overrides_applied(self) -> None:
        """Test severity overrides are applied to all timers."""
        now = datetime.now(UTC)
        ctx = IssueSLAContext(
            status="open",
            severity="critical",
            created_at=now - timedelta(minutes=10),
            triaged_at=None,
            in_progress_at=None,
            resolved_at=None,
            total_blocked_minutes=0,
        )
        overrides = {
            "critical": {
                "time_to_acknowledge": 15,
                "time_to_resolve": 60,
            }
        }
        timers = compute_all_sla_timers(ctx, 60, 30, 120, overrides, now)

        # Acknowledge should use override (15)
        assert timers[SLAType.ACKNOWLEDGE].target_minutes == 15
        # Progress should use base (30) - no override
        assert timers[SLAType.PROGRESS].target_minutes == 30
        # Resolve should use override (60)
        assert timers[SLAType.RESOLVE].target_minutes == 60


class TestGetBreachThresholdsReached:
    """Test breach threshold detection."""

    def test_no_percentage_returns_empty(self) -> None:
        """Test returns empty list when percentage is None."""
        from dataing.core.sla import SLATimer

        timer = SLATimer(
            sla_type=SLAType.ACKNOWLEDGE,
            status=SLAStatus.NOT_APPLICABLE,
            target_minutes=None,
            elapsed_minutes=0,
            remaining_minutes=None,
            breach_at=None,
            percentage=None,
        )
        result = get_breach_thresholds_reached(timer)
        assert result == []

    def test_under_50_returns_empty(self) -> None:
        """Test returns empty list when under 50%."""
        from dataing.core.sla import SLATimer

        timer = SLATimer(
            sla_type=SLAType.ACKNOWLEDGE,
            status=SLAStatus.ON_TRACK,
            target_minutes=60,
            elapsed_minutes=20,
            remaining_minutes=40,
            breach_at=None,
            percentage=33.3,
        )
        result = get_breach_thresholds_reached(timer)
        assert result == []

    def test_at_50_returns_50(self) -> None:
        """Test returns [50] when at 50%."""
        from dataing.core.sla import SLATimer

        timer = SLATimer(
            sla_type=SLAType.ACKNOWLEDGE,
            status=SLAStatus.AT_RISK,
            target_minutes=60,
            elapsed_minutes=30,
            remaining_minutes=30,
            breach_at=None,
            percentage=50.0,
        )
        result = get_breach_thresholds_reached(timer)
        assert result == [50]

    def test_at_75_returns_50_75(self) -> None:
        """Test returns [50, 75] when at 75%."""
        from dataing.core.sla import SLATimer

        timer = SLATimer(
            sla_type=SLAType.ACKNOWLEDGE,
            status=SLAStatus.AT_RISK,
            target_minutes=60,
            elapsed_minutes=45,
            remaining_minutes=15,
            breach_at=None,
            percentage=75.0,
        )
        result = get_breach_thresholds_reached(timer)
        assert result == [50, 75]

    def test_at_100_returns_all(self) -> None:
        """Test returns all thresholds when breached."""
        from dataing.core.sla import SLATimer

        timer = SLATimer(
            sla_type=SLAType.ACKNOWLEDGE,
            status=SLAStatus.BREACHED,
            target_minutes=60,
            elapsed_minutes=60,
            remaining_minutes=0,
            breach_at=None,
            percentage=100.0,
        )
        result = get_breach_thresholds_reached(timer)
        assert result == [50, 75, 90, 100]

    def test_over_100_returns_all(self) -> None:
        """Test returns all thresholds when over 100%."""
        from dataing.core.sla import SLATimer

        timer = SLATimer(
            sla_type=SLAType.ACKNOWLEDGE,
            status=SLAStatus.BREACHED,
            target_minutes=60,
            elapsed_minutes=90,
            remaining_minutes=0,
            breach_at=None,
            percentage=150.0,
        )
        result = get_breach_thresholds_reached(timer)
        assert result == [50, 75, 90, 100]
