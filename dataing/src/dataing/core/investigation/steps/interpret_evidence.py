"""InterpretEvidence step implementation.

This step interprets query results as evidence for/against a hypothesis.
It runs after ExecuteQueryStep and completes the hypothesis branch.
"""

from __future__ import annotations

from typing import Any, Protocol

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import StepType

from .protocol import Signal, Step, StepResult


class LLMProtocol(Protocol):
    """Protocol for LLM client used by InterpretEvidenceStep."""

    async def interpret_evidence(
        self,
        *,
        hypothesis: dict[str, Any],
        query_result: dict[str, Any],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Interpret query results as evidence for/against hypothesis.

        Args:
            hypothesis: The hypothesis being tested.
            query_result: Results from executing the test query.
            alert_summary: Summary of the anomaly alert.

        Returns:
            Evidence dict with fields:
            - hypothesis_id: str
            - supports_hypothesis: bool
            - confidence: float (0.0 to 1.0)
            - interpretation: str
            - query: str
            - result_summary: str
            - row_count: int
        """
        ...


class InterpretEvidenceStep(Step[dict[str, Any], dict[str, Any]]):
    """Interpret query results as evidence for/against a hypothesis.

    This step:
    1. Reads current_query_result from context (set by ExecuteQueryStep)
    2. Receives hypothesis from input_data (step_cursor)
    3. Calls LLM to interpret the evidence
    4. Returns COMPLETE signal (hypothesis branch ends here)
    5. Adds evidence to context.evidence list
    """

    step_type = StepType.INTERPRET_EVIDENCE

    def __init__(self, llm: LLMProtocol) -> None:
        """Initialize the step.

        Args:
            llm: LLM client for interpreting evidence.
        """
        self.llm = llm

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if current_query_result is available in context.

        Args:
            context: Current investigation context.

        Returns:
            True if current_query_result is available, False otherwise.
        """
        return context.current_query_result is not None

    async def execute(
        self,
        context: InvestigationContext,
        input_data: dict[str, Any] | None = None,
    ) -> StepResult[InvestigationContext, dict[str, Any]]:
        """Interpret query results via LLM.

        Args:
            context: Current investigation context with current_query_result.
            input_data: Step cursor data containing the hypothesis.

        Returns:
            StepResult with COMPLETE signal and evidence dict.
        """
        # Get hypothesis from input_data or context
        hypothesis: dict[str, Any] | None = None
        if input_data and "hypothesis" in input_data:
            hypothesis = input_data["hypothesis"]
        elif context.current_hypothesis is not None:
            hypothesis = context.current_hypothesis

        if hypothesis is None:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error="No hypothesis available for interpretation",
            )

        # Validate context has current_query_result
        if context.current_query_result is None:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error="No query result available to interpret",
            )

        # Interpret evidence via LLM
        try:
            evidence: dict[str, Any] = await self.llm.interpret_evidence(
                hypothesis=hypothesis,
                query_result=context.current_query_result,
                alert_summary=context.alert_summary,
            )
        except Exception as e:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error=f"Evidence interpretation failed: {e}",
            )

        # Update context by appending evidence to the list
        updated_evidence = list(context.evidence) + [evidence]
        updated_context = context.model_copy(update={"evidence": updated_evidence})

        return StepResult(
            context=updated_context,
            signal=Signal.COMPLETE,
            output=evidence,
        )
