"""Quality assessment types for LLM output validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class QualityAssessment(BaseModel):
    """Dimensional quality scores from LLM-as-judge.

    Attributes:
        causal_depth: Score for causal reasoning quality (0-1).
        specificity: Score for concrete data points (0-1).
        actionability: Score for actionable recommendations (0-1).
        lowest_dimension: Which dimension scored lowest.
        improvement_suggestion: How to improve the lowest dimension.
    """

    causal_depth: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Does causal_chain explain WHY? "
            "0=restates symptom, 0.5=cause without mechanism, 1=full causal chain"
        ),
    )
    specificity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Are there concrete data points? "
            "0=vague, 0.5=some numbers, 1=timestamps+counts+names"
        ),
    )
    actionability: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Can someone act on recommendations? "
            "0=generic advice, 0.5=direction without specifics, 1=exact commands/steps"
        ),
    )
    lowest_dimension: str = Field(
        description=(
            "Which dimension scored lowest: " "'causal_depth', 'specificity', or 'actionability'"
        )
    )
    improvement_suggestion: str = Field(
        min_length=20,
        description="Specific suggestion to improve the lowest-scoring dimension",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def composite_score(self) -> float:
        """Calculate weighted composite score for pass/fail decisions."""
        return self.causal_depth * 0.5 + self.specificity * 0.3 + self.actionability * 0.2


class ValidationResult(BaseModel):
    """Result of quality validation.

    Attributes:
        passed: Whether the response passed validation.
        assessment: Detailed quality assessment with dimensional scores.
    """

    passed: bool
    assessment: QualityAssessment

    @computed_field  # type: ignore[prop-decorator]
    @property
    def training_signals(self) -> dict[str, float]:
        """Extract dimensional scores for RL training."""
        return {
            "causal_depth": self.assessment.causal_depth,
            "specificity": self.assessment.specificity,
            "actionability": self.assessment.actionability,
            "composite": self.assessment.composite_score,
        }
