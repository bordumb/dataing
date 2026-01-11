"""SynthesizeStep implementation.

This step synthesizes all evidence from hypothesis investigations
into a root cause finding. It is the merge step that runs after
all hypothesis branches complete.
"""

from __future__ import annotations

from typing import Any, Protocol

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import ExecutionSignal, StepType

from .protocol import Step, StepResult


class LLMProtocol(Protocol):
    """Protocol for LLM client used by SynthesizeStep."""

    async def synthesize_findings(
        self,
        *,
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Synthesize evidence into root cause finding.

        Args:
            evidence: List of evidence dicts from hypothesis investigations.
            hypotheses: List of hypothesis dicts that were investigated.
            alert_summary: Summary of the anomaly alert.

        Returns:
            Synthesis dict with fields:
            - root_cause: str - The identified root cause
            - confidence: float (0.0 to 1.0) - Confidence in the finding
            - recommendations: list[str] - Suggested actions
            - supporting_evidence: list[str] - Evidence supporting the conclusion
        """
        ...


class SynthesizeStep(Step[None, dict[str, Any]]):
    """Synthesize evidence from hypothesis investigations into root cause finding.

    This step:
    1. Collects all evidence from context.evidence list
    2. Calls LLM to synthesize findings into root cause analysis
    3. Returns COMPLETE if confidence >= threshold
    4. Returns CONTINUE with next_step=COUNTER_ANALYZE if confidence < threshold
    5. Sets current_synthesis in context
    """

    step_type = StepType.SYNTHESIZE

    def __init__(
        self,
        llm: LLMProtocol,
        confidence_threshold: float = 0.85,
    ) -> None:
        """Initialize the step.

        Args:
            llm: LLM client for synthesizing findings.
            confidence_threshold: Minimum confidence to return COMPLETE signal.
        """
        self.llm = llm
        self.confidence_threshold = confidence_threshold

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if there is evidence to synthesize.

        Args:
            context: Current investigation context.

        Returns:
            True if evidence list is non-empty, False otherwise.
        """
        return len(context.evidence) > 0

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[dict[str, Any]]:
        """Synthesize evidence into root cause finding via LLM.

        Args:
            context: Current investigation context with evidence.
            input_data: Not used (always None).

        Returns:
            StepResult with:
            - COMPLETE signal if confidence >= threshold
            - CONTINUE signal with next_step=COUNTER_ANALYZE if confidence < threshold
            - FAIL signal if LLM raises an error
        """
        try:
            synthesis: dict[str, Any] = await self.llm.synthesize_findings(
                evidence=context.evidence,
                hypotheses=context.hypotheses,
                alert_summary=context.alert_summary,
            )
        except Exception:
            return StepResult(
                context=context,
                signal=ExecutionSignal.FAIL,
                output=None,
            )

        # Update context with synthesis
        updated_context = context.model_copy(update={"current_synthesis": synthesis})

        # Check confidence threshold
        confidence = synthesis.get("confidence", 0.0)
        if confidence >= self.confidence_threshold:
            return StepResult(
                context=updated_context,
                signal=ExecutionSignal.COMPLETE,
                output=synthesis,
            )
        else:
            return StepResult(
                context=updated_context,
                signal=ExecutionSignal.CONTINUE,
                output=synthesis,
                next_step=StepType.COUNTER_ANALYZE,
            )
