"""Replayer for deterministic state reconstruction from events.

The Replayer applies a sequence of events to an initial state using the Engine,
producing the final state. This enables:
- Debugging: Reproduce exact state at any point in a workflow
- Recovery: Rebuild state after crash by replaying persisted events
- Testing: Verify Engine determinism by comparing live vs replay
"""

from __future__ import annotations

from typing import Generic, TypeVar

from maestro.commands import Command
from maestro.engine import Engine
from maestro.events import Event
from maestro.state import RunState

ContextT = TypeVar("ContextT")


class Replayer(Generic[ContextT]):
    """Deterministic replayer for reconstructing workflow state from events.

    The Replayer uses the pure Engine to replay events and reconstruct state.
    Given the same initial state and events, replay always produces the same
    final state - this is the core invariant of the event-sourced architecture.

    Attributes:
        _engine: The pure Engine for state transitions.

    """

    def __init__(self, engine: Engine[ContextT]) -> None:
        """Initialize the Replayer.

        Args:
            engine: The pure Engine for state transitions.

        """
        self._engine = engine

    def replay(
        self, initial_state: RunState[ContextT], events: list[Event]
    ) -> RunState[ContextT]:
        """Replay events to reconstruct final state.

        Applies each event in sequence to the initial state using the Engine.
        This is synchronous because the Engine is pure and performs no I/O.

        Args:
            initial_state: The starting state before any events.
            events: Ordered list of events to apply.

        Returns:
            The final state after applying all events.

        """
        state = initial_state
        for event in events:
            state, _ = self._engine.apply(state, event)
        return state

    def replay_with_commands(
        self, initial_state: RunState[ContextT], events: list[Event]
    ) -> tuple[RunState[ContextT], list[Command]]:
        """Replay events and capture all commands produced.

        Useful for debugging and verifying that replay produces the same
        commands as the original run.

        Args:
            initial_state: The starting state before any events.
            events: Ordered list of events to apply.

        Returns:
            Tuple of (final_state, list_of_commands_produced).

        """
        state = initial_state
        commands: list[Command] = []
        for event in events:
            state, command = self._engine.apply(state, event)
            commands.append(command)
        return state, commands

    def replay_to_event(
        self, initial_state: RunState[ContextT], events: list[Event], target_seq: int
    ) -> RunState[ContextT]:
        """Replay events up to a specific sequence number.

        Useful for debugging by stepping through events one at a time.

        Args:
            initial_state: The starting state before any events.
            events: Ordered list of events to apply.
            target_seq: Sequence number to stop at (inclusive).

        Returns:
            The state after applying events up to target_seq.

        """
        state = initial_state
        for event in events:
            if event.seq > target_seq:
                break
            state, _ = self._engine.apply(state, event)
        return state
