"""Step protocol and result types.

Steps are pure functions: (Context, Input) -> StepResult
They don't know about persistence, locking, or orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import BranchType, ExecutionSignal, StepType

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True)
class BranchSpec:
    """Specification for a child branch to create."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchRequest:
    """Request to create child branches.

    Used when a step needs to fork execution into parallel paths.
    """

    branch_type: BranchType
    branches: list[BranchSpec]
    merge_step: StepType
    child_start_step: StepType | None = None


@dataclass(frozen=True)
class StepResult(Generic[OutputT]):
    """Immutable result of executing a step.

    Contains:
    - context: Updated investigation context
    - signal: What the orchestrator should do next
    - output: Step-specific output (optional)
    - next_step: Explicit next step (when signal=CONTINUE)
    - branch_request: Branch specs (when signal=BRANCH)
    """

    context: InvestigationContext
    signal: ExecutionSignal
    output: OutputT | None = None
    next_step: StepType | None = None
    branch_request: BranchRequest | None = None


class Step(ABC, Generic[InputT, OutputT]):
    """Base class for all investigation steps.

    Steps are:
    - Stateless: All state comes from context
    - Pure: Same input -> same output (modulo LLM stochasticity)
    - Composable: Can be chained, branched, merged
    """

    step_type: StepType

    @abstractmethod
    async def execute(
        self,
        context: InvestigationContext,
        input_data: InputT | None = None,
    ) -> StepResult[OutputT]:
        """Execute the step logic.

        Args:
            context: Current investigation state
            input_data: Step-specific input (e.g., user message)

        Returns:
            StepResult with updated context and execution signal
        """
        ...

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if prerequisites are met.

        Override in subclasses to add precondition checks.
        """
        return True
