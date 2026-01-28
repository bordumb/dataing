"""Temporal Agent Adapter - bridges Temporal activities with AgentClient.

This adapter handles all dict↔domain type conversion using Pydantic's
model_validate() for robust, type-safe serialization at the Temporal boundary.

Design:
- Activities receive dicts from Temporal's JSON serialization
- This adapter converts dicts to domain types using model_validate()
- Calls AgentClient with proper domain objects
- Converts responses back to dicts for Temporal serialization

This is the SINGLE source of truth for Temporal↔Domain bridging.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
from dataing.agents.client import AgentClient
from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Hypothesis,
    InvestigationContext,
    LineageContext,
    MetricSpec,
    RelevantCodeChange,
)


class TemporalAgentAdapter:
    """Adapter that bridges Temporal activities with AgentClient.

    All dict↔domain type conversion happens here, keeping activities thin
    and AgentClient's API clean.
    """

    def __init__(self, agent_client: AgentClient) -> None:
        """Initialize the adapter.

        Args:
            agent_client: The underlying AgentClient to delegate to.
        """
        self._client = agent_client

    # -------------------------------------------------------------------------
    # Public API - matches what activities expect
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
        code_changes: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate hypotheses from dict inputs.

        Args:
            alert_summary: Summary of the alert.
            alert: Alert data as dict.
            schema_info: Schema info as dict.
            lineage_info: Lineage info as dict.
            num_hypotheses: Target number of hypotheses.
            pattern_hints: Optional hints from pattern matching.
            code_changes: Optional list of recent code changes affecting the asset.

        Returns:
            List of hypothesis dicts.
        """
        alert_obj = self._to_alert(alert, alert_summary)
        schema_obj = self._to_schema(schema_info)
        lineage_obj = self._to_lineage(lineage_info)
        code_changes_obj = self._to_code_changes(code_changes)

        context = InvestigationContext(schema=schema_obj, lineage=lineage_obj)
        hypotheses = await self._client.generate_hypotheses(
            alert_obj, context, num_hypotheses, code_changes=code_changes_obj
        )

        # Use mode="json" to ensure dates, UUIDs, etc. are JSON-serializable
        return [h.model_dump(mode="json") for h in hypotheses]

    async def synthesize_findings_for_temporal(
        self,
        *,
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        alert_summary: str,
        code_changes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Synthesize findings from dict inputs.

        Args:
            evidence: List of evidence dicts.
            hypotheses: List of hypothesis dicts (unused but kept for API compat).
            alert_summary: Summary of the alert.
            code_changes: Optional list of code changes related to the investigation.

        Returns:
            Synthesis result as dict.
        """
        evidence_objs = [self._to_evidence(e) for e in evidence]
        alert_obj = self._to_alert(None, alert_summary)
        code_changes_obj = self._to_code_changes(code_changes)

        result = await self._client.synthesize_findings_raw(
            alert_obj, evidence_objs, code_changes=code_changes_obj
        )

        return {
            "root_cause": result.root_cause,
            "confidence": result.confidence,
            "recommendations": list(result.recommendations),
            "supporting_evidence": list(result.supporting_evidence),
            "causal_chain": list(result.causal_chain),
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
        # AgentClient.counter_analyze already accepts dicts
        return await self._client.counter_analyze(
            synthesis=synthesis,
            evidence=evidence,
            hypotheses=hypotheses,
        )

    async def generate_query(
        self,
        *,
        hypothesis: dict[str, Any],
        schema_info: dict[str, Any],
        alert_summary: str,
        alert: dict[str, Any] | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: Hypothesis dict.
            schema_info: Schema info dict.
            alert_summary: Summary of the alert.
            alert: Optional alert dict.

        Returns:
            SQL query string.
        """
        hypothesis_obj = self._to_hypothesis(hypothesis)
        schema_obj = self._to_schema(schema_info)
        # Always create an alert object to ensure date context is available
        # The _to_alert method handles None by creating from alert_summary
        alert_obj = self._to_alert(alert, alert_summary)

        return await self._client.generate_query(
            hypothesis=hypothesis_obj,
            schema=schema_obj,
            alert=alert_obj,
        )

    async def interpret_evidence(
        self,
        *,
        hypothesis: dict[str, Any],
        query_result: dict[str, Any],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Interpret query result as evidence for/against hypothesis.

        Args:
            hypothesis: Hypothesis dict.
            query_result: Query result dict with rows, columns, etc.
            alert_summary: Summary of the alert.

        Returns:
            Evidence interpretation dict.
        """
        hypothesis_obj = self._to_hypothesis(hypothesis)
        query_result_obj = self._to_query_result(query_result)

        evidence = await self._client.interpret_evidence(
            hypothesis=hypothesis_obj,
            sql=query_result.get("query", ""),
            results=query_result_obj,
        )

        # Use mode="json" to ensure dates, UUIDs, etc. are JSON-serializable
        return evidence.model_dump(mode="json")

    # -------------------------------------------------------------------------
    # Conversion helpers - use Pydantic model_validate where possible
    # -------------------------------------------------------------------------

    def _to_alert(self, alert: dict[str, Any] | None, alert_summary: str) -> AnomalyAlert:
        """Convert alert dict to AnomalyAlert using Pydantic validation.

        Args:
            alert: Alert data as dict, or None.
            alert_summary: Summary string as fallback.

        Returns:
            Validated AnomalyAlert object.
        """
        if alert:
            # If alert has all required fields, use model_validate directly
            try:
                return AnomalyAlert.model_validate(alert)
            except Exception:
                # Fall back to manual construction if validation fails
                pass

            # Manual construction with defaults for missing fields
            metric_spec_data = alert.get("metric_spec", {})
            if isinstance(metric_spec_data, dict):
                metric_spec = MetricSpec(
                    metric_type=metric_spec_data.get("metric_type", "description"),
                    expression=metric_spec_data.get("expression", alert_summary),
                    display_name=metric_spec_data.get("display_name", "Unknown Metric"),
                    columns_referenced=metric_spec_data.get("columns_referenced", []),
                )
            else:
                metric_spec = MetricSpec(
                    metric_type="description",
                    expression=alert_summary,
                    display_name="Alert",
                )

            return AnomalyAlert(
                dataset_ids=alert.get("dataset_ids", ["unknown"]),
                metric_spec=metric_spec,
                anomaly_type=alert.get("anomaly_type", "unknown"),
                expected_value=float(alert.get("expected_value", 0.0)),
                actual_value=float(alert.get("actual_value", 0.0)),
                deviation_pct=float(alert.get("deviation_pct", 0.0)),
                anomaly_date=alert.get("anomaly_date", "unknown"),
                severity=alert.get("severity", "medium"),
                source_system=alert.get("source_system"),
            )

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

    def _to_schema(self, schema_info: dict[str, Any] | None) -> SchemaResponse:
        """Convert schema dict to SchemaResponse.

        Expected format: {"target_table": {...}}

        Args:
            schema_info: Schema data with target_table, or None.

        Returns:
            SchemaResponse object.
        """
        if not schema_info or "target_table" not in schema_info:
            return SchemaResponse(
                source_id="unknown",
                source_type=SourceType.POSTGRESQL,
                source_category=SourceCategory.DATABASE,
                fetched_at=datetime.now(),
                catalogs=[],
            )

        target = schema_info["target_table"]
        if not target:
            return SchemaResponse(
                source_id="unknown",
                source_type=SourceType.POSTGRESQL,
                source_category=SourceCategory.DATABASE,
                fetched_at=datetime.now(),
                catalogs=[],
            )

        # Build columns from target table
        columns = []
        for col_data in target.get("columns", []):
            try:
                data_type = NormalizedType(col_data.get("data_type", "unknown"))
            except ValueError:
                data_type = NormalizedType.UNKNOWN
            columns.append(
                Column(
                    name=col_data.get("name", "unknown"),
                    data_type=data_type,
                    native_type=col_data.get("native_type"),
                    nullable=col_data.get("nullable", True),
                    is_primary_key=col_data.get("is_primary_key", False),
                    is_partition_key=col_data.get("is_partition_key", False),
                    description=col_data.get("description"),
                    default_value=col_data.get("default_value"),
                )
            )

        # Parse native_path to extract schema name
        native_path = target.get("native_path", target.get("name", "unknown"))
        parts = native_path.split(".")
        schema_name = parts[0] if len(parts) > 1 else "default"
        table_name = parts[-1]

        table = Table(
            name=table_name,
            table_type=target.get("table_type", "table"),
            native_type=target.get("native_type", "TABLE"),
            native_path=native_path,
            columns=columns,
        )

        # Wrap in catalog/schema structure
        return SchemaResponse(
            source_id="unknown",
            source_type=SourceType.POSTGRESQL,
            source_category=SourceCategory.DATABASE,
            fetched_at=datetime.now(),
            catalogs=[
                Catalog(
                    name="default",
                    schemas=[Schema(name=schema_name, tables=[table])],
                )
            ],
        )

    def _to_lineage(self, lineage_info: dict[str, Any] | None) -> LineageContext | None:
        """Convert lineage dict to LineageContext.

        Args:
            lineage_info: Lineage data as dict, or None.

        Returns:
            LineageContext or None.
        """
        if not lineage_info:
            return None

        return LineageContext(
            target=lineage_info.get("target", ""),
            upstream=tuple(lineage_info.get("upstream", [])),
            downstream=tuple(lineage_info.get("downstream", [])),
        )

    def _to_code_changes(
        self, code_changes: list[dict[str, Any]] | None
    ) -> list[RelevantCodeChange] | None:
        """Convert code changes dicts to RelevantCodeChange objects.

        Args:
            code_changes: List of code change dicts, or None.

        Returns:
            List of RelevantCodeChange objects or None.
        """
        if not code_changes:
            return None

        result = []
        for change in code_changes:
            try:
                result.append(RelevantCodeChange.model_validate(change))
            except Exception:
                # Manual fallback for malformed data
                result.append(
                    RelevantCodeChange(
                        commit_hash=change.get("commit_hash", "unknown"),
                        author_name=change.get("author_name"),
                        message=change.get("message"),
                        committed_at=change.get("committed_at"),
                        affected_assets=change.get("affected_assets", []),
                        relevance_score=float(change.get("relevance_score", 0.0)),
                        relevance_reason=change.get("relevance_reason", "unknown"),
                    )
                )
        return result if result else None

    def _to_hypothesis(self, hypothesis: dict[str, Any]) -> Hypothesis:
        """Convert hypothesis dict to Hypothesis.

        Args:
            hypothesis: Hypothesis data as dict.

        Returns:
            Hypothesis object.
        """
        try:
            return Hypothesis.model_validate(hypothesis)
        except Exception:
            # Manual fallback
            from dataing.core.domain_types import HypothesisCategory

            try:
                category = HypothesisCategory(hypothesis.get("category", "data_quality"))
            except ValueError:
                category = HypothesisCategory.DATA_QUALITY

            return Hypothesis(
                id=hypothesis.get("id", "unknown"),
                title=hypothesis.get("title", "Unknown hypothesis"),
                category=category,
                reasoning=hypothesis.get("reasoning", ""),
                suggested_query=hypothesis.get("suggested_query", "SELECT 1"),
            )

    def _to_evidence(self, evidence: dict[str, Any]) -> Evidence:
        """Convert evidence dict to Evidence.

        Args:
            evidence: Evidence data as dict.

        Returns:
            Evidence object.
        """
        try:
            return Evidence.model_validate(evidence)
        except Exception:
            # Manual fallback
            return Evidence(
                hypothesis_id=evidence.get("hypothesis_id", "unknown"),
                query=evidence.get("query", ""),
                result_summary=evidence.get("result_summary", ""),
                row_count=int(evidence.get("row_count", 0)),
                supports_hypothesis=evidence.get("supports_hypothesis"),
                confidence=float(evidence.get("confidence", 0.0)),
                interpretation=evidence.get("interpretation", ""),
                commit_refs=evidence.get("commit_refs"),
            )

    def _to_query_result(self, query_result: dict[str, Any]) -> Any:
        """Convert query result dict to QueryResult.

        Args:
            query_result: Query result data as dict.

        Returns:
            QueryResult-like object with to_summary() method.
        """
        from dataing.adapters.datasource.types import QueryResult

        try:
            return QueryResult.model_validate(query_result)
        except Exception:
            # Create a minimal QueryResult
            return QueryResult(
                columns=query_result.get("columns", []),
                rows=query_result.get("rows", []),
                row_count=query_result.get("row_count", 0),
                truncated=query_result.get("truncated", False),
                execution_time_ms=query_result.get("execution_time_ms", 0),
            )
