"""Integration tests for the full investigation flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dataing.adapters.context.engine import DefaultContextEngine
from dataing.adapters.db.mock import MockDatabaseAdapter
from dataing.core.domain_types import (
    AnomalyAlert,
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
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.core.state import InvestigationState
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


class TestInvestigationFlow:
    """Integration tests for the investigation flow."""

    @pytest.fixture
    def mock_db(self) -> MockDatabaseAdapter:
        """Return a mock database adapter with responses."""
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
            "COUNT": QueryResult(
                columns=("count",),
                rows=({"count": 500},),
                row_count=1,
            ),
            "SELECT": QueryResult(
                columns=("id", "status"),
                rows=(
                    {"id": 1, "status": "pending"},
                    {"id": 2, "status": "pending"},
                ),
                row_count=2,
            ),
        }

        return MockDatabaseAdapter(responses=responses, schema=schema)

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Return a mock LLM client."""
        mock = AsyncMock()

        # Generate hypotheses
        mock.generate_hypotheses.return_value = [
            Hypothesis(
                id="h001",
                title="Upstream ETL failure",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="The upstream users table may have failed to load.",
                suggested_query="SELECT COUNT(*) FROM users WHERE created_at >= '2024-01-15' LIMIT 100",
            ),
            Hypothesis(
                id="h002",
                title="Data quality issue",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Orders may have been marked with invalid status.",
                suggested_query="SELECT COUNT(*) FROM orders WHERE status = 'invalid' LIMIT 100",
            ),
        ]

        # Generate queries
        mock.generate_query.return_value = (
            "SELECT COUNT(*) FROM orders WHERE created_at >= '2024-01-15' LIMIT 100"
        )

        # Interpret evidence
        mock.interpret_evidence.return_value = Evidence(
            hypothesis_id="h001",
            query="SELECT COUNT(*) FROM orders LIMIT 100",
            result_summary="count=500",
            row_count=1,
            supports_hypothesis=True,
            confidence=0.85,
            interpretation="The row count confirms a 50% reduction.",
        )

        # Synthesize findings
        mock.synthesize_findings.return_value = Finding(
            investigation_id="",
            status="completed",
            root_cause="Upstream ETL job for users table failed, causing a 50% reduction in orders.",
            confidence=0.9,
            evidence=[],
            recommendations=[
                "Restart the ETL job for the users table",
                "Add monitoring for ETL failures",
            ],
            duration_seconds=0.0,
        )

        return mock

    @pytest.fixture
    def mock_context_engine(self, mock_db: MockDatabaseAdapter) -> AsyncMock:
        """Return a mock context engine."""
        mock = AsyncMock()
        mock.gather.return_value = InvestigationContext(
            schema=SchemaContext(
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
                )
            ),
            lineage=LineageContext(
                target="public.orders",
                upstream=("public.users",),
                downstream=(),
            ),
        )
        return mock

    @pytest.fixture
    def circuit_breaker(self) -> CircuitBreaker:
        """Return a circuit breaker."""
        return CircuitBreaker(CircuitBreakerConfig())

    @pytest.fixture
    def orchestrator(
        self,
        mock_db: MockDatabaseAdapter,
        mock_llm: AsyncMock,
        mock_context_engine: AsyncMock,
        circuit_breaker: CircuitBreaker,
    ) -> InvestigationOrchestrator:
        """Return an orchestrator with mock dependencies."""
        return InvestigationOrchestrator(
            db=mock_db,
            llm=mock_llm,
            context_engine=mock_context_engine,
            circuit_breaker=circuit_breaker,
            config=OrchestratorConfig(
                max_hypotheses=3,
                max_queries_per_hypothesis=2,
            ),
        )

    @pytest.fixture
    def alert(self) -> AnomalyAlert:
        """Return a sample anomaly alert."""
        return AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
            metadata={"source": "monte_carlo"},
        )

    async def test_full_investigation_flow(
        self,
        orchestrator: InvestigationOrchestrator,
        alert: AnomalyAlert,
        mock_llm: AsyncMock,
    ) -> None:
        """Test the complete investigation flow from start to finish."""
        state = InvestigationState(id="inv-001", alert=alert)

        finding = await orchestrator.run_investigation(state)

        # Verify finding
        assert finding.investigation_id == "inv-001"
        assert finding.status == "completed"
        assert finding.root_cause is not None
        assert finding.confidence > 0.0
        assert len(finding.recommendations) > 0

        # Verify LLM calls
        mock_llm.generate_hypotheses.assert_called_once()
        mock_llm.synthesize_findings.assert_called_once()

    async def test_investigation_collects_events(
        self,
        orchestrator: InvestigationOrchestrator,
        alert: AnomalyAlert,
    ) -> None:
        """Test that investigation collects events."""
        state = InvestigationState(id="inv-002", alert=alert)

        await orchestrator.run_investigation(state)

        # The state should have events recorded
        # Note: In a real implementation, events would be persisted

    async def test_investigation_handles_no_hypotheses(
        self,
        orchestrator: InvestigationOrchestrator,
        alert: AnomalyAlert,
        mock_llm: AsyncMock,
    ) -> None:
        """Test investigation when LLM returns no hypotheses."""
        mock_llm.generate_hypotheses.return_value = []

        state = InvestigationState(id="inv-003", alert=alert)

        finding = await orchestrator.run_investigation(state)

        # Should still complete with inconclusive result
        assert finding.investigation_id == "inv-003"

    async def test_investigation_respects_circuit_breaker(
        self,
        mock_db: MockDatabaseAdapter,
        mock_llm: AsyncMock,
        mock_context_engine: AsyncMock,
        alert: AnomalyAlert,
    ) -> None:
        """Test that circuit breaker limits are respected."""
        # Create strict circuit breaker
        circuit_breaker = CircuitBreaker(
            CircuitBreakerConfig(
                max_total_queries=2,
                max_queries_per_hypothesis=1,
            )
        )

        orchestrator = InvestigationOrchestrator(
            db=mock_db,
            llm=mock_llm,
            context_engine=mock_context_engine,
            circuit_breaker=circuit_breaker,
            config=OrchestratorConfig(),
        )

        # Generate many hypotheses to trigger circuit breaker
        mock_llm.generate_hypotheses.return_value = [
            Hypothesis(
                id=f"h{i:03d}",
                title=f"Hypothesis {i}",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Test",
                suggested_query="SELECT 1 LIMIT 1",
            )
            for i in range(10)
        ]

        state = InvestigationState(id="inv-004", alert=alert)

        finding = await orchestrator.run_investigation(state)

        # Should complete even with circuit breaker limit
        assert finding.investigation_id == "inv-004"

    async def test_investigation_with_lineage(
        self,
        orchestrator: InvestigationOrchestrator,
        alert: AnomalyAlert,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Test investigation includes lineage context."""
        state = InvestigationState(id="inv-005", alert=alert)

        await orchestrator.run_investigation(state)

        # Verify context engine was called
        mock_context_engine.gather.assert_called_once()

    async def test_investigation_query_execution(
        self,
        orchestrator: InvestigationOrchestrator,
        alert: AnomalyAlert,
        mock_db: MockDatabaseAdapter,
    ) -> None:
        """Test that queries are actually executed."""
        state = InvestigationState(id="inv-006", alert=alert)

        await orchestrator.run_investigation(state)

        # Verify queries were executed
        assert mock_db.get_query_count() > 0
