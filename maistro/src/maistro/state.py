"""Workflow run state types for the event-sourced state machine.

This module defines the immutable state types used by the Engine to track
workflow execution. All state is derived from events via the Engine.apply()
reducer.

Key design decisions:
- All dataclasses are frozen (immutable)
- RunState holds full context; events store context_update deltas
- AwaitState.resume_step is computed by Engine, not provided by Steps
- BranchState.completed stores context_update deltas, not full contexts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

# Type variable for workflow context
ContextT = TypeVar("ContextT")

# Valid run statuses
RunStatus = Literal["running", "paused", "completed", "failed"]


@dataclass(frozen=True)
class BranchState:
    """Tracks pending branch execution state.

    This state is created when a step emits BRANCH signal and is cleared
    after all branches complete and merge.

    Attributes:
        merge_step: The step to execute after all branches complete and merge.
        expected: Set of branch names expected to complete.
        completed: Map of branch_name -> context_update (delta, not full context).

    """

    merge_step: str
    expected: frozenset[str]
    completed: dict[str, dict[str, Any]] = field(default_factory=dict)

    def is_complete(self) -> bool:
        """Check if all expected branches have completed."""
        return set(self.completed.keys()) == self.expected


@dataclass(frozen=True)
class AwaitState:
    """Tracks AWAIT_USER pause state.

    This state is created when a step emits AWAIT_USER signal and is cleared
    when external input is received via InputReceived event.

    Attributes:
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

    Attributes:
        run_id: Unique identifier for this workflow run.
        status: Current run status (running, paused, completed, failed).
        context: Full workflow context. Events store deltas; state stores full.
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
