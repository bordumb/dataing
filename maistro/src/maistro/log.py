"""Event log interface and in-memory implementation.

The EventLog protocol defines the interface for storing and retrieving events.
InMemoryEventLog provides a simple in-memory implementation suitable for
testing and single-process workflows.

Future implementations may persist events to PostgreSQL, files, or other stores.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from maistro.events import Event


class EventLog(Protocol):
    """Protocol for event log implementations.

    An EventLog stores events and assigns sequence numbers. Events are
    append-only; once added, they cannot be modified or removed.

    """

    def append(self, event: Event) -> Event:
        """Append an event to the log, assigning its sequence number.

        Args:
            event: The event to append. The seq field will be overwritten.

        Returns:
            A new event instance with the assigned seq value.

        """
        ...

    def events(self) -> list[Event]:
        """Return all events in the log.

        Returns:
            A copy of all events, ordered by sequence number.

        """
        ...

    def __len__(self) -> int:
        """Return the number of events in the log.

        Returns:
            The event count.

        """
        ...


class InMemoryEventLog:
    """In-memory event log implementation.

    Stores events in a list in memory. Suitable for testing and single-process
    workflows where durability is not required.

    Attributes:
        _events: Internal list of stored events.
        _next_seq: Next sequence number to assign (starts at 1).

    """

    def __init__(self) -> None:
        """Initialize an empty event log."""
        self._events: list[Event] = []
        self._next_seq: int = 1

    def append(self, event: Event) -> Event:
        """Append an event to the log, assigning its sequence number.

        Creates a new event instance with the assigned seq value since events
        are immutable (frozen dataclasses).

        Args:
            event: The event to append. The seq field will be overwritten.

        Returns:
            A new event instance with the assigned seq value.

        """
        stamped = replace(event, seq=self._next_seq)
        self._events.append(stamped)
        self._next_seq += 1
        return stamped

    def events(self) -> list[Event]:
        """Return all events in the log.

        Returns:
            A copy of all events, ordered by sequence number.

        """
        return list(self._events)

    def __len__(self) -> int:
        """Return the number of events in the log.

        Returns:
            The event count.

        """
        return len(self._events)
