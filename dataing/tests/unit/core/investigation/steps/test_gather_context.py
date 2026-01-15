"""Tests for GatherContextStep."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from maestro import Signal

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.gather_context import GatherContextStep
from dataing.core.investigation.values import StepType


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
    """Create context with alert summary and alert data."""
    return InvestigationContext(
        alert_summary=f"{sample_alert.anomaly_type} in {sample_alert.dataset_id}",
        alert=sample_alert.model_dump(mode="json"),
    )


@pytest.fixture
def mock_adapter() -> AsyncMock:
    """Create mock database adapter."""
    return AsyncMock()


@pytest.fixture
def mock_context_engine() -> AsyncMock:
    """Create mock context engine."""
    engine = AsyncMock()
    engine.gather.return_value = MagicMock(
        schema=MagicMock(
            model_dump=MagicMock(
                return_value={
                    "catalogs": [
                        {
                            "name": "default",
                            "schemas": [
                                {"name": "public", "tables": ["events", "users", "orders"]}
                            ],
                        }
                    ]
                }
            ),
        ),
        lineage=MagicMock(
            target="analytics.events",
            upstream=["raw.events"],
            downstream=[],
        ),
    )
    return engine


class TestGatherContextStep:
    """Tests for GatherContextStep."""

    def test_step_type(self, mock_adapter: AsyncMock) -> None:
        """Step has correct type."""
        step = GatherContextStep(context_engine=AsyncMock(), adapter=mock_adapter)
        assert step.step_type == StepType.GATHER_CONTEXT

    async def test_execute_gathers_schema(
        self,
        sample_context: InvestigationContext,
        mock_context_engine: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        """Execute gathers schema from context engine."""
        step = GatherContextStep(context_engine=mock_context_engine, adapter=mock_adapter)

        result = await step.execute(sample_context)

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.CHECK_PATTERNS.value
        assert result.context.schema_info is not None
        # Check we have the expected schema structure
        assert "catalogs" in result.context.schema_info

    async def test_execute_gathers_lineage(
        self,
        sample_context: InvestigationContext,
        mock_context_engine: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        """Execute gathers lineage from context engine."""
        step = GatherContextStep(context_engine=mock_context_engine, adapter=mock_adapter)

        result = await step.execute(sample_context)

        assert result.context.lineage_info is not None
        assert result.context.lineage_info["upstream"] == ["raw.events"]

    async def test_execute_fails_on_empty_schema(
        self,
        sample_context: InvestigationContext,
        mock_adapter: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when schema is empty."""
        engine = AsyncMock()
        engine.gather.return_value = MagicMock(
            schema=MagicMock(
                model_dump=MagicMock(
                    return_value={"catalogs": [{"schemas": [{"tables": []}]}]}
                ),
            ),
        )
        step = GatherContextStep(context_engine=engine, adapter=mock_adapter)

        result = await step.execute(sample_context)

        assert result.signal == Signal.FAIL
        assert "empty schema" in str(result.error).lower()

    async def test_execute_handles_context_engine_error(
        self,
        sample_context: InvestigationContext,
        mock_adapter: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when context engine raises exception."""
        engine = AsyncMock()
        engine.gather.side_effect = Exception("Connection failed")
        step = GatherContextStep(context_engine=engine, adapter=mock_adapter)

        result = await step.execute(sample_context)

        assert result.signal == Signal.FAIL
        assert "Connection failed" in str(result.error)

    async def test_execute_handles_none_lineage(
        self,
        sample_context: InvestigationContext,
        mock_adapter: AsyncMock,
    ) -> None:
        """Execute handles case where lineage is None."""
        engine = AsyncMock()
        engine.gather.return_value = MagicMock(
            schema=MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "catalogs": [
                            {
                                "name": "default",
                                "schemas": [{"name": "public", "tables": ["events"]}],
                            }
                        ]
                    }
                ),
            ),
            lineage=None,
        )
        step = GatherContextStep(context_engine=engine, adapter=mock_adapter)

        result = await step.execute(sample_context)

        assert result.signal == Signal.CONTINUE
        assert result.context.lineage_info is None
        assert result.context.schema_info is not None
