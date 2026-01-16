"""Event types for the event-sourced workflow engine.

Events represent facts about what happened during workflow execution. They are
the "input" side of the pure reducer: (state, event) -> (state, command).

All events are immutable (frozen dataclasses). The `seq` field is assigned by
the EventLog when the event is appended, not by the event creator.

Events store `context_update` deltas, not full contexts, keeping logs lightweight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maestro.signals import Signal


@dataclass(frozen=True)
class Event:
    """Base class for all event types.

    The seq field is a monotonically increasing sequence number assigned by
    the EventLog when the event is appended. Event creators should not set it.

    Attributes:
        seq: Sequence number assigned by EventLog.append().

    """

    seq: int = 0


@dataclass(frozen=True)
class RunStarted(Event):
    """Workflow execution begins.

    Attributes:
        run_id: Unique identifier for this workflow run.
        start_step: Name of the step to begin execution.

    """

    run_id: str = ""
    start_step: str = ""


@dataclass(frozen=True)
class StepStarted(Event):
    """Step execution begins.

    Used for UI updates and stuck detection.

    Attributes:
        step_name: Name of the step being executed.

    """

    step_name: str = ""


@dataclass(frozen=True)
class StepCompleted(Event):
    """Step finished successfully.

    Attributes:
        step_name: Name of the step that completed.
        context_update: Delta to apply to context (not full context).
        signal: The control signal returned by the step.
        next_step: Explicit next step name for routing (if provided).

    """

    step_name: str = ""
    context_update: dict[str, Any] = field(default_factory=dict)
    signal: Signal = Signal.CONTINUE
    next_step: str | None = None


@dataclass(frozen=True)
class StepFailed(Event):
    """Step raised an exception.

    Attributes:
        step_name: Name of the step that failed.
        error: Error message describing the failure.

    """

    step_name: str = ""
    error: str = ""


@dataclass(frozen=True)
class BranchStarted(Event):
    """Branch execution begins.

    Attributes:
        branch_name: Name of the branch being started.
        start_step: Name of the step to begin branch execution.

    """

    branch_name: str = ""
    start_step: str = ""


@dataclass(frozen=True)
class BranchCompleted(Event):
    """Branch finished.

    BranchCompleted events are emitted in canonical alphabetical order
    by branch_name to ensure deterministic replay.

    Attributes:
        branch_name: Name of the branch that completed.
        context_update: Delta to apply to context (not full context).

    """

    branch_name: str = ""
    context_update: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InputRequested(Event):
    """AWAIT_USER signal triggered.

    Attributes:
        token: Deterministic identifier for this pause point.

    """

    token: str = ""


@dataclass(frozen=True)
class InputReceived(Event):
    """External input provided.

    Attributes:
        token: The token that was awaited.
        payload: The input data provided.

    """

    token: str = ""
    payload: Any = None


@dataclass(frozen=True)
class RunPaused(Event):
    """Run paused.

    Attributes:
        reason: Description of why the run was paused.

    """

    reason: str = ""


@dataclass(frozen=True)
class RunResumed(Event):
    """Run resumed.

    Attributes:
        reason: Description of why the run was resumed.

    """

    reason: str = ""


@dataclass(frozen=True)
class RunCompleted(Event):
    """Workflow finished successfully.

    Attributes:
        final_context: The final workflow context as a dictionary.

    """

    final_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunFailed(Event):
    """Workflow finished with failure.

    Attributes:
        error: Error message describing the failure.

    """

    error: str = ""
