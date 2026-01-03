"""Unit tests for InvestigationOrchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    QueryResult,
    SchemaContext,
    TableSchema,
)
from dataing.core.exceptions import CircuitBreakerTripped, SchemaDiscoveryError
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.core.state import InvestigationState
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = OrchestratorConfig()

        assert config.max_hypotheses == 5
        assert config.max_queries_per_hypothesis == 3
        assert config.max_retries_per_hypothesis == 2
        assert config.query_timeout_seconds == 30
        assert config.high_confidence_threshold == 0.85


class TestInvestigationOrchestrator:
    """Tests for InvestigationOrchestrator."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Return a mock database adapter."""
        mock = AsyncMock()
        mock.execute_query.return_value = QueryResult(
            columns=("count",),
            rows=({"count": 500},),
            row_count=1,
        )
        mock.get_schema.return_value = SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.orders",
                    columns=("id", "total"),
                    column_types={"id": "integer", "total": "numeric"},
                ),
            )
        )
        return mock

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Return a mock LLM client."""
        mock = AsyncMock()
        mock.generate_hypotheses.return_value = [
            Hypothesis(
                id="h001",
                title="Test Hypothesis",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Test reasoning",
                suggested_query="SELECT 1 LIMIT 100",
            )
        ]
        mock.generate_query.return_value = "SELECT COUNT(*) FROM orders LIMIT 100"
        mock.interpret_evidence.return_value = Evidence(
            hypothesis_id="h001",
            query="SELECT COUNT(*) FROM orders LIMIT 100",
            result_summary="count=500",
            row_count=1,
            supports_hypothesis=True,
            confidence=0.9,
            interpretation="Evidence supports hypothesis",
        )
        mock.synthesize_findings.return_value = Finding(
            investigation_id="",
            status="completed",
            root_cause="Test root cause",
            confidence=0.9,
            evidence=[],
            recommendations=["Test recommendation"],
            duration_seconds=0.0,
        )
        return mock

    @pytest.fixture
    def mock_context_engine(self) -> AsyncMock:
        """Return a mock context engine."""
        mock = AsyncMock()
        mock.gather.return_value = InvestigationContext(
            schema=SchemaContext(
                tables=(
                    TableSchema(
                        table_name="public.orders",
                        columns=("id", "total"),
                        column_types={"id": "integer", "total": "numeric"},
                    ),
                )
            ),
            lineage=None,
        )
        return mock

    @pytest.fixture
    def circuit_breaker(self) -> CircuitBreaker:
        """Return a circuit breaker."""
        return CircuitBreaker(CircuitBreakerConfig())

    @pytest.fixture
    def orchestrator(
        self,
        mock_db: AsyncMock,
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
        )

    @pytest.fixture
    def state(self, alert: AnomalyAlert) -> InvestigationState:
        """Return a sample investigation state."""
        return InvestigationState(id="inv-001", alert=alert)

    async def test_run_investigation_success(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
    ) -> None:
        """Test successful investigation execution."""
        finding = await orchestrator.run_investigation(state)

        assert finding.status == "completed"
        assert finding.investigation_id == "inv-001"
        assert finding.root_cause is not None

    async def test_run_investigation_calls_all_phases(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_context_engine: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test that all investigation phases are called."""
        await orchestrator.run_investigation(state)

        mock_context_engine.gather.assert_called_once()
        mock_llm.generate_hypotheses.assert_called_once()
        mock_llm.synthesize_findings.assert_called_once()

    async def test_run_investigation_schema_error(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Test investigation fails on schema discovery error."""
        mock_context_engine.gather.side_effect = SchemaDiscoveryError("No schema")

        with pytest.raises(SchemaDiscoveryError):
            await orchestrator.run_investigation(state)

    async def test_run_investigation_empty_schema(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Test investigation fails on empty schema."""
        mock_context_engine.gather.return_value = InvestigationContext(
            schema=SchemaContext(tables=()),
            lineage=None,
        )

        with pytest.raises(SchemaDiscoveryError):
            await orchestrator.run_investigation(state)

    async def test_run_investigation_circuit_breaker(
        self,
        mock_db: AsyncMock,
        mock_llm: AsyncMock,
        mock_context_engine: AsyncMock,
        state: InvestigationState,
    ) -> None:
        """Test investigation handles circuit breaker trip."""
        # Create circuit breaker with very low limits
        circuit_breaker = CircuitBreaker(
            CircuitBreakerConfig(max_total_queries=1)
        )

        orchestrator = InvestigationOrchestrator(
            db=mock_db,
            llm=mock_llm,
            context_engine=mock_context_engine,
            circuit_breaker=circuit_breaker,
        )

        # Make LLM generate multiple hypotheses to trigger circuit breaker
        mock_llm.generate_hypotheses.return_value = [
            Hypothesis(
                id=f"h{i:03d}",
                title=f"Hypothesis {i}",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Test",
                suggested_query="SELECT 1",
            )
            for i in range(5)
        ]

        finding = await orchestrator.run_investigation(state)

        # Investigation completes even with circuit breaker limits
        # It may have limited evidence due to query limits
        assert finding.status in ("completed", "failed")

    async def test_gather_context_success(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Test successful context gathering."""
        updated_state = await orchestrator._gather_context(state)

        assert updated_state.schema_context is not None
        assert len(updated_state.events) == 1
        assert updated_state.events[0].type == "context_gathered"

    async def test_generate_hypotheses_success(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_llm: AsyncMock,
    ) -> None:
        """Test successful hypothesis generation."""
        # Set up state with schema
        state = state.with_context(
            schema_context=SchemaContext(
                tables=(
                    TableSchema(
                        table_name="public.orders",
                        columns=("id",),
                        column_types={"id": "integer"},
                    ),
                )
            )
        )

        updated_state, hypotheses = await orchestrator._generate_hypotheses(state)

        assert len(hypotheses) == 1
        assert len(updated_state.events) == 1
        assert updated_state.events[0].type == "hypothesis_generated"

    async def test_investigate_hypothesis_success(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_db: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test successful hypothesis investigation."""
        state = state.with_context(
            schema_context=SchemaContext(
                tables=(
                    TableSchema(
                        table_name="public.orders",
                        columns=("id",),
                        column_types={"id": "integer"},
                    ),
                )
            )
        )

        hypothesis = Hypothesis(
            id="h001",
            title="Test",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Test",
            suggested_query="SELECT 1",
        )

        evidence = await orchestrator._investigate_hypothesis(state, hypothesis)

        assert len(evidence) >= 1
        mock_db.execute_query.assert_called()
        mock_llm.interpret_evidence.assert_called()

    async def test_investigate_hypothesis_high_confidence_early_stop(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_llm: AsyncMock,
    ) -> None:
        """Test that high confidence stops investigation early."""
        state = state.with_context(
            schema_context=SchemaContext(
                tables=(
                    TableSchema(
                        table_name="public.orders",
                        columns=("id",),
                        column_types={"id": "integer"},
                    ),
                )
            )
        )

        # Return high confidence evidence
        mock_llm.interpret_evidence.return_value = Evidence(
            hypothesis_id="h001",
            query="SELECT 1",
            result_summary="",
            row_count=1,
            supports_hypothesis=True,
            confidence=0.95,  # Above threshold
            interpretation="Very confident",
        )

        hypothesis = Hypothesis(
            id="h001",
            title="Test",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Test",
            suggested_query="SELECT 1",
        )

        evidence = await orchestrator._investigate_hypothesis(state, hypothesis)

        # Should only have one evidence because of early stop
        assert len(evidence) == 1
