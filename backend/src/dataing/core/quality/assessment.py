"""Quality assessment types for LLM output validation."""

from __future__ import annotations

import statistics

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


class HypothesisSetAssessment(BaseModel):
    """Assessment of interpretation quality across hypothesis set.

    This class detects when the LLM is confirming rather than testing
    hypotheses. Good investigations should show variance - some hypotheses
    supported, others refuted.

    Attributes:
        interpretations: Quality assessments for each interpretation.
    """

    interpretations: list[QualityAssessment]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def discrimination_score(self) -> float:
        """Do interpretations differentiate between hypotheses?

        If all hypotheses score similarly, the LLM is confirming
        rather than testing. Good interpretations should have
        variance - some hypotheses supported, others refuted.

        Returns:
            Score from 0-1 where higher means better discrimination.
        """
        if len(self.interpretations) < 2:
            return 1.0

        confidence_values = [i.composite_score for i in self.interpretations]
        variance = statistics.variance(confidence_values)

        # Low variance = all same = bad (confirming everything)
        # High variance = differentiated = good (actually testing)
        # Normalize: variance of 0.1+ is good
        return min(1.0, variance / 0.1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_supporting_penalty(self) -> float:
        """Penalty if all hypotheses claim support.

        In a good investigation, at least one hypothesis should
        be refuted or inconclusive.

        Returns:
            Multiplier: 1.0 if diverse, 0.5 if all high scores.
        """
        if not self.interpretations:
            return 1.0

        # If all scores > 0.7, apply penalty
        high_scores = sum(1 for i in self.interpretations if i.composite_score > 0.7)
        if high_scores == len(self.interpretations):
            return 0.5  # Cut scores in half
        return 1.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def adjusted_composite(self) -> float:
        """Average composite score adjusted for discrimination and confirmation bias.

        Returns:
            Adjusted score accounting for discrimination and all-supporting penalty.
        """
        if not self.interpretations:
            return 0.0

        avg_composite = sum(i.composite_score for i in self.interpretations) / len(
            self.interpretations
        )
        return avg_composite * self.discrimination_score * self.all_supporting_penalty
