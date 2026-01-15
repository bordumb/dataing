"""Tests for GenerateHypothesesStep."""

from unittest.mock import AsyncMock

import pytest
from maestro import Signal

from dataing.core.domain_types import Hypothesis, HypothesisCategory
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.generate_hypotheses import GenerateHypothesesStep
from dataing.core.investigation.values import BranchType, StepType


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create context with schema info."""
    return InvestigationContext(
        alert_summary="NULL rate spike in analytics.events",
        schema_info={"tables": ["events", "users"]},
    )


@pytest.fixture
def sample_hypotheses() -> list[Hypothesis]:
    """Create sample hypotheses."""
    return [
        Hypothesis(
            id="h1",
            title="Upstream ETL failure",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="ETL job may have failed",
            suggested_query="SELECT * FROM events WHERE user_id IS NULL",
        ),
        Hypothesis(
            id="h2",
            title="Mobile app bug",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Mobile app may not be sending user_id",
            suggested_query="SELECT platform, COUNT(*) FROM events GROUP BY platform",
        ),
    ]


@pytest.fixture
def mock_llm(sample_hypotheses: list[Hypothesis]) -> AsyncMock:
    """Create mock LLM client."""
    llm = AsyncMock()
    llm.generate_hypotheses.return_value = sample_hypotheses
    return llm


class TestGenerateHypothesesStep:
    """Tests for GenerateHypothesesStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = GenerateHypothesesStep(llm=AsyncMock())
        assert step.step_type == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_execute_generates_hypotheses(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Execute generates hypotheses via LLM."""
        step = GenerateHypothesesStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.signal == Signal.BRANCH
        assert result.branch_request is not None
        assert len(result.branch_request.branches) == 2

    @pytest.mark.asyncio
    async def test_execute_returns_branch_request(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns BRANCH signal with branch request."""
        step = GenerateHypothesesStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.signal == Signal.BRANCH
        assert result.branch_request is not None
        assert result.branch_request.branch_type == BranchType.HYPOTHESIS
        assert result.branch_request.merge_step == StepType.SYNTHESIZE
        assert result.branch_request.child_start_step == StepType.GENERATE_QUERY

    @pytest.mark.asyncio
    async def test_execute_updates_context_with_hypotheses(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Execute adds hypotheses to context."""
        step = GenerateHypothesesStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert len(result.context.hypotheses) == 2
        assert result.context.hypotheses[0]["id"] == "h1"

    @pytest.mark.asyncio
    async def test_execute_includes_pattern_hints(
        self,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute passes pattern hints to LLM."""
        context = InvestigationContext(
            alert_summary="NULL rate spike",
            schema_info={"tables": ["events"]},
            matched_patterns=[{"name": "ETL failure pattern", "description": "Common ETL issue"}],
        )
        step = GenerateHypothesesStep(llm=mock_llm)

        await step.execute(context)

        # Verify LLM was called with pattern hints
        call_kwargs = mock_llm.generate_hypotheses.call_args.kwargs
        assert "pattern_hints" in call_kwargs
        assert len(call_kwargs["pattern_hints"]) == 1

    def test_can_execute_requires_schema(self) -> None:
        """can_execute returns False if no schema info."""
        step = GenerateHypothesesStep(llm=AsyncMock())
        context_no_schema = InvestigationContext(alert_summary="Test")
        context_with_schema = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
        )

        assert step.can_execute(context_no_schema) is False
        assert step.can_execute(context_with_schema) is True
