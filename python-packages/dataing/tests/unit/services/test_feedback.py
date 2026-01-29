"""Tests for fix feedback service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.adapters.investigation_feedback.types import EventType
from dataing.services.feedback import (
    FeedbackExportRecord,
    FixFeedback,
    FixFeedbackRating,
    FixFeedbackService,
    FixSuccessAlert,
    FixSuccessStats,
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
def mock_feedback_adapter() -> MagicMock:
    """Create a mock feedback adapter."""
    adapter = MagicMock()
    adapter.emit = AsyncMock()
    return adapter


class TestFixFeedbackService:
    """Tests for FixFeedbackService."""

    async def test_record_feedback_success(
        self, mock_db: MagicMock, mock_feedback_adapter: MagicMock
    ) -> None:
        """Test recording feedback successfully."""
        service = FixFeedbackService(db=mock_db, feedback_adapter=mock_feedback_adapter)

        fix_execution_id = uuid4()
        investigation_id = uuid4()
        tenant_id = uuid4()
        user_id = uuid4()

        feedback = await service.record_feedback(
            fix_execution_id=fix_execution_id,
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            rating=FixFeedbackRating.YES,
            fix_type="sql_dml",
            comment="Fixed the issue perfectly!",
            root_cause_category="null_values",
        )

        assert feedback.rating == FixFeedbackRating.YES
        assert feedback.fix_type == "sql_dml"
        assert feedback.comment == "Fixed the issue perfectly!"
        assert feedback.root_cause_category == "null_values"
        mock_db.execute.assert_called_once()
        mock_feedback_adapter.emit.assert_called_once()

    async def test_record_feedback_emits_event(
        self, mock_db: MagicMock, mock_feedback_adapter: MagicMock
    ) -> None:
        """Test that recording feedback emits the correct event."""
        service = FixFeedbackService(db=mock_db, feedback_adapter=mock_feedback_adapter)

        fix_execution_id = uuid4()
        investigation_id = uuid4()
        tenant_id = uuid4()
        user_id = uuid4()

        await service.record_feedback(
            fix_execution_id=fix_execution_id,
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            rating=FixFeedbackRating.NO,
            fix_type="sql_ddl",
        )

        mock_feedback_adapter.emit.assert_called_once()
        call_args = mock_feedback_adapter.emit.call_args
        assert call_args.kwargs["event_type"] == EventType.FEEDBACK_FIX
        assert call_args.kwargs["tenant_id"] == tenant_id
        assert call_args.kwargs["investigation_id"] == investigation_id
        assert call_args.kwargs["actor_id"] == user_id
        assert call_args.kwargs["actor_type"] == "user"

    async def test_record_feedback_without_db(self, mock_feedback_adapter: MagicMock) -> None:
        """Test recording feedback without database."""
        service = FixFeedbackService(db=None, feedback_adapter=mock_feedback_adapter)

        feedback = await service.record_feedback(
            fix_execution_id=uuid4(),
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            rating=FixFeedbackRating.PARTIALLY,
            fix_type="python_patch",
        )

        assert feedback.rating == FixFeedbackRating.PARTIALLY
        # Event should still be emitted
        mock_feedback_adapter.emit.assert_called_once()

    async def test_get_success_stats(self, mock_db: MagicMock) -> None:
        """Test getting success statistics."""
        mock_db.fetch_one.return_value = {
            "total": 100,
            "successful": 70,
            "failed": 20,
            "partial": 10,
        }

        service = FixFeedbackService(db=mock_db)
        tenant_id = uuid4()

        stats = await service.get_success_stats(tenant_id)

        assert stats.total_fixes == 100
        assert stats.successful == 70
        assert stats.failed == 20
        assert stats.partial == 10
        assert stats.success_rate == 0.7
        assert stats.effective_rate == 0.8  # (70 + 10) / 100

    async def test_get_success_stats_no_data(self, mock_db: MagicMock) -> None:
        """Test getting success stats with no data."""
        mock_db.fetch_one.return_value = {"total": 0, "successful": 0, "failed": 0, "partial": 0}

        service = FixFeedbackService(db=mock_db)

        stats = await service.get_success_stats(uuid4())

        assert stats.total_fixes == 0
        assert stats.success_rate == 0.0
        assert stats.effective_rate == 0.0

    async def test_get_success_stats_with_filter(self, mock_db: MagicMock) -> None:
        """Test getting success stats with fix type filter."""
        mock_db.fetch_one.return_value = {
            "total": 50,
            "successful": 40,
            "failed": 5,
            "partial": 5,
        }

        service = FixFeedbackService(db=mock_db)

        stats = await service.get_success_stats(
            uuid4(),
            fix_type="sql_dml",
            days=7,
        )

        assert stats.total_fixes == 50
        assert stats.success_rate == 0.8

    async def test_get_success_stats_without_db(self) -> None:
        """Test getting success stats without database returns empty stats."""
        service = FixFeedbackService(db=None)

        stats = await service.get_success_stats(uuid4())

        assert stats.total_fixes == 0
        assert stats.success_rate == 0.0

    async def test_get_success_stats_by_fix_type(self, mock_db: MagicMock) -> None:
        """Test getting success stats grouped by fix type."""
        mock_db.fetch_all.return_value = [
            {"fix_type": "sql_dml", "total": 60, "successful": 50, "failed": 5, "partial": 5},
            {"fix_type": "sql_ddl", "total": 40, "successful": 30, "failed": 8, "partial": 2},
        ]

        service = FixFeedbackService(db=mock_db)

        stats_by_type = await service.get_success_stats_by_fix_type(uuid4())

        assert len(stats_by_type) == 2
        assert "sql_dml" in stats_by_type
        assert "sql_ddl" in stats_by_type
        assert stats_by_type["sql_dml"].success_rate == pytest.approx(50 / 60)
        assert stats_by_type["sql_ddl"].success_rate == pytest.approx(30 / 40)

    async def test_check_for_alerts_low_success_rate(self, mock_db: MagicMock) -> None:
        """Test that alerts are generated for low success rates."""
        mock_db.fetch_all.return_value = [
            {"fix_type": "sql_dml", "total": 20, "successful": 8, "failed": 10, "partial": 2},
        ]

        service = FixFeedbackService(
            db=mock_db,
            low_success_threshold=0.5,
            min_samples_for_alert=10,
        )
        tenant_id = uuid4()

        alerts = await service.check_for_alerts(tenant_id)

        assert len(alerts) == 1
        assert alerts[0].category == "sql_dml"
        assert alerts[0].category_type == "fix_type"
        assert alerts[0].success_rate == 0.4
        assert "low success rate" in alerts[0].message

    async def test_check_for_alerts_no_alert_above_threshold(self, mock_db: MagicMock) -> None:
        """Test no alerts when success rate is above threshold."""
        mock_db.fetch_all.return_value = [
            {"fix_type": "sql_dml", "total": 20, "successful": 15, "failed": 3, "partial": 2},
        ]

        service = FixFeedbackService(
            db=mock_db,
            low_success_threshold=0.5,
            min_samples_for_alert=10,
        )

        alerts = await service.check_for_alerts(uuid4())

        assert len(alerts) == 0

    async def test_check_for_alerts_not_enough_samples(self, mock_db: MagicMock) -> None:
        """Test no alerts when sample count is below minimum."""
        mock_db.fetch_all.return_value = [
            {"fix_type": "sql_dml", "total": 5, "successful": 1, "failed": 4, "partial": 0},
        ]

        service = FixFeedbackService(
            db=mock_db,
            low_success_threshold=0.5,
            min_samples_for_alert=10,
        )

        alerts = await service.check_for_alerts(uuid4())

        assert len(alerts) == 0  # Not enough samples

    async def test_export_feedback_for_finetuning(self, mock_db: MagicMock) -> None:
        """Test exporting feedback for fine-tuning."""
        fix_execution_id = uuid4()
        investigation_id = uuid4()

        mock_db.fetch_all.return_value = [
            {
                "fix_execution_id": fix_execution_id,
                "investigation_id": investigation_id,
                "fix_type": "sql_dml",
                "fix_code": "UPDATE orders SET status = 'fixed'",
                "rating": "yes",
                "comment": "Worked great",
                "root_cause_category": "null_values",
            },
        ]

        mock_db.fetch_one.return_value = {
            "issue_id": uuid4(),
            "investigation_created_at": datetime.now(UTC),
        }

        service = FixFeedbackService(db=mock_db)

        records = await service.export_feedback_for_finetuning(
            uuid4(),
            include_context=True,
        )

        assert len(records) == 1
        assert records[0].fix_type == "sql_dml"
        assert records[0].rating == "yes"
        assert records[0].comment == "Worked great"
        assert "issue_id" in records[0].context

    async def test_export_feedback_without_context(self, mock_db: MagicMock) -> None:
        """Test exporting feedback without context."""
        mock_db.fetch_all.return_value = [
            {
                "fix_execution_id": uuid4(),
                "investigation_id": uuid4(),
                "fix_type": "sql_ddl",
                "fix_code": "ALTER TABLE orders ADD COLUMN new_col TEXT",
                "rating": "partially",
                "comment": None,
                "root_cause_category": None,
            },
        ]

        service = FixFeedbackService(db=mock_db)

        records = await service.export_feedback_for_finetuning(
            uuid4(),
            include_context=False,
        )

        assert len(records) == 1
        assert records[0].context == {}

    async def test_export_feedback_without_db(self) -> None:
        """Test exporting feedback without database returns empty list."""
        service = FixFeedbackService(db=None)

        records = await service.export_feedback_for_finetuning(uuid4())

        assert records == []

    async def test_get_feedback_from_cache(self, mock_db: MagicMock) -> None:
        """Test retrieving feedback from cache."""
        service = FixFeedbackService(db=mock_db)

        feedback = await service.record_feedback(
            fix_execution_id=uuid4(),
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            rating=FixFeedbackRating.YES,
            fix_type="sql_dml",
        )

        cached = service.get_feedback(feedback.id)

        assert cached is not None
        assert cached.id == feedback.id

    def test_get_feedback_not_found(self) -> None:
        """Test retrieving non-existent feedback returns None."""
        service = FixFeedbackService(db=None)

        result = service.get_feedback(uuid4())

        assert result is None


class TestFixFeedback:
    """Tests for FixFeedback dataclass."""

    def test_create_feedback(self) -> None:
        """Test creating a feedback record."""
        feedback = FixFeedback(
            fix_execution_id=uuid4(),
            investigation_id=uuid4(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            rating=FixFeedbackRating.YES,
            fix_type="sql_dml",
            comment="Perfect fix!",
            root_cause_category="duplicates",
        )

        assert feedback.rating == FixFeedbackRating.YES
        assert feedback.fix_type == "sql_dml"
        assert feedback.comment == "Perfect fix!"
        assert feedback.id is not None
        assert feedback.created_at is not None


class TestFixSuccessStats:
    """Tests for FixSuccessStats dataclass."""

    def test_create_stats(self) -> None:
        """Test creating success stats."""
        now = datetime.now(UTC)
        stats = FixSuccessStats(
            total_fixes=100,
            successful=80,
            failed=15,
            partial=5,
            success_rate=0.8,
            effective_rate=0.85,
            period_start=now - timedelta(days=30),
            period_end=now,
        )

        assert stats.total_fixes == 100
        assert stats.success_rate == 0.8
        assert stats.effective_rate == 0.85


class TestFixSuccessAlert:
    """Tests for FixSuccessAlert dataclass."""

    def test_create_alert(self) -> None:
        """Test creating an alert."""
        alert = FixSuccessAlert(
            tenant_id=uuid4(),
            category="sql_dml",
            category_type="fix_type",
            success_rate=0.3,
            threshold=0.5,
            sample_count=25,
            message="Low success rate detected",
        )

        assert alert.category == "sql_dml"
        assert alert.success_rate == 0.3
        assert alert.threshold == 0.5
        assert alert.id is not None


class TestFeedbackExportRecord:
    """Tests for FeedbackExportRecord dataclass."""

    def test_create_export_record(self) -> None:
        """Test creating an export record."""
        record = FeedbackExportRecord(
            fix_execution_id=uuid4(),
            investigation_id=uuid4(),
            fix_type="sql_dml",
            fix_code="UPDATE orders SET x = 1",
            rating="yes",
            comment="Works",
            root_cause_category="nulls",
            context={"issue_id": "123"},
        )

        assert record.fix_type == "sql_dml"
        assert record.rating == "yes"
        assert record.context == {"issue_id": "123"}


class TestFixFeedbackRating:
    """Tests for FixFeedbackRating enum."""

    def test_rating_values(self) -> None:
        """Test rating enum values."""
        assert FixFeedbackRating.YES.value == "yes"
        assert FixFeedbackRating.NO.value == "no"
        assert FixFeedbackRating.PARTIALLY.value == "partially"

    def test_rating_from_string(self) -> None:
        """Test creating rating from string."""
        rating = FixFeedbackRating("yes")
        assert rating == FixFeedbackRating.YES
