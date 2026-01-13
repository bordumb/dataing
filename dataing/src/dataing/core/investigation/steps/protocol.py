"""Step protocol and result types.

This module re-exports types from maestro for backward compatibility.
New code should import directly from maestro.

Steps are pure functions: (Context, Input) -> StepResult
They don't know about persistence, locking, or orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from maestro import BranchRequest, BranchSpec, Signal, StepResult

from dataing.core.investigation.entities import InvestigationContext

# Re-export maestro types for backward compatibility
__all__ = [
    "BranchRequest",
    "BranchSpec",
    "DataingStep",
    "Signal",
    "StepResult",
]

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class DataingStep(ABC, Generic[InputT, OutputT]):
    """Base class for all investigation steps.

    Steps are:
    - Stateless: All state comes from context
    - Pure: Same input -> same output (modulo LLM stochasticity)
    - Composable: Can be chained, branched, merged

    This class satisfies the maestro.Step protocol by providing
    a name property derived from step_type.
    """

    step_type: str  # Can be StepType enum value or string

    @property
    def name(self) -> str:
        """Return step name for maestro protocol compatibility."""
        # Handle both StepType enum and string values
        step_type = self.step_type
        if hasattr(step_type, "value"):
            val: str = step_type.value
            return val
        return step_type

    @abstractmethod
    async def execute(
        self,
        context: InvestigationContext,
        input_data: InputT | None = None,
    ) -> StepResult[InvestigationContext, OutputT]:
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


# Backward compatibility alias
Step = DataingStep
