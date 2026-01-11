"""CounterAnalyzeStep implementation.

This step runs when synthesis confidence is below threshold.
It provides additional analysis before completing the investigation.
For now, it's a stub that simply completes the investigation.
"""

from __future__ import annotations

from typing import Any

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import ExecutionSignal, StepType

from .protocol import Step, StepResult


class CounterAnalyzeStep(Step[None, dict[str, Any]]):
    """Analyze low-confidence synthesis and complete the investigation.

    This step is invoked when SynthesizeStep produces a low-confidence result.
    In the future, this could implement:
    - Devil's advocate analysis
    - Alternative hypothesis exploration
    - Additional evidence gathering

    For now, it simply completes with the existing synthesis.
    """

    step_type = StepType.COUNTER_ANALYZE

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if synthesis exists to analyze.

        Args:
            context: Current investigation context.

        Returns:
            True if current_synthesis exists, False otherwise.
        """
        return context.current_synthesis is not None

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[dict[str, Any]]:
        """Complete the investigation with the current synthesis.

        In the future, this could implement counter-analysis logic.
        For now, it marks the investigation as complete.

        Args:
            context: Current investigation context with synthesis.
            input_data: Not used (always None).

        Returns:
            StepResult with COMPLETE signal and the synthesis output.
        """
        return StepResult(
            context=context,
            signal=ExecutionSignal.COMPLETE,
            output=context.current_synthesis,
        )
