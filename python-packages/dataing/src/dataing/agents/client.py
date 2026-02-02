"""AgentClient - LLM client facade for investigation agents.

Uses BondAgent for type-safe, validated LLM responses with optional streaming.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from bond import BondAgent, StreamHandlers
from bond.tools.memory import AgentMemoryProtocol, memory_toolset
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.output import PromptedOutput
from pydantic_ai.providers.anthropic import AnthropicProvider

from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    InvestigationContext,
    LineageContext,
    MetricSpec,
    RelevantCodeChange,
)
from dataing.core.exceptions import LLMError

from .models import (
    CounterAnalysisResponse,
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)

# Re-export for type hints in adapters
__all__ = ["AgentClient", "SynthesisResponse"]
from .prompts import counter_analysis, hypothesis, interpretation, query, reflexion, synthesis

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import QueryResult, SchemaResponse


class AgentClient:
    """LLM client facade for investigation agents.

    Uses BondAgent for type-safe, validated LLM responses with optional streaming.
    Prompts are modular and live in the prompts/ package.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
        memory_store: AgentMemoryProtocol | None = None,
    ) -> None:
        """Initialize the agent client.

        Args:
            api_key: Anthropic API key.
            model: Model to use.
            max_retries: Max retries on validation failure.
            memory_store: Optional memory store for agent memory persistence.
        """
        provider = AnthropicProvider(api_key=api_key)
        self._model = AnthropicModel(model, provider=provider)
        self._memory_store = memory_store

        # Configure toolsets and deps based on memory store availability
        toolsets = [memory_toolset] if memory_store else []
        deps = memory_store

        # Empty base instructions: all prompting via dynamic_instructions at runtime.
        # This ensures PromptedOutput gets the full detailed prompt without conflicts.
        self._hypothesis_agent: BondAgent[HypothesesResponse, AgentMemoryProtocol | None] = (
            BondAgent(
                name="hypothesis-generator",
                instructions="",
                model=self._model,
                output_type=PromptedOutput(HypothesesResponse),
                max_retries=max_retries,
                toolsets=toolsets,
                deps=deps,
            )
        )
        self._interpretation_agent: BondAgent[
            InterpretationResponse, AgentMemoryProtocol | None
        ] = BondAgent(
            name="evidence-interpreter",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(InterpretationResponse),
            max_retries=max_retries,
            toolsets=toolsets,
            deps=deps,
        )
        self._synthesis_agent: BondAgent[SynthesisResponse, AgentMemoryProtocol | None] = BondAgent(
            name="finding-synthesizer",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(SynthesisResponse),
            max_retries=max_retries,
            toolsets=toolsets,
            deps=deps,
        )
        self._query_agent: BondAgent[QueryResponse, AgentMemoryProtocol | None] = BondAgent(
            name="sql-generator",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(QueryResponse),
            max_retries=max_retries,
            toolsets=toolsets,
            deps=deps,
        )
        self._counter_analysis_agent: BondAgent[
            CounterAnalysisResponse, AgentMemoryProtocol | None
        ] = BondAgent(
            name="counter-analyst",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(CounterAnalysisResponse),
            max_retries=max_retries,
            toolsets=toolsets,
            deps=deps,
        )

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
        handlers: StreamHandlers | None = None,
        code_changes: list[RelevantCodeChange] | None = None,
        tenant_id: UUID | None = None,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate.
            context: Available schema and lineage context.
            num_hypotheses: Target number of hypotheses.
            handlers: Optional streaming handlers for real-time updates.
            code_changes: Optional list of recent code changes affecting the asset.
            tenant_id: Optional tenant ID for memory scoping.

        Returns:
            List of validated Hypothesis objects.

        Raises:
            LLMError: If LLM call fails after retries.
        """
        system_prompt = hypothesis.build_system(num_hypotheses=num_hypotheses)
        user_prompt = hypothesis.build_user(alert=alert, context=context, code_changes=code_changes)

        try:
            result = await self._hypothesis_agent.ask(
                user_prompt,
                dynamic_instructions=system_prompt,
                handlers=handlers,
            )

            return [
                Hypothesis(
                    id=h.id,
                    title=h.title,
                    category=h.category,
                    reasoning=h.reasoning,
                    suggested_query=h.suggested_query,
                )
                for h in result.hypotheses
            ]

        except Exception as e:
            raise LLMError(
                f"Hypothesis generation failed: {e}",
                retryable=False,
            ) from e

    async def generate_query(
        self,
        hypothesis: Hypothesis,
        schema: SchemaResponse,
        previous_error: str | None = None,
        handlers: StreamHandlers | None = None,
        alert: AnomalyAlert | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous attempt (for reflexion).
            handlers: Optional streaming handlers for real-time updates.
            alert: The anomaly alert being investigated (for date/context).

        Returns:
            Validated SQL query string.

        Raises:
            LLMError: If query generation fails.
        """
        if previous_error:
            prompt = reflexion.build_user(hypothesis=hypothesis, previous_error=previous_error)
            system = reflexion.build_system(schema=schema)
        else:
            prompt = query.build_user(hypothesis=hypothesis, alert=alert)
            system = query.build_system(schema=schema, alert=alert)

        try:
            result = await self._query_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )
            sql_query: str = result.query
            return sql_query

        except Exception as e:
            raise LLMError(
                f"Query generation failed: {e}",
                retryable=True,
            ) from e

    async def interpret_evidence(
        self,
        hypothesis: Hypothesis,
        sql: str,
        results: QueryResult,
        handlers: StreamHandlers | None = None,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested.
            sql: The query that was executed.
            results: The query results.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Evidence with validated interpretation.
        """
        prompt = interpretation.build_user(hypothesis=hypothesis, query=sql, results=results)
        system = interpretation.build_system()

        try:
            result = await self._interpretation_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )

            return Evidence(
                hypothesis_id=hypothesis.id,
                query=sql,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=result.supports_hypothesis,
                confidence=result.confidence,
                interpretation=result.interpretation,
            )

        except Exception as e:
            # Return low-confidence evidence on failure rather than crashing
            return Evidence(
                hypothesis_id=hypothesis.id,
                query=sql,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=None,
                confidence=0.3,
                interpretation=f"Interpretation failed: {e}",
            )

    async def synthesize_findings(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
        handlers: StreamHandlers | None = None,
    ) -> Finding:
        """Synthesize all evidence into a root cause finding.

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Finding with validated root cause and recommendations.

        Raises:
            LLMError: If synthesis fails.
        """
        result = await self.synthesize_findings_raw(alert, evidence, handlers)

        return Finding(
            investigation_id="",  # Set by orchestrator
            status="completed" if result.root_cause else "inconclusive",
            root_cause=result.root_cause,
            confidence=result.confidence,
            evidence=evidence,
            recommendations=result.recommendations,
            duration_seconds=0.0,  # Set by orchestrator
        )

    async def synthesize_findings_raw(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
        handlers: StreamHandlers | None = None,
        code_changes: list[RelevantCodeChange] | None = None,
        tenant_id: UUID | None = None,
    ) -> SynthesisResponse:
        """Synthesize all evidence into a root cause finding (raw response).

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.
            handlers: Optional streaming handlers for real-time updates.
            code_changes: Optional list of code changes related to the investigation.
            tenant_id: Optional tenant ID for memory scoping.

        Returns:
            Raw SynthesisResponse with all fields from LLM.

        Raises:
            LLMError: If synthesis fails.
        """
        prompt = synthesis.build_user(alert=alert, evidence=evidence, code_changes=code_changes)
        system = synthesis.build_system()

        try:
            result: SynthesisResponse = await self._synthesis_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )
            return result

        except Exception as e:
            raise LLMError(
                f"Synthesis failed: {e}",
                retryable=False,
            ) from e

    # -------------------------------------------------------------------------
    # Dict-based methods for Temporal activities
    # These accept raw dicts and convert to domain types internally
    # -------------------------------------------------------------------------

    async def generate_hypotheses_for_temporal(
        self,
        *,
        alert_summary: str,
        alert: dict[str, Any] | None,
        schema_info: dict[str, Any] | None,
        lineage_info: dict[str, Any] | None,
        num_hypotheses: int = 5,
        pattern_hints: list[str] | None = None,
    ) -> list[Hypothesis]:
        """Generate hypotheses from dict inputs (for Temporal activities).

        Args:
            alert_summary: Summary of the alert.
            alert: Alert data as dict.
            schema_info: Schema info as dict.
            lineage_info: Lineage info as dict.
            num_hypotheses: Target number of hypotheses.
            pattern_hints: Optional hints from pattern matching.

        Returns:
            List of Hypothesis objects.
        """
        # Convert alert dict to AnomalyAlert
        alert_obj = self._dict_to_alert(alert, alert_summary)

        # Convert schema dict to SchemaResponse
        schema_obj = self._dict_to_schema(schema_info)

        # Convert lineage dict to LineageContext
        lineage_obj = None
        if lineage_info:
            lineage_obj = LineageContext(
                target=lineage_info.get("target", ""),
                upstream=tuple(lineage_info.get("upstream", [])),
                downstream=tuple(lineage_info.get("downstream", [])),
            )

        context = InvestigationContext(schema=schema_obj, lineage=lineage_obj)
        return await self.generate_hypotheses(alert_obj, context, num_hypotheses)

    async def synthesize_findings_for_temporal(
        self,
        *,
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Synthesize findings from dict inputs (for Temporal activities).

        Args:
            evidence: List of evidence dicts.
            hypotheses: List of hypothesis dicts.
            alert_summary: Summary of the alert.

        Returns:
            Synthesis result as dict.
        """
        # Convert evidence dicts to Evidence objects
        evidence_objs = [
            Evidence(
                hypothesis_id=e.get("hypothesis_id", "unknown"),
                query=e.get("query", ""),
                result_summary=e.get("result_summary", ""),
                row_count=e.get("row_count", 0),
                supports_hypothesis=e.get("supports_hypothesis"),
                confidence=e.get("confidence", 0.0),
                interpretation=e.get("interpretation", ""),
            )
            for e in evidence
        ]

        # Create a minimal alert for synthesis
        alert_obj = self._dict_to_alert(None, alert_summary)

        result = await self.synthesize_findings_raw(alert_obj, evidence_objs)
        return {
            "root_cause": result.root_cause,
            "confidence": result.confidence,
            "recommendations": result.recommendations,
            "supporting_evidence": result.supporting_evidence,
            "causal_chain": result.causal_chain,
            "estimated_onset": result.estimated_onset,
            "affected_scope": result.affected_scope,
        }

    async def counter_analyze(
        self,
        *,
        synthesis: dict[str, Any],
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Perform counter-analysis on synthesis conclusion.

        Args:
            synthesis: The current synthesis/conclusion.
            evidence: All collected evidence.
            hypotheses: The hypotheses that were tested.

        Returns:
            Counter-analysis result as dict.
        """
        prompt = counter_analysis.build_user(
            synthesis=synthesis,
            evidence=evidence,
            hypotheses=hypotheses,
        )
        system = counter_analysis.build_system()

        try:
            result = await self._counter_analysis_agent.ask(
                prompt,
                dynamic_instructions=system,
            )
            return {
                "alternative_explanations": result.alternative_explanations,
                "weaknesses": result.weaknesses,
                "confidence_adjustment": result.confidence_adjustment,
                "recommendation": result.recommendation,
            }

        except Exception as e:
            raise LLMError(
                f"Counter-analysis failed: {e}",
                retryable=False,
            ) from e

    def _dict_to_schema(self, schema_info: dict[str, Any] | None) -> SchemaResponse:
        """Convert schema dict to SchemaResponse domain object.

        Args:
            schema_info: Schema data as dict, or None.

        Returns:
            SchemaResponse object.
        """
        from datetime import datetime

        from dataing.adapters.datasource.types import (
            Catalog,
            Column,
            NormalizedType,
            Schema,
            SchemaResponse,
            SourceCategory,
            SourceType,
            Table,
        )

        if not schema_info:
            return SchemaResponse(
                source_id="unknown",
                source_type=SourceType.POSTGRESQL,
                source_category=SourceCategory.DATABASE,
                fetched_at=datetime.now(),
                catalogs=[],
            )

        # Try to reconstruct from nested structure
        catalogs = []
        for cat_data in schema_info.get("catalogs", []):
            schemas = []
            for sch_data in cat_data.get("schemas", []):
                tables = []
                for tbl_data in sch_data.get("tables", []):
                    columns = []
                    for col_data in tbl_data.get("columns", []):
                        columns.append(
                            Column(
                                name=col_data.get("name", "unknown"),
                                data_type=NormalizedType(col_data.get("data_type", "unknown")),
                                native_type=col_data.get("native_type", "unknown"),
                                nullable=col_data.get("nullable", True),
                            )
                        )
                    tables.append(
                        Table(
                            name=tbl_data.get("name", "unknown"),
                            table_type=tbl_data.get("table_type", "table"),
                            native_type=tbl_data.get("native_type", "TABLE"),
                            native_path=tbl_data.get(
                                "native_path", tbl_data.get("name", "unknown")
                            ),
                            columns=columns,
                        )
                    )
                schemas.append(Schema(name=sch_data.get("name", "default"), tables=tables))
            catalogs.append(Catalog(name=cat_data.get("name", "default"), schemas=schemas))

        return SchemaResponse(
            source_id=schema_info.get("source_id", "unknown"),
            source_type=SourceType(schema_info.get("source_type", "postgresql")),
            source_category=SourceCategory(schema_info.get("source_category", "database")),
            fetched_at=datetime.now(),
            catalogs=catalogs,
        )

    def _dict_to_alert(self, alert: dict[str, Any] | None, alert_summary: str) -> AnomalyAlert:
        """Convert alert dict to AnomalyAlert domain object.

        Args:
            alert: Alert data as dict, or None.
            alert_summary: Summary string as fallback.

        Returns:
            AnomalyAlert object.
        """
        if alert:
            # Extract metric_spec from alert if present
            metric_spec_data = alert.get("metric_spec", {})
            metric_spec = MetricSpec(
                metric_type=metric_spec_data.get("metric_type", "description"),
                expression=metric_spec_data.get("expression", alert_summary),
                display_name=metric_spec_data.get("display_name", "Unknown Metric"),
                columns_referenced=metric_spec_data.get("columns_referenced", []),
            )

            return AnomalyAlert(
                dataset_ids=alert.get("dataset_ids", ["unknown"]),
                metric_spec=metric_spec,
                anomaly_type=alert.get("anomaly_type", "unknown"),
                expected_value=alert.get("expected_value", 0.0),
                actual_value=alert.get("actual_value", 0.0),
                deviation_pct=alert.get("deviation_pct", 0.0),
                anomaly_date=alert.get("anomaly_date", "unknown"),
                severity=alert.get("severity", "medium"),
                source_system=alert.get("source_system"),
            )
        else:
            # Create minimal alert from summary
            return AnomalyAlert(
                dataset_ids=["unknown"],
                metric_spec=MetricSpec(
                    metric_type="description",
                    expression=alert_summary,
                    display_name="Alert",
                ),
                anomaly_type="unknown",
                expected_value=0.0,
                actual_value=0.0,
                deviation_pct=0.0,
                anomaly_date="unknown",
                severity="medium",
            )
