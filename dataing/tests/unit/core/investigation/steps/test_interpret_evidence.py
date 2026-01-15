"""Tests for InterpretEvidenceStep."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from maestro import Signal

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.interpret_evidence import InterpretEvidenceStep
from dataing.core.investigation.values import StepType


@pytest.fixture
def sample_hypothesis() -> dict[str, Any]:
    """Create sample hypothesis dict (as stored in step_cursor)."""
    return {
        "id": "h1",
        "title": "Upstream ETL failure",
        "category": "upstream_dependency",
        "reasoning": "ETL job may have failed causing NULL values",
    }


@pytest.fixture
def sample_query_result() -> dict[str, Any]:
    """Create sample query result from database."""
    return {
        "columns": ("count",),
        "rows": ({"count": 1234},),
        "row_count": 1,
    }


@pytest.fixture
def sample_context(
    sample_hypothesis: dict[str, Any],
    sample_query_result: dict[str, Any],
) -> InvestigationContext:
    """Create context with query result ready for interpretation."""
    return InvestigationContext(
        alert_summary="NULL rate spike in analytics.events",
        schema_info={"tables": ["events", "users"]},
        current_query="SELECT COUNT(*) FROM events WHERE user_id IS NULL",
        current_query_result=sample_query_result,
        hypotheses=[sample_hypothesis],
    )


@pytest.fixture
def sample_evidence() -> dict[str, Any]:
    """Create sample evidence returned by LLM."""
    return {
        "hypothesis_id": "h1",
        "supports_hypothesis": True,
        "confidence": 0.85,
        "interpretation": "Query found 1234 NULL user_id records, confirming the hypothesis.",
        "query": "SELECT COUNT(*) FROM events WHERE user_id IS NULL",
        "result_summary": "count: 1234",
        "row_count": 1,
    }


@pytest.fixture
def mock_llm(sample_evidence: dict[str, Any]) -> AsyncMock:
    """Create mock LLM client."""
    llm = AsyncMock()
    llm.interpret_evidence.return_value = sample_evidence
    return llm


class TestInterpretEvidenceStep:
    """Tests for InterpretEvidenceStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = InterpretEvidenceStep(llm=AsyncMock())
        assert step.step_type == StepType.INTERPRET_EVIDENCE

    def test_can_execute_requires_query_result(self) -> None:
        """can_execute returns False if no current_query_result in context."""
        step = InterpretEvidenceStep(llm=AsyncMock())
        context_no_result = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
            current_query="SELECT 1",
            current_query_result=None,
        )
        context_with_result = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
            current_query="SELECT 1",
            current_query_result={"columns": ("x",), "rows": [], "row_count": 0},
        )

        assert step.can_execute(context_no_result) is False
        assert step.can_execute(context_with_result) is True

    @pytest.mark.asyncio
    async def test_execute_interprets_evidence(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute interprets query results via LLM."""
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        await step.execute(sample_context, input_data)

        # Verify LLM was called with correct parameters
        mock_llm.interpret_evidence.assert_called_once_with(
            hypothesis=sample_hypothesis,
            query_result=sample_context.current_query_result,
            alert_summary=sample_context.alert_summary,
        )

    @pytest.mark.asyncio
    async def test_execute_returns_complete_signal(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns COMPLETE signal (hypothesis branch ends here)."""
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert result.signal == Signal.COMPLETE

    @pytest.mark.asyncio
    async def test_execute_adds_evidence_to_context(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        sample_evidence: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute adds evidence to context.evidence list."""
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert len(result.context.evidence) == 1
        assert result.context.evidence[0] == sample_evidence

    @pytest.mark.asyncio
    async def test_execute_appends_to_existing_evidence(
        self,
        sample_hypothesis: dict[str, Any],
        sample_query_result: dict[str, Any],
        sample_evidence: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute appends new evidence to existing evidence list."""
        existing_evidence = {
            "hypothesis_id": "h0",
            "supports_hypothesis": False,
            "confidence": 0.6,
            "interpretation": "Previous evidence",
        }
        context_with_evidence = InvestigationContext(
            alert_summary="NULL rate spike in analytics.events",
            schema_info={"tables": ["events", "users"]},
            current_query="SELECT COUNT(*) FROM events WHERE user_id IS NULL",
            current_query_result=sample_query_result,
            hypotheses=[sample_hypothesis],
            evidence=[existing_evidence],
        )
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(context_with_evidence, input_data)

        assert len(result.context.evidence) == 2
        assert result.context.evidence[0] == existing_evidence
        assert result.context.evidence[1] == sample_evidence

    @pytest.mark.asyncio
    async def test_execute_returns_evidence_as_output(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        sample_evidence: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns evidence dict as output."""
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert result.output == sample_evidence

    @pytest.mark.asyncio
    async def test_execute_preserves_context_fields(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute preserves other context fields."""
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert result.context.alert_summary == sample_context.alert_summary
        assert result.context.schema_info == sample_context.schema_info
        assert result.context.current_query == sample_context.current_query
        assert result.context.current_query_result == sample_context.current_query_result

    @pytest.mark.asyncio
    async def test_execute_fails_without_hypothesis(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when no hypothesis provided."""
        step = InterpretEvidenceStep(llm=mock_llm)

        # No input_data (hypothesis missing)
        result = await step.execute(sample_context, None)

        assert result.signal == Signal.FAIL
        mock_llm.interpret_evidence.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_fails_with_empty_input(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when input_data has no hypothesis key."""
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data: dict[str, Any] = {}

        result = await step.execute(sample_context, input_data)

        assert result.signal == Signal.FAIL
        mock_llm.interpret_evidence.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_fails_without_query_result(
        self,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when no current_query_result in context."""
        context_no_result = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
            current_query="SELECT 1",
            current_query_result=None,
        )
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(context_no_result, input_data)

        assert result.signal == Signal.FAIL
        mock_llm.interpret_evidence.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_handles_llm_error(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
    ) -> None:
        """Execute returns FAIL signal when LLM raises an error."""
        mock_llm = AsyncMock()
        mock_llm.interpret_evidence.side_effect = Exception("LLM API error")
        step = InterpretEvidenceStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert result.signal == Signal.FAIL
