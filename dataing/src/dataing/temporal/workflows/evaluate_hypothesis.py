"""EvaluateHypothesis child workflow for parallel hypothesis evaluation."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from dataing.temporal.activities import (
        execute_query,
        generate_query,
        interpret_evidence,
    )


@dataclass
class EvaluateHypothesisInput:
    """Input for evaluating a single hypothesis."""

    investigation_id: str
    hypothesis_index: int
    hypothesis: dict[str, Any]
    schema_info: dict[str, Any]
    alert_summary: str
    alert: dict[str, Any] | None = None


@dataclass
class EvaluateHypothesisResult:
    """Result from evaluating a single hypothesis."""

    hypothesis_index: int
    hypothesis_id: str
    evidence: list[dict[str, Any]]
    queries_executed: int
    error: str | None = None


@workflow.defn
class EvaluateHypothesisWorkflow:
    """Child workflow for evaluating a single hypothesis.

    Each hypothesis evaluation runs as a separate child workflow, enabling:
    - Parallel execution of multiple hypotheses
    - Independent retry/failure handling per hypothesis
    - Visibility in Temporal UI as separate executions
    """

    @workflow.run
    async def run(self, input: EvaluateHypothesisInput) -> EvaluateHypothesisResult:
        """Execute hypothesis evaluation: generate query → execute → interpret.

        Args:
            input: Hypothesis evaluation input containing hypothesis and context.

        Returns:
            EvaluateHypothesisResult with evidence gathered.
        """
        hypothesis_id = input.hypothesis.get("id", f"h-{input.hypothesis_index}")

        # Step 1: Generate SQL query to test this hypothesis
        query = await workflow.execute_activity(
            generate_query,
            args=[input.investigation_id, input.hypothesis, input.schema_info],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # Step 2: Execute the generated query
        query_result = await workflow.execute_activity(
            execute_query,
            args=[input.investigation_id, query, hypothesis_id],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 3: Interpret the evidence
        evidence = await workflow.execute_activity(
            interpret_evidence,
            args=[input.investigation_id, input.hypothesis, query_result],
            start_to_close_timeout=timedelta(minutes=2),
        )

        return EvaluateHypothesisResult(
            hypothesis_index=input.hypothesis_index,
            hypothesis_id=hypothesis_id,
            evidence=[evidence],
            queries_executed=1,
        )


async def evaluate_hypotheses_parallel(
    workflow_info: Any,
    investigation_id: str,
    hypotheses: list[dict[str, Any]],
    schema_info: dict[str, Any],
    alert_summary: str,
    alert: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate multiple hypotheses in parallel using child workflows.

    This helper function starts child workflows for each hypothesis and
    waits for all to complete. Failed child workflows don't crash the parent.

    Args:
        workflow_info: The workflow.info() object from the parent workflow.
        investigation_id: ID of the investigation.
        hypotheses: List of hypothesis dictionaries.
        schema_info: Schema information for query generation.
        alert_summary: Summary of the alert being investigated.
        alert: Optional full alert data.

    Returns:
        List of evidence dictionaries from all successful evaluations.
    """
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
            id=f"{workflow_info.workflow_id}-hypothesis-{i}",
        )
        handles.append(handle)

    # Wait for all children to complete (don't crash on individual failures)
    results = await asyncio.gather(*handles, return_exceptions=True)

    # Aggregate evidence from successful evaluations
    all_evidence: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, Exception):
            # Log but don't fail - continue with other hypotheses
            workflow.logger.warning(f"Child workflow failed: {result}")
            continue
        if isinstance(result, EvaluateHypothesisResult):
            if result.error:
                workflow.logger.warning(
                    f"Hypothesis {result.hypothesis_id} evaluation error: {result.error}"
                )
            else:
                all_evidence.extend(result.evidence)

    return all_evidence
