"""Tests for GatherContextStep."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.gather_context import GatherContextStep
from maestro import Signal, StepType


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create sample alert."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec.from_column("user_id", "NULL rate"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        anomaly_date="2026-01-10",
        severity="high",
    )


@pytest.fixture
def sample_context(sample_alert: AnomalyAlert) -> InvestigationContext:
    """Create context with alert summary."""
    return InvestigationContext(
        alert_summary=f"{sample_alert.anomaly_type} in {sample_alert.dataset_id}"
    )


@pytest.fixture
def mock_context_engine() -> AsyncMock:
    """Create mock context engine."""
    engine = AsyncMock()
    engine.gather.return_value = MagicMock(
        schema=MagicMock(
            is_empty=MagicMock(return_value=False),
            table_count=MagicMock(return_value=3),
            to_dict=MagicMock(return_value={"tables": ["events", "users", "orders"]}),
        ),
        lineage=MagicMock(to_dict=MagicMock(return_value={"upstream": ["raw.events"]})),
    )
    return engine


class TestGatherContextStep:
    """Tests for GatherContextStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = GatherContextStep(context_engine=AsyncMock())
        assert step.step_type == StepType.GATHER_CONTEXT

    @pytest.mark.asyncio
    async def test_execute_gathers_schema(
        self,
        sample_context: InvestigationContext,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Execute gathers schema from context engine."""
        step = GatherContextStep(context_engine=mock_context_engine)

        result = await step.execute(sample_context)

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.CHECK_PATTERNS
        assert result.context.schema_info is not None
        assert result.context.schema_info["tables"] == ["events", "users", "orders"]

    @pytest.mark.asyncio
    async def test_execute_gathers_lineage(
        self,
        sample_context: InvestigationContext,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Execute gathers lineage from context engine."""
        step = GatherContextStep(context_engine=mock_context_engine)

        result = await step.execute(sample_context)

        assert result.context.lineage_info is not None
        assert result.context.lineage_info["upstream"] == ["raw.events"]

    @pytest.mark.asyncio
    async def test_execute_fails_on_empty_schema(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute returns FAIL signal when schema is empty."""
        engine = AsyncMock()
        engine.gather.return_value = MagicMock(
            schema=MagicMock(
                is_empty=MagicMock(return_value=True),
            ),
        )
        step = GatherContextStep(context_engine=engine)

        result = await step.execute(sample_context)

        assert result.signal == Signal.FAIL
        assert "empty schema" in str(result.output).lower()

    @pytest.mark.asyncio
    async def test_execute_handles_context_engine_error(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute returns FAIL signal when context engine raises exception."""
        engine = AsyncMock()
        engine.gather.side_effect = Exception("Connection failed")
        step = GatherContextStep(context_engine=engine)

        result = await step.execute(sample_context)

        assert result.signal == Signal.FAIL
        assert "Connection failed" in str(result.output)

    @pytest.mark.asyncio
    async def test_execute_handles_none_lineage(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute handles case where lineage is None."""
        engine = AsyncMock()
        engine.gather.return_value = MagicMock(
            schema=MagicMock(
                is_empty=MagicMock(return_value=False),
                to_dict=MagicMock(return_value={"tables": ["events"]}),
            ),
            lineage=None,
        )
        step = GatherContextStep(context_engine=engine)

        result = await step.execute(sample_context)

        assert result.signal == Signal.CONTINUE
        assert result.context.lineage_info is None
        assert result.context.schema_info is not None
