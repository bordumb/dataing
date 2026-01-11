"""GenerateQuery step implementation.

This step generates a SQL query to test a hypothesis.
It runs in child branches created by GenerateHypothesesStep.
"""

from __future__ import annotations

from typing import Any, Protocol

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import ExecutionSignal, StepType

from .protocol import Step, StepResult


class LLMProtocol(Protocol):
    """Protocol for LLM client used by GenerateQueryStep."""

    async def generate_query(
        self,
        *,
        hypothesis: dict[str, Any],
        schema_info: dict[str, Any],
        alert_summary: str,
    ) -> str:
        """Generate a SQL query to test the hypothesis.

        Args:
            hypothesis: Hypothesis to test.
            schema_info: Database schema information.
            alert_summary: Summary of the anomaly alert.

        Returns:
            SQL query string.
        """
        ...


class GenerateQueryStep(Step[dict[str, Any], str]):
    """Generate a SQL query to test a hypothesis.

    This step:
    1. Receives hypothesis from input_data (step_cursor)
    2. Calls LLM to generate a query to test the hypothesis
    3. Returns CONTINUE signal with next_step=EXECUTE_QUERY
    """

    step_type = StepType.GENERATE_QUERY

    def __init__(self, llm: LLMProtocol) -> None:
        """Initialize the step.

        Args:
            llm: LLM client for generating queries.
        """
        self.llm = llm

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if schema info is available.

        Args:
            context: Current investigation context.

        Returns:
            True if schema info is available, False otherwise.
        """
        return context.schema_info is not None

    async def execute(
        self,
        context: InvestigationContext,
        input_data: dict[str, Any] | None = None,
    ) -> StepResult[str]:
        """Generate SQL query via LLM.

        Args:
            context: Current investigation context with schema.
            input_data: Step cursor data containing the hypothesis.

        Returns:
            StepResult with CONTINUE signal and generated query.
        """
        # Validate input_data contains hypothesis
        if input_data is None or "hypothesis" not in input_data:
            return StepResult(
                context=context,
                signal=ExecutionSignal.FAIL,
                output=None,
            )

        hypothesis: dict[str, Any] = input_data["hypothesis"]

        # Generate query via LLM
        try:
            query = await self.llm.generate_query(
                hypothesis=hypothesis,
                schema_info=context.schema_info,  # type: ignore[arg-type]
                alert_summary=context.alert_summary,
            )
        except Exception:
            return StepResult(
                context=context,
                signal=ExecutionSignal.FAIL,
                output=None,
            )

        return StepResult(
            context=context,
            signal=ExecutionSignal.CONTINUE,
            output=query,
            next_step=StepType.EXECUTE_QUERY,
        )
