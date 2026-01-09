"""Types for the feedback event system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EventType(Enum):
    """Types of events that can be logged."""

    # Investigation lifecycle
    INVESTIGATION_STARTED = "investigation.started"
    INVESTIGATION_COMPLETED = "investigation.completed"
    INVESTIGATION_FAILED = "investigation.failed"

    # Hypothesis events
    HYPOTHESIS_GENERATED = "hypothesis.generated"
    HYPOTHESIS_ACCEPTED = "hypothesis.accepted"
    HYPOTHESIS_REJECTED = "hypothesis.rejected"

    # Query events
    QUERY_SUBMITTED = "query.submitted"
    QUERY_SUCCEEDED = "query.succeeded"
    QUERY_FAILED = "query.failed"

    # Evidence events
    EVIDENCE_COLLECTED = "evidence.collected"
    EVIDENCE_EVALUATED = "evidence.evaluated"

    # Synthesis events
    SYNTHESIS_GENERATED = "synthesis.generated"

    # User feedback events
    FEEDBACK_HYPOTHESIS = "feedback.hypothesis"
    FEEDBACK_QUERY = "feedback.query"
    FEEDBACK_EVIDENCE = "feedback.evidence"
    FEEDBACK_SYNTHESIS = "feedback.synthesis"
    FEEDBACK_INVESTIGATION = "feedback.investigation"

    # Comments
    COMMENT_ADDED = "comment.added"


@dataclass(frozen=True)
class FeedbackEvent:
    """Immutable event for the feedback log.

    Attributes:
        id: Unique event identifier.
        tenant_id: Tenant this event belongs to.
        investigation_id: Optional investigation this event relates to.
        dataset_id: Optional dataset this event relates to.
        event_type: Type of event.
        event_data: Event-specific data payload.
        actor_id: Optional user or system that caused the event.
        actor_type: Type of actor (user or system).
        created_at: When the event occurred.
    """

    tenant_id: UUID
    event_type: EventType
    event_data: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    investigation_id: UUID | None = None
    dataset_id: UUID | None = None
    actor_id: UUID | None = None
    actor_type: str = "system"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
