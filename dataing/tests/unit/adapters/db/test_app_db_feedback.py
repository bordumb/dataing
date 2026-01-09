"""Tests for AppDatabase feedback methods."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from dataing.adapters.db.app_db import AppDatabase


class TestAppDatabaseFeedback:
    """Tests for feedback-related database methods."""

    @pytest.fixture
    def db(self) -> AppDatabase:
        """Create AppDatabase instance."""
        return AppDatabase(dsn="postgresql://localhost/test")  # pragma: allowlist secret

    async def test_list_feedback_events_for_investigation(self, db: AppDatabase) -> None:
        """list_feedback_events returns events for an investigation."""
        tenant_id = uuid4()
        investigation_id = uuid4()

        with patch.object(db, "fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "id": uuid4(),
                    "event_type": "investigation.started",
                    "event_data": {},
                    "created_at": datetime.now(UTC),
                }
            ]

            events = await db.list_feedback_events(
                tenant_id=tenant_id,
                investigation_id=investigation_id,
            )

            assert len(events) == 1
            mock_fetch.assert_called_once()
            assert "investigation_id" in mock_fetch.call_args[0][0]

    async def test_list_feedback_events_for_dataset(self, db: AppDatabase) -> None:
        """list_feedback_events returns events for a dataset."""
        tenant_id = uuid4()
        dataset_id = uuid4()

        with patch.object(db, "fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            events = await db.list_feedback_events(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
            )

            assert events == []
            assert "dataset_id" in mock_fetch.call_args[0][0]

    async def test_count_feedback_events(self, db: AppDatabase) -> None:
        """count_feedback_events returns event count."""
        tenant_id = uuid4()

        with patch.object(db, "fetch_one", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"count": 42}

            count = await db.count_feedback_events(tenant_id=tenant_id)

            assert count == 42
