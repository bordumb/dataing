"""EvaluateHypothesis child workflow for parallel hypothesis evaluation."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from dataing.temporal.activities import (
        ExecuteQueryInput,
        GenerateQueryInput,
        InterpretEvidenceInput,
    )
    from dataing.temporal.errors import LLM_RETRY_POLICY


@dataclass
class EvaluateHypothesisInput:
    """Input for evaluating a single hypothesis."""

    investigation_id: str
    hypothesis_index: int
    hypothesis: dict[str, Any]
    schema_info: dict[str, Any]
    alert_summary: str
    tenant_id: str
    datasource_id: str
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
        # With llm-failures-v1, LLM activities retry per LLM_RETRY_POLICY; a failure the
        # model caused fails this child, and the parent fails the run
        llm_options: dict[str, Any] = (
            {"retry_policy": LLM_RETRY_POLICY} if workflow.patched("llm-failures-v1") else {}
        )

        # Step 1: Generate SQL query to test this hypothesis
        query_input = GenerateQueryInput(
            investigation_id=input.investigation_id,
            hypothesis=input.hypothesis,
            schema_info=input.schema_info,
            alert_summary=input.alert_summary,
            alert=input.alert,
        )
        query_result = await workflow.execute_activity(
            "generate_query",
            query_input,
            start_to_close_timeout=timedelta(minutes=2),
            **llm_options,
        )

        if query_result.get("error"):
            return EvaluateHypothesisResult(
                hypothesis_index=input.hypothesis_index,
                hypothesis_id=hypothesis_id,
                evidence=[],
                queries_executed=0,
                error=query_result["error"],
            )

        query = query_result.get("query", "")

        # Step 2: Execute the generated query
        execute_input = ExecuteQueryInput(
            investigation_id=input.investigation_id,
            query=query,
            hypothesis_id=hypothesis_id,
            tenant_id=input.tenant_id,
            datasource_id=input.datasource_id,
        )
        execute_result = await workflow.execute_activity(
            "execute_query",
            execute_input,
            start_to_close_timeout=timedelta(minutes=5),
        )

        # A failed query is not an empty result: report it, never interpret it
        if execute_result.get("error"):
            return EvaluateHypothesisResult(
                hypothesis_index=input.hypothesis_index,
                hypothesis_id=hypothesis_id,
                evidence=[],
                queries_executed=1,
                error=execute_result["error"],
            )

        # Step 3: Interpret the evidence
        interpret_input = InterpretEvidenceInput(
            investigation_id=input.investigation_id,
            hypothesis=input.hypothesis,
            query_result={
                "query": query,
                "columns": execute_result.get("columns", []),
                "rows": execute_result.get("rows", []),
                "row_count": execute_result.get("row_count", 0),
                "truncated": execute_result.get("truncated", False),
                "execution_time_ms": execute_result.get("execution_time_ms", 0),
            },
            alert_summary=input.alert_summary,
        )
        interpret_result = await workflow.execute_activity(
            "interpret_evidence",
            interpret_input,
            start_to_close_timeout=timedelta(minutes=2),
            **llm_options,
        )

        # A failed interpretation is not a refutation: report it, never use it as evidence
        if interpret_result.get("error"):
            return EvaluateHypothesisResult(
                hypothesis_index=input.hypothesis_index,
                hypothesis_id=hypothesis_id,
                evidence=[],
                queries_executed=1,
                error=interpret_result["error"],
            )

        # Build evidence dict from interpretation
        evidence = {
            "hypothesis_id": hypothesis_id,
            "query": query,
            "supports_hypothesis": interpret_result.get("supports_hypothesis", False),
            "confidence": interpret_result.get("confidence", 0.0),
            "interpretation": interpret_result.get("interpretation", ""),
            "key_findings": interpret_result.get("key_findings", []),
            "result_summary": str(execute_result.get("rows", [])[:5]),
            "row_count": execute_result.get("row_count", 0),
        }

        return EvaluateHypothesisResult(
            hypothesis_index=input.hypothesis_index,
            hypothesis_id=hypothesis_id,
            evidence=[evidence],
            queries_executed=1,
        )
