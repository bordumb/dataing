"""Tests for SynthesizeStep."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.synthesize import SynthesizeStep
from dataing.core.investigation.values import StepType
from maestro import Signal


@pytest.fixture
def sample_hypotheses() -> list[dict[str, Any]]:
    """Create sample hypotheses that were investigated."""
    return [
        {
            "id": "h1",
            "title": "Upstream ETL failure",
            "category": "upstream_dependency",
            "reasoning": "ETL job may have failed causing NULL values",
        },
        {
            "id": "h2",
            "title": "Mobile app bug",
            "category": "source_system",
            "reasoning": "Mobile app v2.3 may not be sending user_id",
        },
    ]


@pytest.fixture
def sample_evidence() -> list[dict[str, Any]]:
    """Create sample evidence from hypothesis investigations."""
    return [
        {
            "hypothesis_id": "h1",
            "supports_hypothesis": False,
            "confidence": 0.2,
            "interpretation": "ETL job ran successfully, no failures detected.",
            "query": "SELECT * FROM etl_logs WHERE status = 'failed'",
            "result_summary": "0 rows",
            "row_count": 0,
        },
        {
            "hypothesis_id": "h2",
            "supports_hypothesis": True,
            "confidence": 0.9,
            "interpretation": "Mobile app v2.3 is the source of NULL user_ids.",
            "query": "SELECT app_version, COUNT(*) FROM events WHERE user_id IS NULL",
            "result_summary": "v2.3: 1234 rows",
            "row_count": 1,
        },
    ]


@pytest.fixture
def sample_context(
    sample_hypotheses: list[dict[str, Any]],
    sample_evidence: list[dict[str, Any]],
) -> InvestigationContext:
    """Create context with evidence ready for synthesis."""
    return InvestigationContext(
        alert_summary="NULL rate spike in analytics.events",
        schema_info={"tables": ["events", "users"]},
        hypotheses=sample_hypotheses,
        evidence=sample_evidence,
    )


@pytest.fixture
def high_confidence_synthesis() -> dict[str, Any]:
    """Create high confidence synthesis result."""
    return {
        "root_cause": "Mobile app v2.3 has a bug that fails to send user_id field.",
        "confidence": 0.92,
        "recommendations": [
            "Roll back mobile app to v2.2",
            "Fix user_id serialization in mobile SDK",
            "Add client-side validation for required fields",
        ],
        "supporting_evidence": [
            "Evidence from h2 shows v2.3 is the source of NULL values",
            "ETL jobs ran successfully, ruling out upstream issues",
        ],
    }


@pytest.fixture
def low_confidence_synthesis() -> dict[str, Any]:
    """Create low confidence synthesis result."""
    return {
        "root_cause": "Possible mobile app bug, but insufficient evidence.",
        "confidence": 0.6,
        "recommendations": [
            "Gather more evidence about mobile app behavior",
            "Check server-side logs for additional context",
        ],
        "supporting_evidence": [
            "Some evidence points to mobile app",
        ],
    }


@pytest.fixture
def mock_llm(high_confidence_synthesis: dict[str, Any]) -> AsyncMock:
    """Create mock LLM client that returns high confidence synthesis."""
    llm = AsyncMock()
    llm.synthesize_findings.return_value = high_confidence_synthesis
    return llm


class TestSynthesizeStep:
    """Tests for SynthesizeStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = SynthesizeStep(llm=AsyncMock())
        assert step.step_type == StepType.SYNTHESIZE

    def test_can_execute_requires_evidence(self) -> None:
        """can_execute returns False if no evidence in context."""
        step = SynthesizeStep(llm=AsyncMock())
        context_no_evidence = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
            evidence=[],
        )
        context_with_evidence = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
            evidence=[{"hypothesis_id": "h1", "supports_hypothesis": True}],
        )

        assert step.can_execute(context_no_evidence) is False
        assert step.can_execute(context_with_evidence) is True

    @pytest.mark.asyncio
    async def test_execute_synthesizes_findings(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute synthesizes evidence via LLM."""
        step = SynthesizeStep(llm=mock_llm)

        await step.execute(sample_context)

        # Verify LLM was called with correct parameters
        mock_llm.synthesize_findings.assert_called_once_with(
            evidence=sample_context.evidence,
            hypotheses=sample_context.hypotheses,
            alert_summary=sample_context.alert_summary,
        )

    @pytest.mark.asyncio
    async def test_execute_returns_complete_on_high_confidence(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns COMPLETE signal when confidence >= threshold."""
        step = SynthesizeStep(llm=mock_llm, confidence_threshold=0.85)

        result = await step.execute(sample_context)

        assert result.signal == Signal.COMPLETE

    @pytest.mark.asyncio
    async def test_execute_returns_continue_on_low_confidence(
        self,
        sample_context: InvestigationContext,
        low_confidence_synthesis: dict[str, Any],
    ) -> None:
        """Execute returns CONTINUE signal with next_step=COUNTER_ANALYZE on low confidence."""
        mock_llm = AsyncMock()
        mock_llm.synthesize_findings.return_value = low_confidence_synthesis
        step = SynthesizeStep(llm=mock_llm, confidence_threshold=0.85)

        result = await step.execute(sample_context)

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.COUNTER_ANALYZE

    @pytest.mark.asyncio
    async def test_execute_sets_current_synthesis_in_context(
        self,
        sample_context: InvestigationContext,
        high_confidence_synthesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute sets current_synthesis in context."""
        step = SynthesizeStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.context.current_synthesis == high_confidence_synthesis

    @pytest.mark.asyncio
    async def test_execute_returns_synthesis_as_output(
        self,
        sample_context: InvestigationContext,
        high_confidence_synthesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns synthesis dict as output."""
        step = SynthesizeStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.output == high_confidence_synthesis

    @pytest.mark.asyncio
    async def test_execute_handles_llm_error(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute returns FAIL signal when LLM raises an error."""
        mock_llm = AsyncMock()
        mock_llm.synthesize_findings.side_effect = Exception("LLM API error")
        step = SynthesizeStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.signal == Signal.FAIL

    @pytest.mark.asyncio
    async def test_execute_preserves_context_fields(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute preserves other context fields."""
        step = SynthesizeStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.context.alert_summary == sample_context.alert_summary
        assert result.context.schema_info == sample_context.schema_info
        assert result.context.hypotheses == sample_context.hypotheses
        assert result.context.evidence == sample_context.evidence

    @pytest.mark.asyncio
    async def test_execute_uses_custom_threshold(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute respects custom confidence threshold."""
        # Synthesis with 0.75 confidence
        synthesis_75 = {
            "root_cause": "Some root cause",
            "confidence": 0.75,
            "recommendations": [],
            "supporting_evidence": [],
        }
        mock_llm = AsyncMock()
        mock_llm.synthesize_findings.return_value = synthesis_75

        # With threshold 0.70, should be COMPLETE
        step_low_threshold = SynthesizeStep(llm=mock_llm, confidence_threshold=0.70)
        result_low = await step_low_threshold.execute(sample_context)
        assert result_low.signal == Signal.COMPLETE

        # With threshold 0.80, should be CONTINUE
        step_high_threshold = SynthesizeStep(llm=mock_llm, confidence_threshold=0.80)
        result_high = await step_high_threshold.execute(sample_context)
        assert result_high.signal == Signal.CONTINUE
        assert result_high.next_step == StepType.COUNTER_ANALYZE

    @pytest.mark.asyncio
    async def test_execute_handles_missing_confidence(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute defaults to CONTINUE when synthesis has no confidence field."""
        synthesis_no_confidence: dict[str, Any] = {
            "root_cause": "Some root cause",
            "recommendations": [],
            "supporting_evidence": [],
        }
        mock_llm = AsyncMock()
        mock_llm.synthesize_findings.return_value = synthesis_no_confidence
        step = SynthesizeStep(llm=mock_llm)

        result = await step.execute(sample_context)

        # Missing confidence should default to 0, triggering CONTINUE
        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.COUNTER_ANALYZE
