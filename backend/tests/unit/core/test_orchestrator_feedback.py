"""Tests for orchestrator feedback event emission."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.investigation_feedback import EventType
from dataing.core.domain_types import AnomalyAlert
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.core.state import InvestigationState


class TestOrchestratorFeedbackEmission:
    """Tests for feedback event emission during investigations."""

    @pytest.fixture
    def mock_feedback(self) -> MagicMock:
        """Create mock feedback emitter."""
        feedback = MagicMock()
        feedback.emit = AsyncMock()
        return feedback

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        """Create mock LLM client."""
        llm = MagicMock()
        llm.generate_hypotheses = AsyncMock(return_value=[])
        llm.synthesize_findings = AsyncMock(
            return_value=MagicMock(
                status="completed",
                root_cause="Test cause",
                confidence=0.9,
                recommendations=[],
            )
        )
        return llm

    @pytest.fixture
    def mock_context_engine(self) -> MagicMock:
        """Create mock context engine."""
        engine = MagicMock()
        schema = MagicMock()
        schema.is_empty.return_value = False
        schema.table_count.return_value = 5
        engine.gather = AsyncMock(return_value=MagicMock(schema=schema, lineage=None))
        return engine

    @pytest.fixture
    def mock_circuit_breaker(self) -> MagicMock:
        """Create mock circuit breaker."""
        cb = MagicMock()
        cb.check = MagicMock()
        return cb

    @pytest.fixture
    def mock_adapter(self) -> MagicMock:
        """Create mock SQL adapter."""
        adapter = MagicMock()
        adapter.execute_query = AsyncMock()
        return adapter

    @pytest.fixture
    def orchestrator(
        self,
        mock_llm: MagicMock,
        mock_context_engine: MagicMock,
        mock_circuit_breaker: MagicMock,
        mock_feedback: MagicMock,
    ) -> InvestigationOrchestrator:
        """Create orchestrator with mocks."""
        return InvestigationOrchestrator(
            db=None,
            llm=mock_llm,
            context_engine=mock_context_engine,
            circuit_breaker=mock_circuit_breaker,
            feedback=mock_feedback,
            config=OrchestratorConfig(),
        )

    @pytest.fixture
    def alert(self) -> AnomalyAlert:
        """Create test alert."""
        return AnomalyAlert(
            dataset_id="public.orders",
            metric_name="null_rate",
            expected_value=0.01,
            actual_value=0.15,
            deviation_pct=1400.0,
            anomaly_date="2024-01-15",
            severity="high",
        )

    @pytest.fixture
    def state(self, alert: AnomalyAlert) -> InvestigationState:
        """Create test state."""
        return InvestigationState(
            id=str(uuid4()),
            tenant_id=uuid4(),
            alert=alert,
        )

    async def test_emits_investigation_started(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_feedback: MagicMock,
        mock_adapter: MagicMock,
    ) -> None:
        """Orchestrator emits investigation.started event."""
        await orchestrator.run_investigation(state, data_adapter=mock_adapter)

        # Find the investigation.started call with dataset_id
        calls = mock_feedback.emit.call_args_list
        started_calls = [
            c
            for c in calls
            if c.kwargs.get("event_type") == EventType.INVESTIGATION_STARTED
            and "dataset_id" in c.kwargs.get("event_data", {})
        ]

        assert len(started_calls) == 1
        assert started_calls[0].kwargs["tenant_id"] == state.tenant_id

    async def test_emits_investigation_completed(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_feedback: MagicMock,
        mock_adapter: MagicMock,
    ) -> None:
        """Orchestrator emits investigation.completed event."""
        await orchestrator.run_investigation(state, data_adapter=mock_adapter)

        calls = mock_feedback.emit.call_args_list
        completed_calls = [
            c for c in calls if c.kwargs.get("event_type") == EventType.INVESTIGATION_COMPLETED
        ]

        assert len(completed_calls) == 1

    async def test_emits_context_gathered(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_feedback: MagicMock,
        mock_adapter: MagicMock,
    ) -> None:
        """Orchestrator emits context.gathered event."""
        await orchestrator.run_investigation(state, data_adapter=mock_adapter)

        calls = mock_feedback.emit.call_args_list
        # Look for a context-related event in event_data
        context_calls = [c for c in calls if "tables_found" in c.kwargs.get("event_data", {})]

        assert len(context_calls) >= 1
