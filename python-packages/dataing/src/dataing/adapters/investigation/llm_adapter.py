"""LLM adapter for unified investigation steps.

This module provides adapters that wrap the AgentClient to implement
the protocol interfaces expected by the unified investigation steps.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.adapters.datasource.types import (
    Catalog,
    QueryResult,
    Schema,
    SchemaResponse,
    SourceCategory,
    SourceType,
)
from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    MetricSpec,
)

if TYPE_CHECKING:
    from dataing.agents.client import AgentClient
    from dataing.services.usage import UsageTracker


def _create_minimal_alert(alert_summary: str) -> AnomalyAlert:
    """Create a minimal AnomalyAlert from a summary string.

    Args:
        alert_summary: The alert summary text.

    Returns:
        AnomalyAlert with minimal required fields.
    """
    metric_spec = MetricSpec(
        metric_type="column",
        expression="",
        display_name=alert_summary,
        columns_referenced=[],
    )
    return AnomalyAlert(
        dataset_ids=["unknown"],
        metric_spec=metric_spec,
        anomaly_type="unknown",
        expected_value=0,
        actual_value=0,
        deviation_pct=0,
        anomaly_date="unknown",
        severity="medium",
    )


def _dict_to_schema_response(schema_info: dict[str, Any] | None) -> SchemaResponse:
    """Convert a schema info dict to SchemaResponse.

    Args:
        schema_info: Schema information as dict, or None.

    Returns:
        SchemaResponse object (may be empty if schema_info is None).
    """
    if schema_info is None:
        return SchemaResponse(
            source_id="unknown",
            source_type=SourceType.POSTGRESQL,
            source_category=SourceCategory.DATABASE,
            fetched_at=datetime.now(),
            catalogs=[],
        )

    # If already contains catalogs structure, reconstruct
    if "catalogs" in schema_info:
        return SchemaResponse.model_validate(schema_info)

    # Otherwise create minimal response
    return SchemaResponse(
        source_id=schema_info.get("source_id", "unknown"),
        source_type=SourceType(schema_info.get("source_type", "postgresql")),
        source_category=SourceCategory(schema_info.get("source_category", "database")),
        fetched_at=datetime.now(),
        catalogs=[
            Catalog(
                name="default",
                schemas=[Schema(name="public", tables=[])],
            )
        ],
    )


def _dict_to_query_result(query_result: dict[str, Any]) -> QueryResult:
    """Convert a query result dict to QueryResult.

    Args:
        query_result: Query result as dict.

    Returns:
        QueryResult object.
    """
    return QueryResult(
        columns=query_result.get("columns", []),
        rows=query_result.get("rows", []),
        row_count=query_result.get("row_count", 0),
        truncated=query_result.get("truncated", False),
        execution_time_ms=query_result.get("execution_time_ms"),
    )


def _dict_to_hypothesis(hypothesis: dict[str, Any]) -> Hypothesis:
    """Convert a hypothesis dict to Hypothesis.

    Args:
        hypothesis: Hypothesis as dict.

    Returns:
        Hypothesis object.
    """
    return Hypothesis(
        id=hypothesis.get("id", ""),
        title=hypothesis.get("title", ""),
        category=HypothesisCategory(hypothesis.get("category", "transformation_bug")),
        reasoning=hypothesis.get("reasoning", ""),
        suggested_query=hypothesis.get("suggested_query", ""),
    )


class HypothesisLLMAdapter:
    """Adapter that wraps AgentClient for GenerateHypothesesStep.

    Implements the LLMProtocol expected by GenerateHypothesesStep.
    """

    def __init__(
        self,
        agent_client: AgentClient,
        usage_tracker: UsageTracker | None = None,
        tenant_id: UUID | None = None,
        investigation_id: UUID | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        """Initialize the adapter.

        Args:
            agent_client: The underlying AgentClient.
            usage_tracker: Optional usage tracker for recording LLM usage.
            tenant_id: Tenant ID for usage tracking.
            investigation_id: Investigation ID for usage tracking.
            model: Model name for usage tracking.
        """
        self._client = agent_client
        self._usage_tracker = usage_tracker
        self._tenant_id = tenant_id
        self._investigation_id = investigation_id
        self._model = model

    async def generate_hypotheses(
        self,
        *,
        alert_summary: str,
        alert: dict[str, Any] | None,
        schema_info: dict[str, Any] | None,
        lineage_info: dict[str, Any] | None,
        num_hypotheses: int,
        pattern_hints: list[str] | None,
    ) -> list[Hypothesis]:
        """Generate hypotheses about potential root causes.

        Args:
            alert_summary: Summary of the anomaly alert (for display).
            alert: Full alert data with date, column, values (for LLM prompts).
            schema_info: Database schema information.
            lineage_info: Data lineage information.
            num_hypotheses: Maximum number of hypotheses to generate.
            pattern_hints: Hints from matched patterns.

        Returns:
            List of generated hypotheses.
        """
        # Use full alert if provided, otherwise fall back to minimal alert
        if alert is not None:
            anomaly_alert = AnomalyAlert.model_validate(alert)
        else:
            anomaly_alert = _create_minimal_alert(alert_summary)

        schema = _dict_to_schema_response(schema_info)

        # Build context with schema (lineage is optional)
        context = InvestigationContext(
            schema=schema,
            lineage=None,  # TODO: Convert lineage_info to LineageContext if needed
        )

        result: list[Hypothesis] = await self._client.generate_hypotheses(
            alert=anomaly_alert,
            context=context,
            num_hypotheses=num_hypotheses,
        )

        # Record usage (estimate tokens based on prompt + response)
        if self._usage_tracker and self._tenant_id:
            # Rough estimate: 4 chars per token
            input_tokens = len(str(alert_summary) + str(schema_info)) // 4
            output_tokens = sum(len(h.title) + len(h.reasoning) for h in result) // 4
            await self._usage_tracker.record_llm_usage(
                tenant_id=self._tenant_id,
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                investigation_id=self._investigation_id,
            )

        return result


class SynthesisLLMAdapter:
    """Adapter that wraps AgentClient for SynthesizeStep.

    Implements the LLMProtocol expected by SynthesizeStep.
    """

    def __init__(
        self,
        agent_client: AgentClient,
        usage_tracker: UsageTracker | None = None,
        tenant_id: UUID | None = None,
        investigation_id: UUID | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        """Initialize the adapter.

        Args:
            agent_client: The underlying AgentClient.
            usage_tracker: Optional usage tracker for recording LLM usage.
            tenant_id: Tenant ID for usage tracking.
            investigation_id: Investigation ID for usage tracking.
            model: Model name for usage tracking.
        """
        self._client = agent_client
        self._usage_tracker = usage_tracker
        self._tenant_id = tenant_id
        self._investigation_id = investigation_id
        self._model = model

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
            Synthesis dict with all fields from LLM response.
        """
        # Convert evidence dicts to Evidence objects
        evidence_objects = [
            Evidence(
                hypothesis_id=e.get("hypothesis_id", ""),
                query=e.get("query", ""),
                result_summary=e.get("result_summary", ""),
                row_count=e.get("row_count", 0),
                supports_hypothesis=e.get("supports_hypothesis"),
                confidence=e.get("confidence", 0.5),
                interpretation=e.get("interpretation", ""),
            )
            for e in evidence
        ]

        alert = _create_minimal_alert(alert_summary)

        # Get full synthesis response from LLM
        synthesis_response = await self._client.synthesize_findings_raw(
            alert=alert,
            evidence=evidence_objects,
        )

        # Record usage
        if self._usage_tracker and self._tenant_id:
            input_tokens = len(str(evidence) + alert_summary) // 4
            output_tokens = len(str(synthesis_response.root_cause)) // 4
            await self._usage_tracker.record_llm_usage(
                tenant_id=self._tenant_id,
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                investigation_id=self._investigation_id,
            )

        return {
            "root_cause": synthesis_response.root_cause,
            "confidence": synthesis_response.confidence,
            "causal_chain": synthesis_response.causal_chain,
            "estimated_onset": synthesis_response.estimated_onset,
            "affected_scope": synthesis_response.affected_scope,
            "recommendations": synthesis_response.recommendations,
            "supporting_evidence": synthesis_response.supporting_evidence,
        }


class QueryLLMAdapter:
    """Adapter that wraps AgentClient for GenerateQueryStep.

    Implements the LLMProtocol expected by GenerateQueryStep.
    """

    def __init__(
        self,
        agent_client: AgentClient,
        usage_tracker: UsageTracker | None = None,
        tenant_id: UUID | None = None,
        investigation_id: UUID | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        """Initialize the adapter.

        Args:
            agent_client: The underlying AgentClient.
            usage_tracker: Optional usage tracker for recording LLM usage.
            tenant_id: Tenant ID for usage tracking.
            investigation_id: Investigation ID for usage tracking.
            model: Model name for usage tracking.
        """
        self._client = agent_client
        self._usage_tracker = usage_tracker
        self._tenant_id = tenant_id
        self._investigation_id = investigation_id
        self._model = model

    async def generate_query(
        self,
        *,
        hypothesis: dict[str, Any],
        schema_info: dict[str, Any],
        alert_summary: str,
        alert: dict[str, Any] | None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema_info: Database schema information.
            alert_summary: Summary of the anomaly alert (for display).
            alert: Full alert data with date, column, values (for LLM prompts).

        Returns:
            SQL query string.
        """
        hyp = _dict_to_hypothesis(hypothesis)

        # Convert schema_info dict to SchemaResponse at runtime
        schema = _dict_to_schema_response(schema_info)

        # Convert alert dict to AnomalyAlert if provided
        anomaly_alert = AnomalyAlert.model_validate(alert) if alert else None

        generated_query: str = await self._client.generate_query(
            hypothesis=hyp,
            schema=schema,
            alert=anomaly_alert,
        )

        # Record usage
        if self._usage_tracker and self._tenant_id:
            input_tokens = len(str(hypothesis) + str(schema_info)) // 4
            output_tokens = len(generated_query) // 4
            await self._usage_tracker.record_llm_usage(
                tenant_id=self._tenant_id,
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                investigation_id=self._investigation_id,
            )

        return generated_query


class InterpretEvidenceLLMAdapter:
    """Adapter that wraps AgentClient for InterpretEvidenceStep.

    Implements the LLMProtocol expected by InterpretEvidenceStep.
    """

    def __init__(
        self,
        agent_client: AgentClient,
        usage_tracker: UsageTracker | None = None,
        tenant_id: UUID | None = None,
        investigation_id: UUID | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        """Initialize the adapter.

        Args:
            agent_client: The underlying AgentClient.
            usage_tracker: Optional usage tracker for recording LLM usage.
            tenant_id: Tenant ID for usage tracking.
            investigation_id: Investigation ID for usage tracking.
            model: Model name for usage tracking.
        """
        self._client = agent_client
        self._usage_tracker = usage_tracker
        self._tenant_id = tenant_id
        self._investigation_id = investigation_id
        self._model = model

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
            Evidence dict with hypothesis_id, supports_hypothesis, confidence,
            interpretation, query, result_summary, row_count.
        """
        hyp = _dict_to_hypothesis(hypothesis)
        results = _dict_to_query_result(query_result)

        # Get query from hypothesis if available
        sql = hypothesis.get("suggested_query", "")

        # AgentClient.interpret_evidence returns Evidence domain type
        evidence_obj = await self._client.interpret_evidence(
            hypothesis=hyp,
            sql=sql,
            results=results,
        )

        # Record usage
        if self._usage_tracker and self._tenant_id:
            input_tokens = len(str(hypothesis) + str(query_result)) // 4
            output_tokens = len(evidence_obj.interpretation) // 4
            await self._usage_tracker.record_llm_usage(
                tenant_id=self._tenant_id,
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                investigation_id=self._investigation_id,
            )

        return {
            "hypothesis_id": evidence_obj.hypothesis_id,
            "query": evidence_obj.query,
            "result_summary": evidence_obj.result_summary,
            "row_count": evidence_obj.row_count,
            "supports_hypothesis": evidence_obj.supports_hypothesis,
            "confidence": evidence_obj.confidence,
            "interpretation": evidence_obj.interpretation,
        }
