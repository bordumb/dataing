"""Tests for feedback event types."""

from uuid import uuid4

import pytest
from dataing.adapters.feedback.types import EventType, FeedbackEvent


class TestFeedbackEvent:
    """Tests for FeedbackEvent dataclass."""

    def test_create_event_with_required_fields(self) -> None:
        """Event can be created with required fields only."""
        event = FeedbackEvent(
            tenant_id=uuid4(),
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={"dataset_id": "public.orders"},
        )

        assert event.id is not None
        assert event.actor_type == "system"
        assert event.created_at is not None

    def test_create_event_with_all_fields(self) -> None:
        """Event can be created with all fields."""
        tenant_id = uuid4()
        investigation_id = uuid4()
        dataset_id = uuid4()
        actor_id = uuid4()

        event = FeedbackEvent(
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            dataset_id=dataset_id,
            event_type=EventType.HYPOTHESIS_GENERATED,
            event_data={"hypothesis_id": "h1", "title": "NULL spike"},
            actor_id=actor_id,
            actor_type="user",
        )

        assert event.tenant_id == tenant_id
        assert event.investigation_id == investigation_id
        assert event.dataset_id == dataset_id
        assert event.actor_id == actor_id
        assert event.actor_type == "user"

    def test_event_is_immutable(self) -> None:
        """Event should be immutable (frozen dataclass)."""
        event = FeedbackEvent(
            tenant_id=uuid4(),
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={},
        )

        with pytest.raises(AttributeError):
            event.event_type = EventType.INVESTIGATION_COMPLETED  # type: ignore[misc]


class TestEventType:
    """Tests for EventType enum."""

    def test_investigation_events_exist(self) -> None:
        """Investigation lifecycle events are defined."""
        assert EventType.INVESTIGATION_STARTED.value == "investigation.started"
        assert EventType.INVESTIGATION_COMPLETED.value == "investigation.completed"

    def test_hypothesis_events_exist(self) -> None:
        """Hypothesis events are defined."""
        assert EventType.HYPOTHESIS_GENERATED.value == "hypothesis.generated"
        assert EventType.HYPOTHESIS_ACCEPTED.value == "hypothesis.accepted"
        assert EventType.HYPOTHESIS_REJECTED.value == "hypothesis.rejected"

    def test_query_events_exist(self) -> None:
        """Query events are defined."""
        assert EventType.QUERY_SUBMITTED.value == "query.submitted"
        assert EventType.QUERY_SUCCEEDED.value == "query.succeeded"
        assert EventType.QUERY_FAILED.value == "query.failed"

    def test_feedback_events_exist(self) -> None:
        """User feedback events are defined."""
        assert EventType.FEEDBACK_HYPOTHESIS.value == "feedback.hypothesis"
        assert EventType.FEEDBACK_QUERY.value == "feedback.query"
        assert EventType.FEEDBACK_SYNTHESIS.value == "feedback.synthesis"
        assert EventType.FEEDBACK_INVESTIGATION.value == "feedback.investigation"
