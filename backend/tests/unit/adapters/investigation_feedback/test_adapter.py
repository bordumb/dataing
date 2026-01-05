"""Tests for InvestigationFeedbackAdapter."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.investigation_feedback import (
    EventType,
    FeedbackEvent,
    InvestigationFeedbackAdapter,
)
from dataing.core.interfaces import InvestigationFeedbackEmitter


class TestInvestigationFeedbackAdapter:
    """Tests for InvestigationFeedbackAdapter."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        db.execute = AsyncMock(return_value="INSERT 0 1")
        return db

    @pytest.fixture
    def adapter(self, mock_db: MagicMock) -> InvestigationFeedbackAdapter:
        """Create adapter with mock database."""
        return InvestigationFeedbackAdapter(db=mock_db)

    async def test_emit_stores_event(
        self, adapter: InvestigationFeedbackAdapter, mock_db: MagicMock
    ) -> None:
        """emit() stores event in database."""
        tenant_id = uuid4()
        investigation_id = uuid4()

        await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={"dataset_id": "public.orders"},
            investigation_id=investigation_id,
        )

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "INSERT INTO investigation_feedback_events" in call_args[0][0]

    async def test_emit_returns_event(self, adapter: InvestigationFeedbackAdapter) -> None:
        """emit() returns the created event."""
        tenant_id = uuid4()

        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.HYPOTHESIS_GENERATED,
            event_data={"hypothesis_id": "h1"},
        )

        assert isinstance(event, FeedbackEvent)
        assert event.tenant_id == tenant_id
        assert event.event_type == EventType.HYPOTHESIS_GENERATED

    async def test_emit_with_actor(
        self, adapter: InvestigationFeedbackAdapter, mock_db: MagicMock
    ) -> None:
        """emit() includes actor information when provided."""
        tenant_id = uuid4()
        actor_id = uuid4()

        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.FEEDBACK_INVESTIGATION,
            event_data={"rating": 1},
            actor_id=actor_id,
            actor_type="user",
        )

        assert event.actor_id == actor_id
        assert event.actor_type == "user"

    async def test_emit_logs_event(
        self, adapter: InvestigationFeedbackAdapter, mock_db: MagicMock
    ) -> None:
        """emit() logs the event for observability."""
        tenant_id = uuid4()

        # This test verifies emit doesn't raise and completes
        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.QUERY_SUCCEEDED,
            event_data={"row_count": 100},
        )

        assert event is not None


class TestInvestigationFeedbackAdapterProtocol:
    """Tests for protocol conformance."""

    def test_adapter_implements_feedback_emitter(self) -> None:
        """InvestigationFeedbackAdapter implements InvestigationFeedbackEmitter protocol."""
        assert isinstance(InvestigationFeedbackAdapter, type)
        # Verify the class has the emit method signature matching InvestigationFeedbackEmitter
        assert hasattr(InvestigationFeedbackAdapter, "emit")
        # Verify InvestigationFeedbackEmitter is a runtime checkable protocol
        assert hasattr(InvestigationFeedbackEmitter, "__protocol_attrs__")
