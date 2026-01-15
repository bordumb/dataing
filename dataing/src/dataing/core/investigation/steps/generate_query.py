"""GenerateQuery step implementation.

This step generates a SQL query to test a hypothesis.
It runs in child branches created by GenerateHypothesesStep.
"""

from __future__ import annotations

from typing import Any, Protocol

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import StepType

from .protocol import Signal, Step, StepResult


class LLMProtocol(Protocol):
    """Protocol for LLM client used by GenerateQueryStep."""

    async def generate_query(
        self,
        *,
        hypothesis: dict[str, Any],
        schema_info: dict[str, Any],
        alert_summary: str,
        alert: dict[str, Any] | None,
    ) -> str:
        """Generate a SQL query to test the hypothesis.

        Args:
            hypothesis: Hypothesis to test.
            schema_info: Database schema information.
            alert_summary: Summary of the anomaly alert (for display).
            alert: Full alert data with date, column, values (for LLM prompts).

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
    ) -> StepResult[InvestigationContext, str]:
        """Generate SQL query via LLM.

        Args:
            context: Current investigation context with schema.
            input_data: Step cursor data containing the hypothesis (optional).

        Returns:
            StepResult with CONTINUE signal and generated query.
        """
        # Get hypothesis from input_data or context.current_hypothesis
        hypothesis: dict[str, Any] | None = None
        if input_data and "hypothesis" in input_data:
            hypothesis = input_data["hypothesis"]
        elif context.current_hypothesis:
            hypothesis = context.current_hypothesis

        if hypothesis is None:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error="No hypothesis available for query generation",
            )

        # Generate query via LLM
        try:
            schema_info = context.schema_info
            if schema_info is None:
                return StepResult(
                    context=context,
                    signal=Signal.FAIL,
                    error="No schema info available for query generation",
                )
            query = await self.llm.generate_query(
                hypothesis=hypothesis,
                schema_info=schema_info,
                alert_summary=context.alert_summary,
                alert=context.alert,
            )
        except Exception as e:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error=f"Query generation failed: {e}",
            )

        # Update context with the generated query and current hypothesis
        updated_context = context.model_copy(
            update={
                "current_query": query,
                "current_hypothesis": hypothesis,
            }
        )

        return StepResult(
            context=updated_context,
            signal=Signal.CONTINUE,
            output=query,
            next_step=StepType.EXECUTE_QUERY.value,
        )
