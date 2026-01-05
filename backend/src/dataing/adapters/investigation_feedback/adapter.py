"""Feedback adapter for emitting and storing events."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from .types import EventType, FeedbackEvent

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


class InvestigationFeedbackAdapter:
    """Adapter for emitting investigation feedback events to the event log.

    This adapter provides a clean interface for recording investigation
    traces, user feedback, and other events for later analysis.
    """

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the feedback adapter.

        Args:
            db: Application database for storing events.
        """
        self.db = db

    async def emit(
        self,
        tenant_id: UUID,
        event_type: EventType,
        event_data: dict[str, Any],
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str = "system",
    ) -> FeedbackEvent:
        """Emit an event to the feedback log.

        Args:
            tenant_id: Tenant this event belongs to.
            event_type: Type of event being emitted.
            event_data: Event-specific data payload.
            investigation_id: Optional investigation this relates to.
            dataset_id: Optional dataset this relates to.
            actor_id: Optional user or system that caused the event.
            actor_type: Type of actor (user or system).

        Returns:
            The created FeedbackEvent.
        """
        event = FeedbackEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            event_data=event_data,
            investigation_id=investigation_id,
            dataset_id=dataset_id,
            actor_id=actor_id,
            actor_type=actor_type,
        )

        await self._store_event(event)

        logger.debug(
            f"feedback_event_emitted event_id={event.id} "
            f"event_type={event_type.value} "
            f"investigation_id={investigation_id if investigation_id else 'None'}"
        )

        return event

    async def _store_event(self, event: FeedbackEvent) -> None:
        """Store event in the database.

        Args:
            event: The event to store.
        """
        query = """
            INSERT INTO investigation_feedback_events (
                id, tenant_id, investigation_id, dataset_id,
                event_type, event_data, actor_id, actor_type, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """

        await self.db.execute(
            query,
            event.id,
            event.tenant_id,
            event.investigation_id,
            event.dataset_id,
            event.event_type.value,
            json.dumps(event.event_data),
            event.actor_id,
            event.actor_type,
            event.created_at,
        )
