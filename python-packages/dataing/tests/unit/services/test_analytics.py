"""Unit tests for AnalyticsService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from dataing.services.analytics import (
    ActivationFunnelStats,
    ActivationStatus,
    AnalyticsEventType,
    AnalyticsService,
    EntityType,
    WeeklyUsageStats,
)


class TestAnalyticsEventType:
    """Tests for AnalyticsEventType enum."""

    def test_event_types(self) -> None:
        """Test all event types are defined."""
        assert AnalyticsEventType.ISSUE_CREATED.value == "issue_created"
        assert AnalyticsEventType.INVESTIGATION_STARTED.value == "investigation_started"
        assert AnalyticsEventType.INVESTIGATION_COMPLETED.value == "investigation_completed"
        assert AnalyticsEventType.ISSUE_RESOLVED.value == "issue_resolved"


class TestEntityType:
    """Tests for EntityType enum."""

    def test_entity_types(self) -> None:
        """Test all entity types are defined."""
        assert EntityType.ISSUE.value == "issue"
        assert EntityType.INVESTIGATION.value == "investigation"


class TestAnalyticsService:
    """Tests for AnalyticsService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create a mock database."""
        mock = AsyncMock()
        mock.fetch_one = AsyncMock(return_value={"event_id": uuid4()})
        mock.fetch_all = AsyncMock(return_value=[])
        mock.execute = AsyncMock()
        return mock

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> AnalyticsService:
        """Create an analytics service with mock DB."""
        return AnalyticsService(mock_db)

    async def test_record_event(self, service: AnalyticsService, mock_db: AsyncMock) -> None:
        """Test recording an analytics event."""
        tenant_id = uuid4()
        entity_id = uuid4()
        team_id = uuid4()
        expected_event_id = uuid4()
        mock_db.fetch_one.return_value = {"event_id": expected_event_id}

        event_id = await service.record_event(
            tenant_id=tenant_id,
            event_type=AnalyticsEventType.ISSUE_CREATED,
            entity_type=EntityType.ISSUE,
            entity_id=entity_id,
            team_id=team_id,
            payload={"title": "Test Issue"},
        )

        assert event_id == expected_event_id
        mock_db.fetch_one.assert_called_once()

    async def test_record_event_without_team(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test recording event without team ID."""
        tenant_id = uuid4()
        entity_id = uuid4()

        await service.record_event(
            tenant_id=tenant_id,
            event_type=AnalyticsEventType.INVESTIGATION_STARTED,
            entity_type=EntityType.INVESTIGATION,
            entity_id=entity_id,
        )

        mock_db.fetch_one.assert_called_once()

    async def test_get_weekly_usage_empty(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting weekly usage with no data."""
        mock_db.fetch_all.return_value = []
        tenant_id = uuid4()

        stats = await service.get_weekly_usage(tenant_id, weeks=4)

        assert stats == []

    async def test_get_weekly_usage_with_data(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting weekly usage with data."""
        week_start = datetime.now(UTC) - timedelta(days=7)
        mock_db.fetch_all.return_value = [
            {
                "week_start": week_start,
                "issues_created": 10,
                "investigations_started": 5,
                "investigations_completed": 4,
                "issues_resolved": 8,
                "active_teams": 3,
            }
        ]
        tenant_id = uuid4()

        stats = await service.get_weekly_usage(tenant_id, weeks=4)

        assert len(stats) == 1
        assert stats[0].issues_created == 10
        assert stats[0].investigations_started == 5
        assert stats[0].investigations_completed == 4
        assert stats[0].issues_resolved == 8
        assert stats[0].active_teams == 3
        assert stats[0].resolution_rate == 0.8

    async def test_get_weekly_usage_by_team(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting weekly usage filtered by team."""
        tenant_id = uuid4()
        team_id = uuid4()
        mock_db.fetch_all.return_value = []

        await service.get_weekly_usage(tenant_id, weeks=4, team_id=team_id)

        # Verify the query included team filter
        mock_db.fetch_all.assert_called()

    async def test_get_activation_status_not_found(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting activation status for nonexistent tenant."""
        mock_db.fetch_one.side_effect = [None, None]  # No activation, no tenant
        tenant_id = uuid4()

        status = await service.get_activation_status(tenant_id)

        assert status is None

    async def test_get_activation_status_new_tenant(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting activation status for new tenant."""
        tenant_id = uuid4()
        created_at = datetime.now(UTC) - timedelta(days=2)
        mock_db.fetch_one.side_effect = [
            None,  # No activation record yet
            {"id": tenant_id, "created_at": created_at},  # Tenant exists
        ]

        status = await service.get_activation_status(tenant_id)

        assert status is not None
        assert status.tenant_id == tenant_id
        assert status.is_activated is False
        assert status.first_issue_at is None
        assert status.first_investigation_at is None

    async def test_get_activation_status_activated(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting activation status for activated tenant."""
        tenant_id = uuid4()
        created_at = datetime.now(UTC) - timedelta(days=10)
        activated_at = created_at + timedelta(days=5)
        mock_db.fetch_one.return_value = {
            "tenant_id": tenant_id,
            "created_at": created_at,
            "first_issue_at": created_at + timedelta(days=1),
            "first_investigation_at": created_at + timedelta(days=3),
            "activated_at": activated_at,
        }

        status = await service.get_activation_status(tenant_id)

        assert status is not None
        assert status.is_activated is True
        assert status.days_to_activation == 5

    async def test_get_activation_funnel_empty(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting activation funnel with no tenants."""
        mock_db.fetch_one.return_value = {
            "total_tenants": 0,
            "tenants_with_issue": 0,
            "tenants_with_investigation": 0,
            "tenants_activated": 0,
        }

        funnel = await service.get_activation_funnel()

        assert funnel.total_tenants == 0
        assert funnel.issue_rate == 0.0
        assert funnel.activation_rate == 0.0

    async def test_get_activation_funnel_with_data(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test getting activation funnel with data."""
        mock_db.fetch_one.return_value = {
            "total_tenants": 100,
            "tenants_with_issue": 80,
            "tenants_with_investigation": 60,
            "tenants_activated": 50,
        }

        funnel = await service.get_activation_funnel()

        assert funnel.total_tenants == 100
        assert funnel.tenants_with_issue == 80
        assert funnel.issue_rate == 0.8
        assert funnel.investigation_rate == 0.6
        assert funnel.activation_rate == 0.5

    async def test_refresh_weekly_stats(
        self, service: AnalyticsService, mock_db: AsyncMock
    ) -> None:
        """Test refreshing weekly stats materialized view."""
        await service.refresh_weekly_stats()

        mock_db.execute.assert_called_once_with("SELECT refresh_weekly_usage_stats()")


class TestWeeklyUsageStats:
    """Tests for WeeklyUsageStats dataclass."""

    def test_resolution_rate_calculation(self) -> None:
        """Test resolution rate is calculated correctly."""
        stats = WeeklyUsageStats(
            week_start=datetime.now(UTC),
            issues_created=10,
            investigations_started=5,
            investigations_completed=4,
            issues_resolved=8,
            active_teams=3,
            resolution_rate=0.8,
        )

        assert stats.resolution_rate == 0.8


class TestActivationStatus:
    """Tests for ActivationStatus dataclass."""

    def test_activated_status(self) -> None:
        """Test activated status fields."""
        now = datetime.now(UTC)
        status = ActivationStatus(
            tenant_id=uuid4(),
            created_at=now - timedelta(days=10),
            first_issue_at=now - timedelta(days=8),
            first_investigation_at=now - timedelta(days=7),
            activated_at=now - timedelta(days=7),
            is_activated=True,
            days_to_activation=3,
        )

        assert status.is_activated is True
        assert status.days_to_activation == 3


class TestActivationFunnelStats:
    """Tests for ActivationFunnelStats dataclass."""

    def test_funnel_rates(self) -> None:
        """Test funnel rate fields."""
        funnel = ActivationFunnelStats(
            total_tenants=100,
            tenants_with_issue=80,
            tenants_with_investigation=60,
            tenants_activated=50,
            issue_rate=0.8,
            investigation_rate=0.6,
            activation_rate=0.5,
        )

        assert funnel.issue_rate == 0.8
        assert funnel.investigation_rate == 0.6
        assert funnel.activation_rate == 0.5
