"""Workflow run state types for the event-sourced state machine.

This module defines the immutable state types used by the Engine to track
workflow execution. All state is derived from events via the Engine.apply()
reducer.

Key design decisions:
- All dataclasses are frozen (immutable)
- RunState holds full context; events store context_update deltas
- AwaitState.resume_step is computed by Engine, not provided by Steps
- BranchState uses immutable containers (frozenset, tuple of tuples)
- Context is dict[str, Any] - dataclass contexts must serialize to dict
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

# Type variable for workflow context
ContextT = TypeVar("ContextT")

# Valid run statuses
RunStatus = Literal["running", "paused", "completed", "failed"]

# Immutable branch completion type: tuple of (branch_name, context_update_items)
# where context_update_items is tuple of (key, value) pairs
BranchCompletions = tuple[tuple[str, tuple[tuple[str, Any], ...]], ...]


@dataclass(frozen=True)
class BranchState:
    """Tracks pending branch execution state.

    This state is created when a step emits BRANCH signal and is cleared
    after all branches complete and merge.

    Attributes
    ----------
        merge_step: The step to execute after all branches complete and merge.
        expected: Set of branch names expected to complete.
        completed: Immutable tuple of (branch_name, context_update_items) pairs.
            Each context_update_items is a tuple of (key, value) pairs.

    """

    merge_step: str
    expected: frozenset[str]
    completed: BranchCompletions = ()

    def is_complete(self) -> bool:
        """Check if all expected branches have completed."""
        completed_names = {name for name, _ in self.completed}
        return completed_names == self.expected

    def get_completed_dict(self) -> dict[str, dict[str, Any]]:
        """Get completed branches as a dict for merge processing.

        Returns
        -------
            Dict mapping branch_name to context_update dict.

        """
        return {name: dict(items) for name, items in self.completed}

    def with_completion(self, branch_name: str, context_update: dict[str, Any]) -> BranchState:
        """Create new BranchState with an additional completion.

        Args:
        ----
            branch_name: Name of the completed branch.
            context_update: Context update from the branch.

        Returns:
        -------
            New BranchState with the completion added.

        """
        # Convert context_update dict to immutable tuple of items
        update_items = tuple(context_update.items())
        new_completed = self.completed + ((branch_name, update_items),)
        return BranchState(
            merge_step=self.merge_step,
            expected=self.expected,
            completed=new_completed,
        )


@dataclass(frozen=True)
class AwaitState:
    """Tracks AWAIT_USER pause state.

    This state is created when a step emits AWAIT_USER signal and is cleared
    when external input is received via InputReceived event.

    Attributes
    ----------
        token: Deterministic resume key provided by the Step.
        resume_step: Step to resume after input received (computed by Engine).

    """

    token: str
    resume_step: str


@dataclass(frozen=True)
class RunState(Generic[ContextT]):
    """Main workflow run state.

    This is the single source of truth for a workflow run's current state.
    All state transitions happen through the Engine.apply() reducer, which
    takes an Event and produces a new RunState.

    Note: ContextT should be dict[str, Any]. If using a dataclass context,
    the Engine will serialize it to dict for storage and events.

    Attributes
    ----------
        run_id: Unique identifier for this workflow run.
        status: Current run status (running, paused, completed, failed).
        context: Full workflow context as dict[str, Any].
        current_step: Step currently executing, or None if terminal/paused.
        pending_branches: Branch execution state if BRANCH signal active.
        pending_await: AWAIT_USER state if waiting for external input.
        seq: Monotonically increasing event counter for ordering.

    """

    run_id: str
    status: RunStatus
    context: ContextT
    current_step: str | None = None
    pending_branches: BranchState | None = None
    pending_await: AwaitState | None = None
    seq: int = 0
