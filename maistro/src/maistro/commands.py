"""Command types for the event-sourced workflow engine.

Commands are instructions from the Engine to the Runner. They represent
the "output" side of the pure reducer: (state, event) -> (state, command).

Commands tell the Runner what effectful operation to perform next:
- ExecuteStep: Run a workflow step
- StartBranches: Begin parallel branch execution
- WaitForInput: Pause and wait for external input
- Stop: Terminate the workflow
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from maistro.result import BranchRequest


@dataclass(frozen=True)
class Command:
    """Base class for all command types.

    Commands are instructions from Engine to Runner. They are immutable
    and represent what action the Runner should take next.

    """


@dataclass(frozen=True)
class NoOp(Command):
    """Command indicating no action needed from Runner.

    Used when:
    - BranchStarted: informational event, branches execute independently
    - Waiting for more branches to complete (not external input)
    - Other informational events that don't require Runner action

    """


@dataclass(frozen=True)
class ExecuteStep(Command):
    """Command to execute a workflow step.

    Attributes:
        step_name: Name of the step to execute.
        input_data: Optional input data to pass to the step.

    """

    step_name: str
    input_data: Any | None = None


@dataclass(frozen=True)
class StartBranches(Command):
    """Command to start parallel branch execution.

    Attributes:
        branch_request: The branch specifications from the step result.

    """

    branch_request: BranchRequest


@dataclass(frozen=True)
class WaitForInput(Command):
    """Command to pause and wait for external input.

    Attributes:
        token: Deterministic identifier for this pause point.

    """

    token: str


@dataclass(frozen=True)
class Stop(Command):
    """Command to terminate the workflow.

    Attributes:
        status: Terminal status - either "completed" or "failed".
        final_context: The final workflow context.
        error: Error message if status is "failed".

    """

    status: Literal["completed", "failed"]
    final_context: Any | None = None
    error: str | None = None
