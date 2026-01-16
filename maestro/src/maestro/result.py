"""Step result types for workflow execution.

StepResult is the return type of all step executions, containing the
updated context, control signal, and optional output/branching data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from maestro.signals import Signal

ContextT = TypeVar("ContextT")
OutputT = TypeVar("OutputT", covariant=True)


@dataclass(frozen=True)
class BranchSpec:
    """Specification for a child branch to create.

    Attributes:
        name: Unique identifier for this branch within the parent.
        data: Arbitrary data to pass to the child workflow.

    """

    name: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchRequest:
    """Request to create child branches for parallel execution.

    Used when a step needs to fork execution into parallel paths.
    The workflow engine will create child workflows for each branch.

    Attributes:
        branches: List of branch specifications to create.
        merge_step: Name of the step that will merge branch results.
        child_start_step: Optional step name to start each child at.
            If None, children start at the workflow's default start step.
        branch_type: Optional string categorizing the type of branch.
            Domains can use this for tracking/routing (e.g., "hypothesis", "user").

    """

    branches: list[BranchSpec]
    merge_step: str
    child_start_step: str | None = None
    branch_type: str | None = None


@dataclass(frozen=True)
class StepResult(Generic[ContextT, OutputT]):
    """Immutable result of executing a step.

    StepResult is the contract between steps and the workflow engine.
    It tells the engine:
    - The updated context (which may be unchanged)
    - What to do next via the signal
    - Optional step-specific output
    - Routing hints for CONTINUE signal
    - Branching specs for BRANCH signal

    Attributes:
        context: The (possibly updated) workflow context.
        signal: Control flow signal for the workflow engine.
        output: Optional step-specific output data.
        error: Error message (when signal=FAIL).
        next_step: Explicit next step name (when signal=CONTINUE).
            If None, the workflow uses its default routing.
        branch_request: Branch specifications (required when signal=BRANCH).

    """

    context: ContextT
    signal: Signal
    output: OutputT | None = None
    error: str | None = None
    next_step: str | None = None
    branch_request: BranchRequest | None = None

    def __post_init__(self) -> None:
        """Validate result consistency."""
        if self.signal == Signal.BRANCH and self.branch_request is None:
            raise ValueError("BRANCH signal requires branch_request")
