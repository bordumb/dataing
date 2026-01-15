"""Integration tests for feedback system with real database."""

import os
from collections.abc import AsyncGenerator
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
    async def db(self) -> AsyncGenerator[AppDatabase, None]:
        """Create database connection."""
        dsn = os.getenv("DATABASE_URL", "postgresql://dataing:dataing@localhost:5432/dataing_demo")
        db = AppDatabase(dsn=dsn)
        try:
            await db.connect()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")
        yield db
        await db.close()

    @pytest.fixture
    def adapter(self, db: AppDatabase) -> InvestigationFeedbackAdapter:
        """Create feedback adapter."""
        return InvestigationFeedbackAdapter(db=db)

    async def test_emit_and_retrieve_event(self, adapter: InvestigationFeedbackAdapter, db: AppDatabase) -> None:
        """Events can be emitted and retrieved."""
        # Get a valid tenant_id from the database
        tenant = await db.fetch_one("SELECT id FROM tenants LIMIT 1")
        if not tenant:
            pytest.skip("No tenant in database")

        tenant_id = tenant["id"]

        # Emit an event
        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={"dataset_id": "test.table"},
        )

        # Retrieve events
        events = await db.list_feedback_events(tenant_id=tenant_id)

        # Find our event
        our_event = next((e for e in events if e["id"] == event.id), None)
        assert our_event is not None
        assert our_event["event_type"] == "investigation.started"
