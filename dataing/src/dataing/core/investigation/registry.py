"""StepRegistry for mapping step types to implementations.

The registry allows the orchestrator to look up the correct step
to execute based on the snapshot's current step type.
"""

from __future__ import annotations

from typing import Any

from maestro import Step

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import StepType

# Type alias for investigation steps
InvestigationStep = Step[InvestigationContext, Any, Any]


class StepRegistry:
    """Registry for step implementations.

    Maps StepType enums to Step instances. The orchestrator uses this
    to look up which step to execute for a given snapshot.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._steps: dict[StepType, InvestigationStep] = {}

    def register(self, step: InvestigationStep) -> None:
        """Register a step implementation.

        Args:
            step: Step instance to register. Uses step.name as key.
        """
        step_type = StepType(step.name)
        self._steps[step_type] = step

    def get(self, step_type: StepType) -> InvestigationStep | None:
        """Get step implementation for a step type.

        Args:
            step_type: The step type to look up.

        Returns:
            The registered step, or None if not registered.
        """
        return self._steps.get(step_type)

    def has(self, step_type: StepType) -> bool:
        """Check if a step type is registered.

        Args:
            step_type: The step type to check.

        Returns:
            True if the step type has a registered implementation.
        """
        return step_type in self._steps

    def registered_types(self) -> list[StepType]:
        """List all registered step types.

        Returns:
            List of registered step types.
        """
        return list(self._steps.keys())
