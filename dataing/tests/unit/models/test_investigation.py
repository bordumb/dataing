"""Unit tests for investigation model."""

from __future__ import annotations

from dataing.models.investigation import Investigation, InvestigationStatus


class TestInvestigationStatus:
    """Tests for InvestigationStatus enum."""

    def test_pending_status(self) -> None:
        """Test pending status."""
        assert InvestigationStatus.PENDING.value == "pending"

    def test_in_progress_status(self) -> None:
        """Test in_progress status."""
        assert InvestigationStatus.IN_PROGRESS.value == "in_progress"

    def test_waiting_approval_status(self) -> None:
        """Test waiting_approval status."""
        assert InvestigationStatus.WAITING_APPROVAL.value == "waiting_approval"

    def test_completed_status(self) -> None:
        """Test completed status."""
        assert InvestigationStatus.COMPLETED.value == "completed"

    def test_failed_status(self) -> None:
        """Test failed status."""
        assert InvestigationStatus.FAILED.value == "failed"

    def test_status_is_string_enum(self) -> None:
        """Test that status is a string enum."""
        assert isinstance(InvestigationStatus.PENDING.value, str)


class TestInvestigation:
    """Tests for Investigation model."""

    def test_investigation_tablename(self) -> None:
        """Test investigation table name."""
        assert Investigation.__tablename__ == "investigations"

    def test_investigation_has_required_columns(self) -> None:
        """Test investigation has required columns."""
        # Check column existence
        columns = [c.name for c in Investigation.__table__.columns]

        assert "id" in columns
        assert "tenant_id" in columns
        assert "dataset_id" in columns
        assert "metric_name" in columns
        assert "status" in columns
        assert "events" in columns
        assert "finding" in columns

    def test_investigation_has_timestamps(self) -> None:
        """Test investigation has timestamp columns."""
        columns = [c.name for c in Investigation.__table__.columns]

        assert "created_at" in columns
        assert "started_at" in columns
        assert "completed_at" in columns

    def test_investigation_has_relationships(self) -> None:
        """Test investigation has relationships."""
        relationships = list(Investigation.__mapper__.relationships)

        assert len(relationships) >= 1
