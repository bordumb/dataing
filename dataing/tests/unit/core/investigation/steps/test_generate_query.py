"""Tests for GenerateQueryStep."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from maestro import Signal

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.generate_query import GenerateQueryStep
from dataing.core.investigation.values import StepType


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create context with schema info."""
    return InvestigationContext(
        alert_summary="NULL rate spike in analytics.events",
        schema_info={"tables": ["events", "users"]},
    )


@pytest.fixture
def sample_hypothesis() -> dict[str, Any]:
    """Create sample hypothesis dict (as stored in step_cursor)."""
    return {
        "id": "h1",
        "title": "Upstream ETL failure",
        "category": "upstream_dependency",
        "reasoning": "ETL job may have failed causing NULL values",
        "suggested_query": "SELECT * FROM events WHERE user_id IS NULL",
    }


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Create mock LLM client."""
    llm = AsyncMock()
    llm.generate_query.return_value = "SELECT COUNT(*) FROM events WHERE user_id IS NULL"
    return llm


class TestGenerateQueryStep:
    """Tests for GenerateQueryStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = GenerateQueryStep(llm=AsyncMock())
        assert step.step_type == StepType.GENERATE_QUERY

    def test_can_execute_requires_schema(self) -> None:
        """can_execute returns False if no schema info."""
        step = GenerateQueryStep(llm=AsyncMock())
        context_no_schema = InvestigationContext(alert_summary="Test")
        context_with_schema = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
        )

        assert step.can_execute(context_no_schema) is False
        assert step.can_execute(context_with_schema) is True

    @pytest.mark.asyncio
    async def test_execute_generates_query(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute generates SQL query via LLM."""
        step = GenerateQueryStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        # Verify LLM was called with correct parameters
        mock_llm.generate_query.assert_called_once_with(
            hypothesis=sample_hypothesis,
            schema_info=sample_context.schema_info,
            alert_summary=sample_context.alert_summary,
            alert=sample_context.alert,
        )
        # Verify output is the generated query
        assert result.output == "SELECT COUNT(*) FROM events WHERE user_id IS NULL"

    @pytest.mark.asyncio
    async def test_execute_returns_continue_signal(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns CONTINUE signal."""
        step = GenerateQueryStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert result.signal == Signal.CONTINUE

    @pytest.mark.asyncio
    async def test_execute_sets_next_step_execute_query(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute sets next_step to EXECUTE_QUERY."""
        step = GenerateQueryStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert result.next_step == StepType.EXECUTE_QUERY

    @pytest.mark.asyncio
    async def test_execute_fails_without_hypothesis(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when no hypothesis provided."""
        step = GenerateQueryStep(llm=mock_llm)

        # No input_data (hypothesis missing)
        result = await step.execute(sample_context, None)

        assert result.signal == Signal.FAIL
        # LLM should not be called
        mock_llm.generate_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_fails_with_empty_input(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when input_data has no hypothesis key."""
        step = GenerateQueryStep(llm=mock_llm)
        input_data: dict[str, Any] = {}

        result = await step.execute(sample_context, input_data)

        assert result.signal == Signal.FAIL
        mock_llm.generate_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_preserves_context(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute preserves the existing context."""
        step = GenerateQueryStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        # Context should be preserved (same alert_summary, schema_info)
        assert result.context.alert_summary == sample_context.alert_summary
        assert result.context.schema_info == sample_context.schema_info

    @pytest.mark.asyncio
    async def test_execute_sets_current_query_in_context(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
        mock_llm: AsyncMock,
    ) -> None:
        """Execute sets current_query in the updated context."""
        step = GenerateQueryStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        # Context should have current_query set
        assert result.context.current_query == result.output
        assert result.context.current_query == ("SELECT COUNT(*) FROM events WHERE user_id IS NULL")

    @pytest.mark.asyncio
    async def test_execute_handles_llm_error(
        self,
        sample_context: InvestigationContext,
        sample_hypothesis: dict[str, Any],
    ) -> None:
        """Execute returns FAIL signal when LLM raises an error."""
        mock_llm = AsyncMock()
        mock_llm.generate_query.side_effect = Exception("LLM API error")
        step = GenerateQueryStep(llm=mock_llm)
        input_data = {"hypothesis": sample_hypothesis}

        result = await step.execute(sample_context, input_data)

        assert result.signal == Signal.FAIL
