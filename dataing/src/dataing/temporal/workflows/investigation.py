"""Investigation workflow definition for Temporal."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from dataing.temporal.activities import (
        check_patterns,
        counter_analyze,
        gather_context,
        generate_hypotheses,
        synthesize,
    )
    from dataing.temporal.workflows.evaluate_hypothesis import (
        EvaluateHypothesisInput,
        EvaluateHypothesisWorkflow,
    )


@dataclass
class InvestigationInput:
    """Input for starting an investigation workflow."""

    investigation_id: str
    tenant_id: str
    datasource_id: str
    alert_data: dict[str, Any]
    alert_summary: str = ""
    max_hypotheses: int = 5
    confidence_threshold: float = 0.85


@dataclass
class InvestigationResult:
    """Result of a completed investigation workflow."""

    investigation_id: str
    status: str
    context: dict[str, Any]
    hypotheses: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    synthesis: dict[str, Any]
    counter_analysis: dict[str, Any] | None = None


@workflow.defn
class InvestigationWorkflow:
    """Main investigation workflow that orchestrates the full investigation process.

    This workflow:
    1. Gathers context (schema, lineage, sample data)
    2. Checks for known patterns
    3. Generates hypotheses based on context and patterns
    4. Evaluates hypotheses in parallel via child workflows
    5. Synthesizes findings into root cause analysis
    6. Optionally performs counter-analysis if confidence is low
    """

    @workflow.run
    async def run(self, input: InvestigationInput) -> InvestigationResult:
        """Execute the investigation workflow.

        Args:
            input: Investigation input containing alert data and identifiers.

        Returns:
            InvestigationResult with status and findings.
        """
        alert_summary = input.alert_summary or str(input.alert_data)

        # Step 1: Gather context (schema, lineage, sample data)
        context = await workflow.execute_activity(
            gather_context,
            args=[input.investigation_id, input.datasource_id],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 2: Check for known patterns (used for hypothesis hints in production)
        _patterns = await workflow.execute_activity(
            check_patterns,
            args=[input.investigation_id, input.alert_data, context],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # Step 3: Generate hypotheses based on context and patterns
        hypotheses = await workflow.execute_activity(
            generate_hypotheses,
            args=[input.investigation_id, input.alert_data, context],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 4: Evaluate hypotheses in parallel via child workflows
        evidence = await self._evaluate_hypotheses_parallel(
            investigation_id=input.investigation_id,
            hypotheses=hypotheses,
            schema_info=context.get("schema", {}),
            alert_summary=alert_summary,
            alert=input.alert_data,
        )

        # Step 5: Synthesize findings
        synthesis = await workflow.execute_activity(
            synthesize,
            args=[input.investigation_id, context, hypotheses],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 6: Counter-analysis if confidence is below threshold
        counter_analysis = None
        root_cause = synthesis.get("root_cause", {})
        confidence = root_cause.get("confidence", 1.0) if isinstance(root_cause, dict) else 1.0
        if confidence < input.confidence_threshold:
            counter_analysis = await workflow.execute_activity(
                counter_analyze,
                args=[input.investigation_id, synthesis, evidence],
                start_to_close_timeout=timedelta(minutes=5),
            )

        return InvestigationResult(
            investigation_id=input.investigation_id,
            status="completed",
            context=context,
            hypotheses=hypotheses,
            evidence=evidence,
            synthesis=synthesis,
            counter_analysis=counter_analysis,
        )

    async def _evaluate_hypotheses_parallel(
        self,
        investigation_id: str,
        hypotheses: list[dict[str, Any]],
        schema_info: dict[str, Any],
        alert_summary: str,
        alert: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate hypotheses in parallel using child workflows.

        Args:
            investigation_id: ID of the investigation.
            hypotheses: List of hypothesis dictionaries.
            schema_info: Schema information for query generation.
            alert_summary: Summary of the alert being investigated.
            alert: Optional full alert data.

        Returns:
            List of evidence dictionaries from all successful evaluations.
        """
        import asyncio

        if not hypotheses:
            return []

        # Start all child workflows
        handles = []
        for i, hypothesis in enumerate(hypotheses):
            child_input = EvaluateHypothesisInput(
                investigation_id=investigation_id,
                hypothesis_index=i,
                hypothesis=hypothesis,
                schema_info=schema_info,
                alert_summary=alert_summary,
                alert=alert,
            )
            handle = await workflow.start_child_workflow(
                EvaluateHypothesisWorkflow.run,
                child_input,
                id=f"{workflow.info().workflow_id}-hypothesis-{i}",
            )
            handles.append(handle)

        # Wait for all children to complete (don't crash on individual failures)
        results = await asyncio.gather(*handles, return_exceptions=True)

        # Aggregate evidence from successful evaluations
        all_evidence: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, BaseException):
                workflow.logger.warning(f"Child workflow failed: {result}")
                continue
            # result is now narrowed to EvaluateHypothesisResult
            if result.error:
                workflow.logger.warning(
                    f"Hypothesis {result.hypothesis_id} evaluation error: {result.error}"
                )
            else:
                all_evidence.extend(result.evidence)

        return all_evidence
