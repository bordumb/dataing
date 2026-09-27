"""Integration tests for feedback system with real database."""

from uuid import UUID

import pytest

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.investigation_feedback.adapter import (
    InvestigationFeedbackAdapter,
)
from dataing.adapters.investigation_feedback.types import EventType


@pytest.mark.integration
class TestInvestigationFeedbackIntegration:
    """Integration tests for investigation feedback with real database."""

    @pytest.fixture
    def adapter(self, migrated_db: AppDatabase) -> InvestigationFeedbackAdapter:
        """Create feedback adapter."""
        return InvestigationFeedbackAdapter(db=migrated_db)

    async def test_emit_and_retrieve_event(
        self, adapter: InvestigationFeedbackAdapter, migrated_db: AppDatabase, tenant_id: UUID
    ) -> None:
        """Events can be emitted and retrieved."""
        # Emit an event
        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={"dataset_id": "test.table"},
        )

        # Retrieve events
        events = await migrated_db.list_feedback_events(tenant_id=tenant_id)

        # Find our event
        our_event = next((e for e in events if e["id"] == event.id), None)
        assert our_event is not None
        assert our_event["event_type"] == "investigation.started"
