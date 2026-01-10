"""StepRegistry for mapping step types to implementations.

The registry allows the orchestrator to look up the correct step
to execute based on the snapshot's current step type.
"""

from __future__ import annotations

from typing import Any

from dataing.core.investigation.steps.protocol import Step
from dataing.core.investigation.values import StepType


class StepRegistry:
    """Registry for step implementations.

    Maps StepType enums to Step instances. The orchestrator uses this
    to look up which step to execute for a given snapshot.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._steps: dict[StepType, Step[Any, Any]] = {}

    def register(self, step: Step[Any, Any]) -> None:
        """Register a step implementation.

        Args:
            step: Step instance to register. Uses step.step_type as key.
        """
        self._steps[step.step_type] = step

    def get(self, step_type: StepType) -> Step[Any, Any] | None:
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
