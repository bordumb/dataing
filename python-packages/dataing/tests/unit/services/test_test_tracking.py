"""Tests for the test tracking service."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.services.test_tracking import (
    TestTrackingService,
)


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.fetch_one = AsyncMock()
    db.fetch_all = AsyncMock()
    return db


@pytest.fixture
def tracker(mock_db: MagicMock) -> TestTrackingService:
    """Create a test tracking service instance."""
    return TestTrackingService(mock_db)


class TestRecordTestGenerated:
    async def test_records_test_with_all_fields(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test recording a generated test with all fields."""
        tenant_id = uuid4()
        investigation_id = uuid4()
        test_id = uuid4()

        result = await tracker.record_test_generated(
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            test_id=test_id,
            format_="dbt",
            test_type="not_null",
            table="orders",
            column="customer_id",
            description="customer_id should not be null",
        )

        assert result == test_id
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "INSERT INTO generated_tests" in call_args[0][0]

    async def test_records_test_without_column(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test recording a table-level test without column."""
        tenant_id = uuid4()
        investigation_id = uuid4()
        test_id = uuid4()

        result = await tracker.record_test_generated(
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            test_id=test_id,
            format_="sql",
            test_type="row_count",
            table="orders",
            column=None,
            description="orders table row count check",
        )

        assert result == test_id


class TestRecordTestAdopted:
    async def test_marks_test_as_adopted(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test marking a test as adopted."""
        tenant_id = uuid4()
        test_id = uuid4()
        mock_db.execute.return_value = 1  # Rows affected

        result = await tracker.record_test_adopted(
            tenant_id=tenant_id,
            test_id=test_id,
            adopted_by="user@example.com",
        )

        assert result is True
        mock_db.execute.assert_called_once()

    async def test_returns_false_if_not_found(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test returns False if test not found."""
        tenant_id = uuid4()
        test_id = uuid4()
        mock_db.execute.return_value = 0  # No rows affected

        result = await tracker.record_test_adopted(
            tenant_id=tenant_id,
            test_id=test_id,
        )

        assert result is False


class TestRecordTestRun:
    async def test_records_passing_test(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test recording a passing test run."""
        tenant_id = uuid4()
        test_id = uuid4()

        await tracker.record_test_run(
            tenant_id=tenant_id,
            test_id=test_id,
            passed=True,
        )

        # Should update stats and insert run record
        assert mock_db.execute.call_count == 2

    async def test_records_failing_test(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test recording a failing test run."""
        tenant_id = uuid4()
        test_id = uuid4()

        await tracker.record_test_run(
            tenant_id=tenant_id,
            test_id=test_id,
            passed=False,
            failure_message="Expected 0 nulls, found 150",
        )

        assert mock_db.execute.call_count == 2


class TestGetTest:
    async def test_returns_test_if_found(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test returning a test by ID."""
        tenant_id = uuid4()
        test_id = uuid4()
        investigation_id = uuid4()

        mock_db.fetch_one.return_value = {
            "id": test_id,
            "investigation_id": investigation_id,
            "tenant_id": tenant_id,
            "format": "dbt",
            "test_type": "not_null",
            "table_name": "orders",
            "column_name": "customer_id",
            "description": "customer_id should not be null",
            "created_at": datetime.now(UTC),
            "adopted_at": None,
            "last_run_at": None,
            "run_count": 0,
            "failure_count": 0,
        }

        result = await tracker.get_test(tenant_id, test_id)

        assert result is not None
        assert result.test_id == test_id
        assert result.test_type == "not_null"
        assert result.table == "orders"

    async def test_returns_none_if_not_found(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test returns None if test not found."""
        mock_db.fetch_one.return_value = None

        result = await tracker.get_test(uuid4(), uuid4())

        assert result is None


class TestGetStats:
    async def test_returns_stats(self, tracker: TestTrackingService, mock_db: MagicMock) -> None:
        """Test getting test tracking stats."""
        tenant_id = uuid4()

        mock_db.fetch_one.return_value = {
            "tests_generated": 10,
            "tests_adopted": 5,
            "total_runs": 20,
            "total_failures": 3,
        }

        result = await tracker.get_stats(tenant_id, days=30)

        assert result.tests_generated == 10
        assert result.tests_adopted == 5
        assert result.tests_run == 20
        assert result.issues_caught == 3
        assert result.adoption_rate == 0.5
        assert result.effectiveness_rate == 0.3

    async def test_handles_empty_results(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test handles empty results gracefully."""
        mock_db.fetch_one.return_value = None

        result = await tracker.get_stats(uuid4(), days=30)

        assert result.tests_generated == 0
        assert result.adoption_rate == 0.0
        assert result.effectiveness_rate == 0.0


class TestGetRecentCatches:
    async def test_returns_recent_catches(
        self, tracker: TestTrackingService, mock_db: MagicMock
    ) -> None:
        """Test getting recent test failure catches."""
        tenant_id = uuid4()
        test_id = uuid4()
        investigation_id = uuid4()

        mock_db.fetch_all.return_value = [
            {
                "test_id": test_id,
                "run_at": datetime.now(UTC),
                "failure_message": "NULL rate exceeded threshold",
                "test_type": "not_null",
                "table_name": "orders",
                "column_name": "customer_id",
                "investigation_id": investigation_id,
            }
        ]

        result = await tracker.get_recent_catches(tenant_id, limit=10)

        assert len(result) == 1
        assert result[0]["test_type"] == "not_null"
        assert "failure_message" in result[0]
