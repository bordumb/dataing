"""Unit tests for domain types."""

from __future__ import annotations

import pytest

from dataing.core.domain_types import (
    AnomalyAlert,
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRequest,
    ApprovalRequestType,
    Evidence,
    Finding,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    LineageContext,
    QueryResult,
    SchemaContext,
    TableSchema,
)


class TestAnomalyAlert:
    """Tests for AnomalyAlert."""

    def test_create_alert(self) -> None:
        """Test creating an anomaly alert."""
        alert = AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
        )

        assert alert.dataset_id == "public.orders"
        assert alert.metric_name == "row_count"
        assert alert.deviation_pct == 50.0

    def test_alert_is_frozen(self) -> None:
        """Test that alert is immutable."""
        alert = AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
        )

        with pytest.raises(Exception):  # Pydantic raises ValidationError
            alert.dataset_id = "modified"

    def test_alert_with_metadata(self) -> None:
        """Test alert with optional metadata."""
        alert = AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
            metadata={"source": "airflow", "dag_id": "etl_daily"},
        )

        assert alert.metadata["source"] == "airflow"


class TestHypothesis:
    """Tests for Hypothesis."""

    def test_create_hypothesis(self) -> None:
        """Test creating a hypothesis."""
        hypothesis = Hypothesis(
            id="h001",
            title="Upstream failure",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="The upstream table may have failed.",
            suggested_query="SELECT COUNT(*) FROM upstream LIMIT 100",
        )

        assert hypothesis.id == "h001"
        assert hypothesis.category == HypothesisCategory.UPSTREAM_DEPENDENCY

    def test_hypothesis_categories(self) -> None:
        """Test all hypothesis categories."""
        assert HypothesisCategory.UPSTREAM_DEPENDENCY.value == "upstream_dependency"
        assert HypothesisCategory.TRANSFORMATION_BUG.value == "transformation_bug"
        assert HypothesisCategory.DATA_QUALITY.value == "data_quality"
        assert HypothesisCategory.INFRASTRUCTURE.value == "infrastructure"
        assert HypothesisCategory.EXPECTED_VARIANCE.value == "expected_variance"


class TestEvidence:
    """Tests for Evidence."""

    def test_create_evidence(self) -> None:
        """Test creating evidence."""
        evidence = Evidence(
            hypothesis_id="h001",
            query="SELECT COUNT(*) FROM orders",
            result_summary="count=500",
            row_count=1,
            supports_hypothesis=True,
            confidence=0.85,
            interpretation="Evidence supports the hypothesis.",
        )

        assert evidence.hypothesis_id == "h001"
        assert evidence.supports_hypothesis is True
        assert evidence.confidence == 0.85


class TestFinding:
    """Tests for Finding."""

    def test_create_finding(self) -> None:
        """Test creating a finding."""
        finding = Finding(
            investigation_id="inv-001",
            status="completed",
            root_cause="ETL job failed",
            confidence=0.9,
            evidence=[],
            recommendations=["Restart the job"],
            duration_seconds=120.5,
        )

        assert finding.status == "completed"
        assert finding.root_cause == "ETL job failed"
        assert finding.confidence == 0.9


class TestTableSchema:
    """Tests for TableSchema."""

    def test_create_table_schema(self) -> None:
        """Test creating a table schema."""
        schema = TableSchema(
            table_name="public.orders",
            columns=("id", "total", "status"),
            column_types={"id": "integer", "total": "numeric", "status": "varchar"},
        )

        assert schema.table_name == "public.orders"
        assert len(schema.columns) == 3
        assert schema.column_types["id"] == "integer"

    def test_table_schema_is_frozen(self) -> None:
        """Test that table schema is immutable."""
        schema = TableSchema(
            table_name="public.orders",
            columns=("id",),
        )

        with pytest.raises(Exception):
            schema.table_name = "modified"


class TestSchemaContext:
    """Tests for SchemaContext."""

    @pytest.fixture
    def schema_context(self) -> SchemaContext:
        """Return a sample schema context."""
        return SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.orders",
                    columns=("id", "total"),
                    column_types={"id": "integer", "total": "numeric"},
                ),
                TableSchema(
                    table_name="public.users",
                    columns=("id", "email"),
                    column_types={"id": "integer", "email": "varchar"},
                ),
            )
        )

    def test_get_table_by_name(self, schema_context: SchemaContext) -> None:
        """Test getting a table by name."""
        table = schema_context.get_table("public.orders")

        assert table is not None
        assert table.table_name == "public.orders"

    def test_get_table_case_insensitive(self, schema_context: SchemaContext) -> None:
        """Test that table lookup is case-insensitive."""
        table = schema_context.get_table("PUBLIC.ORDERS")

        assert table is not None
        assert table.table_name == "public.orders"

    def test_get_table_not_found(self, schema_context: SchemaContext) -> None:
        """Test getting a non-existent table."""
        table = schema_context.get_table("public.unknown")

        assert table is None

    def test_to_prompt_string(self, schema_context: SchemaContext) -> None:
        """Test formatting schema for LLM prompt."""
        prompt = schema_context.to_prompt_string()

        assert "AVAILABLE TABLES" in prompt
        assert "public.orders" in prompt
        assert "public.users" in prompt
        assert "id (integer)" in prompt


class TestLineageContext:
    """Tests for LineageContext."""

    def test_create_lineage_context(self) -> None:
        """Test creating a lineage context."""
        lineage = LineageContext(
            target="public.orders",
            upstream=("public.users", "public.products"),
            downstream=("public.summary",),
        )

        assert lineage.target == "public.orders"
        assert len(lineage.upstream) == 2
        assert len(lineage.downstream) == 1

    def test_to_prompt_string(self) -> None:
        """Test formatting lineage for LLM prompt."""
        lineage = LineageContext(
            target="public.orders",
            upstream=("public.users",),
            downstream=("public.summary",),
        )

        prompt = lineage.to_prompt_string()

        assert "TARGET TABLE: public.orders" in prompt
        assert "UPSTREAM DEPENDENCIES" in prompt
        assert "public.users" in prompt
        assert "DOWNSTREAM DEPENDENCIES" in prompt
        assert "public.summary" in prompt


class TestQueryResult:
    """Tests for QueryResult."""

    def test_create_query_result(self) -> None:
        """Test creating a query result."""
        result = QueryResult(
            columns=("id", "name"),
            rows=({"id": 1, "name": "Test"},),
            row_count=1,
        )

        assert len(result.columns) == 2
        assert result.row_count == 1

    def test_to_summary_empty(self) -> None:
        """Test summary for empty result."""
        result = QueryResult(columns=(), rows=(), row_count=0)

        assert result.to_summary() == "No rows returned"

    def test_to_summary_with_rows(self) -> None:
        """Test summary with rows."""
        result = QueryResult(
            columns=("id", "name"),
            rows=(
                {"id": 1, "name": "A"},
                {"id": 2, "name": "B"},
            ),
            row_count=2,
        )

        summary = result.to_summary()

        assert "Columns: id, name" in summary
        assert "Total rows: 2" in summary
        assert "id=1" in summary

    def test_to_summary_truncates(self) -> None:
        """Test summary truncates large results."""
        rows = tuple({"id": i} for i in range(100))
        result = QueryResult(columns=("id",), rows=rows, row_count=100)

        summary = result.to_summary(max_rows=5)

        assert "... and 95 more rows" in summary


class TestApprovalRequest:
    """Tests for ApprovalRequest."""

    def test_create_approval_request(self) -> None:
        """Test creating an approval request."""
        from datetime import datetime, timezone

        request = ApprovalRequest(
            investigation_id="inv-001",
            request_type=ApprovalRequestType.QUERY_APPROVAL,
            context={"query": "SELECT 1"},
            requested_at=datetime.now(timezone.utc),
            requested_by="system",
        )

        assert request.request_type == ApprovalRequestType.QUERY_APPROVAL

    def test_approval_request_types(self) -> None:
        """Test all approval request types."""
        assert ApprovalRequestType.CONTEXT_REVIEW.value == "context_review"
        assert ApprovalRequestType.QUERY_APPROVAL.value == "query_approval"
        assert ApprovalRequestType.EXECUTION_APPROVAL.value == "execution_approval"


class TestApprovalDecision:
    """Tests for ApprovalDecision."""

    def test_create_approval_decision(self) -> None:
        """Test creating an approval decision."""
        from datetime import datetime, timezone

        decision = ApprovalDecision(
            request_id="req-001",
            decision=ApprovalDecisionType.APPROVED,
            decided_by="admin",
            decided_at=datetime.now(timezone.utc),
        )

        assert decision.decision == ApprovalDecisionType.APPROVED

    def test_approval_decision_types(self) -> None:
        """Test all approval decision types."""
        assert ApprovalDecisionType.APPROVED.value == "approved"
        assert ApprovalDecisionType.REJECTED.value == "rejected"
        assert ApprovalDecisionType.MODIFIED.value == "modified"
