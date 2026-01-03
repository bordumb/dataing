"""Unit tests for UsageTracker."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from dataing.services.usage import UsageSummary, UsageTracker


class TestUsageTracker:
    """Tests for UsageTracker."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database."""
        mock = AsyncMock()
        mock.record_usage.return_value = None
        mock.get_monthly_usage.return_value = []
        mock.fetch_all.return_value = []
        return mock

    @pytest.fixture
    def tracker(self, mock_db: AsyncMock) -> UsageTracker:
        """Return a usage tracker."""
        return UsageTracker(db=mock_db)

    @pytest.fixture
    def tenant_id(self) -> uuid.UUID:
        """Return a sample tenant ID."""
        return uuid.uuid4()

    async def test_record_llm_usage(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test recording LLM usage."""
        cost = await tracker.record_llm_usage(
            tenant_id=tenant_id,
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
        )

        assert cost > 0
        mock_db.record_usage.assert_called_once()
        call_kwargs = mock_db.record_usage.call_args.kwargs
        assert call_kwargs["resource_type"] == "llm_tokens"
        assert call_kwargs["quantity"] == 1500  # input + output

    async def test_record_llm_usage_with_investigation(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test recording LLM usage with investigation ID."""
        inv_id = uuid.uuid4()

        await tracker.record_llm_usage(
            tenant_id=tenant_id,
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=100,
            investigation_id=inv_id,
        )

        call_kwargs = mock_db.record_usage.call_args.kwargs
        assert call_kwargs["metadata"]["investigation_id"] == str(inv_id)

    async def test_record_llm_usage_unknown_model(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test recording LLM usage with unknown model uses default pricing."""
        cost = await tracker.record_llm_usage(
            tenant_id=tenant_id,
            model="unknown-model",
            input_tokens=1000,
            output_tokens=1000,
        )

        # Default pricing is higher than known models
        assert cost > 0

    async def test_record_query_execution(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test recording query execution."""
        await tracker.record_query_execution(
            tenant_id=tenant_id,
            data_source_type="postgres",
            rows_scanned=1000,
        )

        mock_db.record_usage.assert_called_once()
        call_kwargs = mock_db.record_usage.call_args.kwargs
        assert call_kwargs["resource_type"] == "query_execution"
        assert call_kwargs["quantity"] == 1

    async def test_record_investigation(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test recording investigation."""
        inv_id = uuid.uuid4()

        await tracker.record_investigation(
            tenant_id=tenant_id,
            investigation_id=inv_id,
            status="completed",
        )

        mock_db.record_usage.assert_called_once()
        call_kwargs = mock_db.record_usage.call_args.kwargs
        assert call_kwargs["resource_type"] == "investigation"
        assert call_kwargs["unit_cost"] == 0.05  # Completed cost

    async def test_record_investigation_failed(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test recording failed investigation has lower cost."""
        await tracker.record_investigation(
            tenant_id=tenant_id,
            investigation_id=uuid.uuid4(),
            status="failed",
        )

        call_kwargs = mock_db.record_usage.call_args.kwargs
        assert call_kwargs["unit_cost"] == 0.01  # Failed cost

    async def test_get_monthly_usage(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test getting monthly usage summary."""
        mock_db.get_monthly_usage.return_value = [
            {"resource_type": "llm_tokens", "total_quantity": 10000, "total_cost": 0.50},
            {"resource_type": "query_execution", "total_quantity": 100, "total_cost": 0.10},
            {"resource_type": "investigation", "total_quantity": 5, "total_cost": 0.25},
        ]

        result = await tracker.get_monthly_usage(tenant_id)

        assert isinstance(result, UsageSummary)
        assert result.llm_tokens == 10000
        assert result.llm_cost == 0.50
        assert result.query_executions == 100
        assert result.investigations == 5
        assert result.total_cost == 0.85

    async def test_get_monthly_usage_empty(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test getting monthly usage with no data."""
        result = await tracker.get_monthly_usage(tenant_id)

        assert result.llm_tokens == 0
        assert result.total_cost == 0.0

    async def test_get_monthly_usage_specific_month(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test getting monthly usage for specific month."""
        await tracker.get_monthly_usage(tenant_id, year=2024, month=6)

        mock_db.get_monthly_usage.assert_called_once_with(tenant_id, 2024, 6)

    async def test_check_quota_returns_true(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
    ) -> None:
        """Test quota check always returns True (placeholder)."""
        result = await tracker.check_quota(
            tenant_id=tenant_id,
            resource_type="llm_tokens",
            quantity=1000,
        )

        assert result is True

    async def test_get_daily_trend(
        self,
        tracker: UsageTracker,
        tenant_id: uuid.UUID,
        mock_db: AsyncMock,
    ) -> None:
        """Test getting daily usage trend."""
        mock_db.fetch_all.return_value = [
            {"date": "2024-01-15", "quantity": 1000, "cost": 0.10},
            {"date": "2024-01-14", "quantity": 800, "cost": 0.08},
        ]

        result = await tracker.get_daily_trend(tenant_id, days=30)

        assert len(result) == 2
        mock_db.fetch_all.assert_called_once()


class TestUsageSummary:
    """Tests for UsageSummary."""

    def test_create_summary(self) -> None:
        """Test creating usage summary."""
        summary = UsageSummary(
            llm_tokens=10000,
            llm_cost=0.50,
            query_executions=100,
            investigations=5,
            total_cost=1.00,
        )

        assert summary.llm_tokens == 10000
        assert summary.total_cost == 1.00
