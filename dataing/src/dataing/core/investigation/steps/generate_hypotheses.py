"""GenerateHypotheses step implementation.

This step uses the LLM to generate hypotheses about potential root causes.
It returns a BRANCH signal to investigate each hypothesis in parallel.
"""

from __future__ import annotations

from typing import Any, Protocol

from dataing.core.domain_types import Hypothesis
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import BranchType, ExecutionSignal, StepType

from .protocol import BranchRequest, BranchSpec, Step, StepResult


class LLMProtocol(Protocol):
    """Protocol for LLM client used by GenerateHypothesesStep."""

    async def generate_hypotheses(
        self,
        *,
        alert_summary: str,
        schema_info: dict[str, Any] | None,
        lineage_info: dict[str, Any] | None,
        num_hypotheses: int,
        pattern_hints: list[str] | None,
    ) -> list[Hypothesis]:
        """Generate hypotheses about potential root causes.

        Args:
            alert_summary: Summary of the anomaly alert.
            schema_info: Database schema information.
            lineage_info: Data lineage information.
            num_hypotheses: Maximum number of hypotheses to generate.
            pattern_hints: Hints from matched patterns.

        Returns:
            List of generated hypotheses.
        """
        ...


class GenerateHypothesesStep(Step[None, list[Hypothesis]]):
    """Generate hypotheses about potential root causes.

    This step:
    1. Calls LLM with alert, schema, and pattern hints
    2. Returns BRANCH signal to investigate each hypothesis in parallel
    """

    step_type = StepType.GENERATE_HYPOTHESES

    def __init__(
        self,
        llm: LLMProtocol,
        max_hypotheses: int = 5,
    ) -> None:
        """Initialize the step.

        Args:
            llm: LLM client for generating hypotheses.
            max_hypotheses: Maximum number of hypotheses to generate.
        """
        self.llm = llm
        self.max_hypotheses = max_hypotheses

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
        input_data: None = None,
    ) -> StepResult[list[Hypothesis]]:
        """Generate hypotheses via LLM.

        Args:
            context: Current investigation context with schema.
            input_data: Not used for this step.

        Returns:
            StepResult with BRANCH signal and hypothesis branches.
        """
        # Extract pattern hints if any patterns matched
        pattern_hints = [p.get("description", p.get("name", "")) for p in context.matched_patterns]

        # Generate hypotheses
        hypotheses = await self.llm.generate_hypotheses(
            alert_summary=context.alert_summary,
            schema_info=context.schema_info,
            lineage_info=context.lineage_info,
            num_hypotheses=self.max_hypotheses,
            pattern_hints=pattern_hints if pattern_hints else None,
        )

        # Convert hypotheses to dicts for context storage
        hypotheses_dicts = [h.model_dump() for h in hypotheses]

        # Create branch specs for each hypothesis
        branch_specs = [
            BranchSpec(
                name=f"hypothesis_{h.id}",
                data={"hypothesis": h.model_dump()},
            )
            for h in hypotheses
        ]

        # Update context with hypotheses
        new_context = InvestigationContext(
            alert_summary=context.alert_summary,
            schema_info=context.schema_info,
            lineage_info=context.lineage_info,
            recent_changes=context.recent_changes,
            matched_patterns=context.matched_patterns,
            hypotheses=hypotheses_dicts,
            evidence=context.evidence,
            current_synthesis=context.current_synthesis,
            counter_analysis=context.counter_analysis,
            chat_history=context.chat_history,
            pending_approval=context.pending_approval,
            total_tokens_used=context.total_tokens_used,
            total_queries_executed=context.total_queries_executed,
            execution_time_ms=context.execution_time_ms,
        )

        return StepResult(
            context=new_context,
            signal=ExecutionSignal.BRANCH,
            output=hypotheses,
            branch_request=BranchRequest(
                branch_type=BranchType.HYPOTHESIS,
                branches=branch_specs,
                merge_step=StepType.SYNTHESIZE,
                child_start_step=StepType.GENERATE_QUERY,
            ),
        )
