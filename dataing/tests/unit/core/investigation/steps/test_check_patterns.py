"""Tests for CheckPatternsStep."""

from unittest.mock import AsyncMock

import pytest

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.check_patterns import CheckPatternsStep
from dataing.core.investigation.values import StepType
from maistro import Signal


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample investigation context."""
    return InvestigationContext(
        alert_summary="null_rate anomaly in analytics.events: user_id NULL rate 15% (expected 1%)",
        schema_info={"tables": ["events", "users", "orders"]},
        lineage_info={"upstream": ["raw.events"]},
    )


@pytest.fixture
def sample_patterns() -> list[dict[str, object]]:
    """Create sample matched patterns."""
    return [
        {
            "id": "pattern-001",
            "name": "Mobile SDK NULL User ID",
            "description": "Mobile SDK versions < 2.0 send NULL user_id on first launch",
            "typical_root_cause": "Mobile app not waiting for auth before tracking events",
            "confidence": 0.92,
        },
        {
            "id": "pattern-002",
            "name": "Session Timeout NULL User",
            "description": "Server-side session timeouts cause NULL user_id in events",
            "typical_root_cause": "Session expiry not properly handled by tracking code",
            "confidence": 0.85,
        },
    ]


@pytest.fixture
def mock_pattern_repository(
    sample_patterns: list[dict[str, object]],
) -> AsyncMock:
    """Create mock pattern repository."""
    repo = AsyncMock()
    repo.find_matching_patterns.return_value = sample_patterns
    return repo


class TestCheckPatternsStep:
    """Tests for CheckPatternsStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = CheckPatternsStep(pattern_repository=AsyncMock())
        assert step.step_type == StepType.CHECK_PATTERNS

    def test_can_execute_always_true(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Step can always execute (even without schema)."""
        step = CheckPatternsStep(pattern_repository=AsyncMock())

        # With full context
        assert step.can_execute(sample_context) is True

        # Without schema
        context_no_schema = InvestigationContext(
            alert_summary="anomaly detected",
            schema_info=None,
        )
        assert step.can_execute(context_no_schema) is True

    @pytest.mark.asyncio
    async def test_execute_finds_patterns(
        self,
        sample_context: InvestigationContext,
        mock_pattern_repository: AsyncMock,
        sample_patterns: list[dict[str, object]],
    ) -> None:
        """Execute queries pattern repository and returns matches."""
        step = CheckPatternsStep(pattern_repository=mock_pattern_repository)

        result = await step.execute(sample_context)

        mock_pattern_repository.find_matching_patterns.assert_called_once()
        assert result.output == sample_patterns

    @pytest.mark.asyncio
    async def test_execute_returns_continue_signal(
        self,
        sample_context: InvestigationContext,
        mock_pattern_repository: AsyncMock,
    ) -> None:
        """Execute returns CONTINUE signal."""
        step = CheckPatternsStep(pattern_repository=mock_pattern_repository)

        result = await step.execute(sample_context)

        assert result.signal == Signal.CONTINUE

    @pytest.mark.asyncio
    async def test_execute_sets_next_step_generate_hypotheses(
        self,
        sample_context: InvestigationContext,
        mock_pattern_repository: AsyncMock,
    ) -> None:
        """Execute sets next_step to GENERATE_HYPOTHESES."""
        step = CheckPatternsStep(pattern_repository=mock_pattern_repository)

        result = await step.execute(sample_context)

        assert result.next_step == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_execute_sets_matched_patterns_in_context(
        self,
        sample_context: InvestigationContext,
        mock_pattern_repository: AsyncMock,
        sample_patterns: list[dict[str, object]],
    ) -> None:
        """Execute sets matched_patterns in the updated context."""
        step = CheckPatternsStep(pattern_repository=mock_pattern_repository)

        result = await step.execute(sample_context)

        assert result.context.matched_patterns == sample_patterns

    @pytest.mark.asyncio
    async def test_execute_handles_no_patterns(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute handles case where no patterns match."""
        repo = AsyncMock()
        repo.find_matching_patterns.return_value = []
        step = CheckPatternsStep(pattern_repository=repo)

        result = await step.execute(sample_context)

        assert result.signal == Signal.CONTINUE
        assert result.output == []
        assert result.context.matched_patterns == []
        assert result.next_step == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_execute_handles_repository_error(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute handles pattern repository errors gracefully."""
        repo = AsyncMock()
        repo.find_matching_patterns.side_effect = Exception("Database connection failed")
        step = CheckPatternsStep(pattern_repository=repo)

        result = await step.execute(sample_context)

        # Should still continue (patterns are optional enrichment)
        assert result.signal == Signal.CONTINUE
        assert result.context.matched_patterns == []
        assert result.next_step == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_execute_extracts_dataset_from_alert(
        self,
        sample_context: InvestigationContext,
        mock_pattern_repository: AsyncMock,
    ) -> None:
        """Execute extracts dataset identifier from alert summary."""
        step = CheckPatternsStep(pattern_repository=mock_pattern_repository)

        await step.execute(sample_context)

        # Verify the call includes extracted dataset
        call_kwargs = mock_pattern_repository.find_matching_patterns.call_args.kwargs
        assert "dataset_id" in call_kwargs

    @pytest.mark.asyncio
    async def test_execute_passes_min_confidence(
        self,
        sample_context: InvestigationContext,
        mock_pattern_repository: AsyncMock,
    ) -> None:
        """Execute passes min_confidence threshold to repository."""
        step = CheckPatternsStep(pattern_repository=mock_pattern_repository)

        await step.execute(sample_context)

        call_kwargs = mock_pattern_repository.find_matching_patterns.call_args.kwargs
        assert call_kwargs.get("min_confidence") == 0.8

    @pytest.mark.asyncio
    async def test_execute_preserves_existing_context(
        self,
        mock_pattern_repository: AsyncMock,
        sample_patterns: list[dict[str, object]],
    ) -> None:
        """Execute preserves other context fields when updating."""
        context = InvestigationContext(
            alert_summary="test alert",
            schema_info={"tables": ["test_table"]},
            lineage_info={"upstream": ["source"]},
            hypotheses=[{"id": "h1", "text": "existing hypothesis"}],
            evidence=[{"id": "e1", "content": "existing evidence"}],
            total_tokens_used=100,
            total_queries_executed=5,
        )
        step = CheckPatternsStep(pattern_repository=mock_pattern_repository)

        result = await step.execute(context)

        assert result.context.alert_summary == context.alert_summary
        assert result.context.schema_info == context.schema_info
        assert result.context.lineage_info == context.lineage_info
        assert result.context.hypotheses == context.hypotheses
        assert result.context.evidence == context.evidence
        assert result.context.total_tokens_used == context.total_tokens_used
        assert result.context.total_queries_executed == context.total_queries_executed
        assert result.context.matched_patterns == sample_patterns
