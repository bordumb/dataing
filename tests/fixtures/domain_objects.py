"""Domain object fixtures for testing."""

from __future__ import annotations

from datetime import datetime, timezone

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
from dataing.core.state import Event, InvestigationState


@pytest.fixture
def sample_anomaly_alert() -> AnomalyAlert:
    """Return a sample anomaly alert."""
    return AnomalyAlert(
        dataset_id="public.orders",
        metric_name="row_count",
        expected_value=1000.0,
        actual_value=500.0,
        deviation_pct=50.0,
        anomaly_date="2024-01-15",
        severity="high",
        metadata={"source": "test"},
    )


@pytest.fixture
def sample_table_schema() -> TableSchema:
    """Return a sample table schema."""
    return TableSchema(
        table_name="public.orders",
        columns=("id", "user_id", "total", "status", "created_at"),
        column_types={
            "id": "integer",
            "user_id": "integer",
            "total": "numeric",
            "status": "varchar",
            "created_at": "timestamp",
        },
    )


@pytest.fixture
def sample_schema_context(sample_table_schema: TableSchema) -> SchemaContext:
    """Return a sample schema context."""
    users_table = TableSchema(
        table_name="public.users",
        columns=("id", "email", "created_at"),
        column_types={
            "id": "integer",
            "email": "varchar",
            "created_at": "timestamp",
        },
    )
    return SchemaContext(tables=(sample_table_schema, users_table))


@pytest.fixture
def sample_lineage_context() -> LineageContext:
    """Return a sample lineage context."""
    return LineageContext(
        target="public.orders",
        upstream=("public.users", "public.products"),
        downstream=("public.order_summary",),
    )


@pytest.fixture
def sample_investigation_context(
    sample_schema_context: SchemaContext,
    sample_lineage_context: LineageContext,
) -> InvestigationContext:
    """Return a sample investigation context."""
    return InvestigationContext(
        schema=sample_schema_context,
        lineage=sample_lineage_context,
    )


@pytest.fixture
def sample_hypothesis() -> Hypothesis:
    """Return a sample hypothesis."""
    return Hypothesis(
        id="h001",
        title="Upstream data source failure",
        category=HypothesisCategory.UPSTREAM_DEPENDENCY,
        reasoning="The row count drop may be caused by a failure in the upstream ETL.",
        suggested_query="SELECT COUNT(*) FROM public.orders WHERE created_at >= '2024-01-15' LIMIT 100",
    )


@pytest.fixture
def sample_query_result() -> QueryResult:
    """Return a sample query result."""
    return QueryResult(
        columns=("count",),
        rows=({"count": 500},),
        row_count=1,
    )


@pytest.fixture
def sample_evidence(sample_hypothesis: Hypothesis) -> Evidence:
    """Return a sample evidence object."""
    return Evidence(
        hypothesis_id=sample_hypothesis.id,
        query="SELECT COUNT(*) FROM public.orders WHERE created_at >= '2024-01-15' LIMIT 100",
        result_summary="count=500",
        row_count=1,
        supports_hypothesis=True,
        confidence=0.85,
        interpretation="The query confirms a 50% reduction in row count on the anomaly date.",
    )


@pytest.fixture
def sample_finding(sample_evidence: Evidence) -> Finding:
    """Return a sample finding."""
    return Finding(
        investigation_id="inv-001",
        status="completed",
        root_cause="Upstream ETL job failed due to timeout",
        confidence=0.9,
        evidence=[sample_evidence],
        recommendations=[
            "Restart the ETL job",
            "Add monitoring for ETL timeouts",
        ],
        duration_seconds=120.5,
    )


@pytest.fixture
def sample_investigation_state(sample_anomaly_alert: AnomalyAlert) -> InvestigationState:
    """Return a sample investigation state."""
    return InvestigationState(
        id="inv-001",
        alert=sample_anomaly_alert,
        events=[],
    )


@pytest.fixture
def sample_event() -> Event:
    """Return a sample event."""
    return Event(
        type="investigation_started",
        timestamp=datetime.now(timezone.utc),
        data={"dataset_id": "public.orders"},
    )


@pytest.fixture
def sample_approval_request() -> ApprovalRequest:
    """Return a sample approval request."""
    return ApprovalRequest(
        investigation_id="inv-001",
        request_type=ApprovalRequestType.QUERY_APPROVAL,
        context={"query": "SELECT * FROM users LIMIT 10"},
        requested_at=datetime.now(timezone.utc),
        requested_by="system",
    )


@pytest.fixture
def sample_approval_decision() -> ApprovalDecision:
    """Return a sample approval decision."""
    return ApprovalDecision(
        request_id="req-001",
        decision=ApprovalDecisionType.APPROVED,
        decided_by="admin",
        decided_at=datetime.now(timezone.utc),
        comment="Approved for testing",
    )
