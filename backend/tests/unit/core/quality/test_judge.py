"""Tests for LLM-as-judge quality validator."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dataing.adapters.llm.response_models import InterpretationResponse, SynthesisResponse
from dataing.core.quality.assessment import QualityAssessment
from dataing.core.quality.judge import LLMJudgeValidator


class TestLLMJudgeValidator:
    """Tests for LLMJudgeValidator."""

    @pytest.fixture
    def mock_judge_agent(self) -> MagicMock:
        """Create a mock judge agent."""
        agent = MagicMock()
        agent.run = AsyncMock()
        return agent

    @pytest.fixture
    def validator(self, mock_judge_agent: MagicMock) -> LLMJudgeValidator:
        """Create validator with mocked agent."""
        validator = LLMJudgeValidator.__new__(LLMJudgeValidator)
        validator.pass_threshold = 0.6
        validator.judge = mock_judge_agent
        return validator

    @pytest.mark.asyncio
    async def test_validate_interpretation_passes(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test interpretation validation passes when score is above threshold."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.8,
                specificity=0.7,
                actionability=0.6,
                lowest_dimension="actionability",
                improvement_suggestion="Could include more specific action items",
            )
        )

        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation=(
                "The 485 orphaned orders appeared after 03:14 UTC when users table stopped."
            ),
            causal_chain="users ETL stopped -> stale table -> JOIN NULLs",
            key_findings=["485 orders affected"],
        )

        result = await validator.validate_interpretation(
            response=response,
            hypothesis_title="Users ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is True
        assert result.assessment.causal_depth == 0.8

    @pytest.mark.asyncio
    async def test_validate_interpretation_fails(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test interpretation validation fails when score is below threshold."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.3,
                specificity=0.4,
                actionability=0.2,
                lowest_dimension="causal_depth",
                improvement_suggestion="Explain the causal chain from cause to effect",
            )
        )

        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation="The query confirms there are NULL values in the user_id column.",
            causal_chain="NULLs exist in the data, source unknown",
            key_findings=["NULLs found"],
        )

        result = await validator.validate_interpretation(
            response=response,
            hypothesis_title="Users ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is False
        assert result.assessment.lowest_dimension == "causal_depth"

    @pytest.mark.asyncio
    async def test_validate_synthesis_passes(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test synthesis validation passes with good quality."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.9,
                specificity=0.8,
                actionability=0.7,
                lowest_dimension="actionability",
                improvement_suggestion="Could add exact command syntax",
            )
        )

        response = SynthesisResponse(
            root_cause="Users ETL job timed out at 03:14 UTC due to API rate limiting",
            confidence=0.85,
            causal_chain=["API rate limit", "ETL timeout", "stale table", "JOIN NULLs"],
            estimated_onset="03:14 UTC",
            affected_scope="orders table and downstream reports",
            supporting_evidence=["485 NULLs", "Last update 03:14"],
            recommendations=["Re-run stg_users with backfill"],
        )

        result = await validator.validate_synthesis(
            response=response,
            alert_summary="null_count on orders.user_id: expected 0, got 485",
        )

        assert result.passed is True
        assert result.assessment.composite_score > 0.6

    @pytest.mark.asyncio
    async def test_training_signals_captured(
        self, validator: LLMJudgeValidator, mock_judge_agent: MagicMock
    ) -> None:
        """Test that training signals are properly captured."""
        mock_judge_agent.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.7,
                specificity=0.6,
                actionability=0.5,
                lowest_dimension="actionability",
                improvement_suggestion="Add specific commands",
            )
        )

        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.8,
            interpretation=(
                "The data shows a clear pattern of NULLs appearing after the ETL failure."
            ),
            causal_chain="ETL failure -> missing data -> NULLs",
            key_findings=["Pattern detected"],
        )

        result = await validator.validate_interpretation(
            response=response,
            hypothesis_title="Test",
            query="SELECT 1 LIMIT 1",
        )

        signals = result.training_signals
        assert "causal_depth" in signals
        assert "specificity" in signals
        assert "actionability" in signals
        assert "composite" in signals
