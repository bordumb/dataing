"""Event-sourced investigation state.

This module implements the Event Sourcing pattern for tracking
investigation state. All derived values (retry counts, query counts, etc.)
are computed from the event history, never stored as mutable counters.

This approach ensures:
- Complete audit trail of all investigation actions
- Impossible to have inconsistent state
- Easy to replay and debug investigations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import SchemaResponse

    from .domain_types import AnomalyAlert, LineageContext


EventType = Literal[
    "investigation_started",
    "context_gathered",
    "schema_discovery_failed",
    "hypothesis_generated",
    "query_submitted",
    "query_succeeded",
    "query_failed",
    "reflexion_attempted",
    "hypothesis_confirmed",
    "hypothesis_rejected",
    "synthesis_completed",
    "investigation_failed",
]


@dataclass(frozen=True)
class Event:
    """Immutable event in the investigation timeline.

    Events are the source of truth for investigation state.
    They are append-only and never modified after creation.

    Attributes:
        type: The type of event that occurred.
        timestamp: When the event occurred (UTC).
        data: Additional event-specific data.
    """

    type: EventType
    timestamp: datetime
    data: dict[str, str | int | float | bool | list[str] | None]


@dataclass
class InvestigationState:
    """Event-sourced investigation state.

    All derived values (retry_count, query_count, etc.) are computed
    from the event history, never stored as mutable counters.

    This ensures that the state is always consistent and can be
    reconstructed from the event history at any time.

    Attributes:
        id: Unique investigation identifier.
        alert: The anomaly alert that triggered this investigation.
        events: Ordered list of all events in this investigation.
        schema_context: Cached schema context (set once after gathering).
        lineage_context: Cached lineage context (optional).
    """

    id: str
    alert: AnomalyAlert
    events: list[Event] = field(default_factory=list)
    schema_context: SchemaResponse | None = None
    lineage_context: LineageContext | None = None

    @property
    def status(self) -> str:
        """Derive status from events.

        Returns:
            Current investigation status based on event history.
        """
        if not self.events:
            return "pending"
        last_event = self.events[-1]
        if last_event.type == "synthesis_completed":
            return "completed"
        if last_event.type in ("investigation_failed", "schema_discovery_failed"):
            return "failed"
        return "in_progress"

    def get_retry_count(self, hypothesis_id: str) -> int:
        """Derive retry count from event history - NOT a mutable counter.

        Args:
            hypothesis_id: ID of the hypothesis to count retries for.

        Returns:
            Number of reflexion attempts for this hypothesis.
        """
        return sum(
            1
            for e in self.events
            if e.type == "reflexion_attempted" and e.data.get("hypothesis_id") == hypothesis_id
        )

    def get_query_count(self) -> int:
        """Total queries executed across all hypotheses.

        Returns:
            Total number of queries submitted.
        """
        return sum(1 for e in self.events if e.type == "query_submitted")

    def get_hypothesis_query_count(self, hypothesis_id: str) -> int:
        """Count queries executed for a specific hypothesis.

        Args:
            hypothesis_id: ID of the hypothesis.

        Returns:
            Number of queries submitted for this hypothesis.
        """
        return sum(
            1
            for e in self.events
            if e.type == "query_submitted" and e.data.get("hypothesis_id") == hypothesis_id
        )

    def get_failed_queries(self, hypothesis_id: str) -> list[str]:
        """Get all failed query texts for duplicate detection.

        Args:
            hypothesis_id: ID of the hypothesis.

        Returns:
            List of failed query SQL strings.
        """
        return [
            str(e.data.get("query", ""))
            for e in self.events
            if e.type == "query_failed" and e.data.get("hypothesis_id") == hypothesis_id
        ]

    def get_all_queries(self, hypothesis_id: str) -> list[str]:
        """Get all query texts submitted for a hypothesis.

        Args:
            hypothesis_id: ID of the hypothesis.

        Returns:
            List of all query SQL strings submitted.
        """
        return [
            str(e.data.get("query", ""))
            for e in self.events
            if e.type == "query_submitted" and e.data.get("hypothesis_id") == hypothesis_id
        ]

    def get_consecutive_failures(self) -> int:
        """Count consecutive query failures from the end of events.

        Returns:
            Number of consecutive failures.
        """
        consecutive = 0
        for event in reversed(self.events):
            if event.type == "query_failed":
                consecutive += 1
            elif event.type == "query_succeeded":
                break
        return consecutive

    def append_event(self, event: Event) -> InvestigationState:
        """Return new state with event appended (immutable update).

        This method returns a new InvestigationState with the event
        appended, preserving immutability of the event list.

        Args:
            event: The event to append.

        Returns:
            New InvestigationState with the event appended.
        """
        return InvestigationState(
            id=self.id,
            alert=self.alert,
            events=[*self.events, event],
            schema_context=self.schema_context,
            lineage_context=self.lineage_context,
        )

    def with_context(
        self,
        schema_context: SchemaResponse | None = None,
        lineage_context: LineageContext | None = None,
    ) -> InvestigationState:
        """Return new state with updated context.

        Args:
            schema_context: New schema context.
            lineage_context: New lineage context.

        Returns:
            New InvestigationState with updated context.
        """
        return InvestigationState(
            id=self.id,
            alert=self.alert,
            events=self.events.copy(),
            schema_context=schema_context or self.schema_context,
            lineage_context=lineage_context or self.lineage_context,
        )
