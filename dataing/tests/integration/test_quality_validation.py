"""Integration tests for quality validation pipeline."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dataing.adapters.llm.response_models import InterpretationResponse
from dataing.core.quality import LLMJudgeValidator, QualityAssessment


class TestQualityValidationIntegration:
    """Integration tests for the quality validation pipeline."""

    @pytest.fixture
    def mock_validator(self) -> LLMJudgeValidator:
        """Create a validator with mocked judge."""
        validator = LLMJudgeValidator.__new__(LLMJudgeValidator)
        validator.pass_threshold = 0.6
        validator.judge = MagicMock()
        validator.judge.run = AsyncMock()
        return validator

    @pytest.mark.asyncio
    async def test_shallow_interpretation_rejected(self, mock_validator: LLMJudgeValidator) -> None:
        """Test that shallow interpretation is rejected."""
        # Configure mock to return low scores for shallow content
        mock_validator.judge.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.2,
                specificity=0.3,
                actionability=0.2,
                lowest_dimension="causal_depth",
                improvement_suggestion=(
                    "Explain the causal chain from upstream cause to observed symptom"
                ),
            )
        )

        # Shallow interpretation that just confirms the symptom
        shallow_response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.9,
            interpretation=(
                "The query results confirm there are NULL values in the user_id column "
                "of the orders table. This indicates a data quality issue."
            ),
            causal_chain="NULL values exist in the data due to some upstream issue",
            key_findings=["NULLs found in user_id column"],
        )

        result = await mock_validator.validate_interpretation(
            response=shallow_response,
            hypothesis_title="NULL user_ids due to ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is False
        assert result.assessment.causal_depth < 0.5

    @pytest.mark.asyncio
    async def test_good_interpretation_accepted(self, mock_validator: LLMJudgeValidator) -> None:
        """Test that good interpretation is accepted."""
        mock_validator.judge.run.return_value = MagicMock(
            output=QualityAssessment(
                causal_depth=0.8,
                specificity=0.9,
                actionability=0.7,
                lowest_dimension="actionability",
                improvement_suggestion="Could add specific remediation commands",
            )
        )

        # Good interpretation with causal reasoning
        good_response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation=(
                "The 485 orphaned orders all appeared after 03:14 UTC. The users table "
                "shows no updates since 03:14 UTC, suggesting the upstream ETL job stopped. "
                "This temporal correlation indicates the users ETL failure caused the JOIN "
                "to produce NULLs."
            ),
            causal_chain=(
                "users ETL stopped at 03:14 UTC -> users table stale -> "
                "orders JOIN produces NULLs for new user_ids"
            ),
            key_findings=[
                "485 orders with NULL user_id",
                "All created after 03:14 UTC",
                "Last users table update: 03:14 UTC",
            ],
        )

        result = await mock_validator.validate_interpretation(
            response=good_response,
            hypothesis_title="NULL user_ids due to ETL failure",
            query="SELECT * FROM orders WHERE user_id IS NULL LIMIT 100",
        )

        assert result.passed is True
        assert result.assessment.causal_depth >= 0.7
