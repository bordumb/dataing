"""Mock objects for testing."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.adapters.db.mock import MockDatabaseAdapter
from dataing.core.domain_types import (
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


@pytest.fixture
def mock_database_adapter() -> MockDatabaseAdapter:
    """Return a configured mock database adapter."""
    schema = SchemaContext(
        tables=(
            TableSchema(
                table_name="public.orders",
                columns=("id", "user_id", "total", "status", "created_at"),
                column_types={
                    "id": "integer",
                    "user_id": "integer",
                    "total": "numeric",
                    "status": "varchar",
                    "created_at": "timestamp",
                },
            ),
            TableSchema(
                table_name="public.users",
                columns=("id", "email", "created_at"),
                column_types={
                    "id": "integer",
                    "email": "varchar",
                    "created_at": "timestamp",
                },
            ),
        )
    )

    responses = {
        "SELECT COUNT": QueryResult(
            columns=("count",),
            rows=({"count": 500},),
            row_count=1,
        ),
    }

    return MockDatabaseAdapter(responses=responses, schema=schema)


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Return a mock LLM client."""
    mock = AsyncMock()

    # Mock generate_hypotheses
    mock.generate_hypotheses.return_value = [
        Hypothesis(
            id="h001",
            title="Upstream ETL failure",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="ETL may have failed",
            suggested_query="SELECT COUNT(*) FROM orders LIMIT 100",
        ),
        Hypothesis(
            id="h002",
            title="Data quality issue",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Data may be corrupted",
            suggested_query="SELECT * FROM orders WHERE total < 0 LIMIT 100",
        ),
    ]

    # Mock generate_query
    mock.generate_query.return_value = "SELECT COUNT(*) FROM orders WHERE created_at >= '2024-01-15' LIMIT 100"

    # Mock interpret_evidence
    mock.interpret_evidence.return_value = Evidence(
        hypothesis_id="h001",
        query="SELECT COUNT(*) FROM orders LIMIT 100",
        result_summary="count=500",
        row_count=1,
        supports_hypothesis=True,
        confidence=0.85,
        interpretation="Evidence supports the hypothesis",
    )

    # Mock synthesize_findings
    mock.synthesize_findings.return_value = Finding(
        investigation_id="",
        status="completed",
        root_cause="Upstream ETL job failed",
        confidence=0.9,
        evidence=[],
        recommendations=["Restart ETL job"],
        duration_seconds=0.0,
    )

    return mock


@pytest.fixture
def mock_context_engine(
    sample_schema_context: SchemaContext,
    sample_lineage_context: LineageContext,
) -> AsyncMock:
    """Return a mock context engine."""
    mock = AsyncMock()
    mock.gather.return_value = InvestigationContext(
        schema=sample_schema_context,
        lineage=sample_lineage_context,
    )
    return mock


@pytest.fixture
def mock_lineage_client() -> AsyncMock:
    """Return a mock lineage client."""
    mock = AsyncMock()
    mock.get_lineage.return_value = LineageContext(
        target="public.orders",
        upstream=("public.users",),
        downstream=(),
    )
    return mock


@pytest.fixture
def mock_app_database() -> AsyncMock:
    """Return a mock application database."""
    mock = AsyncMock()

    # Default return values
    mock.fetch_one.return_value = None
    mock.fetch_all.return_value = []
    mock.execute.return_value = "OK"
    mock.execute_returning.return_value = None

    # Tenant operations
    mock.get_tenant.return_value = {
        "id": "12345678-1234-5678-1234-567812345678",
        "name": "Test Tenant",
        "slug": "test-tenant",
        "settings": {},
    }
    mock.get_tenant_by_slug.return_value = None

    # API key operations
    mock.get_api_key_by_hash.return_value = None

    # Data source operations
    mock.list_data_sources.return_value = []

    # Investigation operations
    mock.list_investigations.return_value = []

    # Webhook operations
    mock.list_webhooks.return_value = []
    mock.get_webhooks_for_event.return_value = []

    return mock


@pytest.fixture
def mock_httpx_client() -> AsyncMock:
    """Return a mock httpx async client."""
    mock = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.is_success = True
    response.json.return_value = {}
    mock.post.return_value = response
    mock.get.return_value = response
    return mock
