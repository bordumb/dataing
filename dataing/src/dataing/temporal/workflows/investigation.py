"""Investigation workflow definition for Temporal."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from dataing.temporal.activities import gather_context, generate_hypotheses, synthesize


@dataclass
class InvestigationInput:
    """Input for starting an investigation workflow."""

    investigation_id: str
    tenant_id: str
    datasource_id: str
    alert_data: dict[str, Any]


@dataclass
class InvestigationResult:
    """Result of a completed investigation workflow."""

    investigation_id: str
    status: str
    context: dict[str, Any]
    hypotheses: list[dict[str, Any]]
    synthesis: dict[str, Any]


@workflow.defn
class InvestigationWorkflow:
    """Main investigation workflow that orchestrates the investigation process.

    This workflow executes three activities sequentially:
    1. gather_context - Gathers schema and lineage information
    2. generate_hypotheses - Generates hypotheses based on context
    3. synthesize - Synthesizes findings into a final result
    """

    @workflow.run
    async def run(self, input: InvestigationInput) -> InvestigationResult:
        """Execute the investigation workflow.

        Args:
            input: Investigation input containing alert data and identifiers.

        Returns:
            InvestigationResult with status and findings.
        """
        # Step 1: Gather context (schema, lineage, sample data)
        context = await workflow.execute_activity(
            gather_context,
            args=[input.investigation_id, input.datasource_id],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 2: Generate hypotheses based on context
        hypotheses = await workflow.execute_activity(
            generate_hypotheses,
            args=[input.investigation_id, input.alert_data, context],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 3: Synthesize findings
        synthesis = await workflow.execute_activity(
            synthesize,
            args=[input.investigation_id, context, hypotheses],
            start_to_close_timeout=timedelta(minutes=5),
        )

        return InvestigationResult(
            investigation_id=input.investigation_id,
            status="completed",
            context=context,
            hypotheses=hypotheses,
            synthesis=synthesis,
        )
