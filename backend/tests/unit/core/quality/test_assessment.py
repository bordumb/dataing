"""Tests for quality assessment types."""

import pytest
from dataing.core.quality.assessment import (
    HypothesisSetAssessment,
    QualityAssessment,
    ValidationResult,
)


class TestQualityAssessment:
    """Tests for QualityAssessment model."""

    def test_composite_score_calculation(self) -> None:
        """Test weighted composite score calculation."""
        assessment = QualityAssessment(
            causal_depth=0.8,
            specificity=0.6,
            actionability=0.4,
            lowest_dimension="actionability",
            improvement_suggestion="Provide specific commands instead of generic advice",
        )
        # 0.8 * 0.5 + 0.6 * 0.3 + 0.4 * 0.2 = 0.4 + 0.18 + 0.08 = 0.66
        assert assessment.composite_score == pytest.approx(0.66)

    def test_composite_score_all_high(self) -> None:
        """Test composite score when all dimensions are high."""
        assessment = QualityAssessment(
            causal_depth=0.9,
            specificity=0.9,
            actionability=0.9,
            lowest_dimension="causal_depth",
            improvement_suggestion="Minor improvements possible",
        )
        # 0.9 * 0.5 + 0.9 * 0.3 + 0.9 * 0.2 = 0.45 + 0.27 + 0.18 = 0.9
        assert assessment.composite_score == pytest.approx(0.9)

    def test_score_bounds(self) -> None:
        """Test that scores must be between 0 and 1."""
        with pytest.raises(ValueError):
            QualityAssessment(
                causal_depth=1.5,  # Invalid
                specificity=0.5,
                actionability=0.5,
                lowest_dimension="causal_depth",
                improvement_suggestion="Test",
            )


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_training_signals_property(self) -> None:
        """Test training_signals computed property."""
        assessment = QualityAssessment(
            causal_depth=0.7,
            specificity=0.8,
            actionability=0.5,
            lowest_dimension="actionability",
            improvement_suggestion="Be more specific about actions",
        )
        result = ValidationResult(passed=True, assessment=assessment)

        signals = result.training_signals
        assert signals["causal_depth"] == 0.7
        assert signals["specificity"] == 0.8
        assert signals["actionability"] == 0.5
        assert "composite" in signals

    def test_passed_based_on_threshold(self) -> None:
        """Test that passed reflects composite score vs threshold."""
        assessment = QualityAssessment(
            causal_depth=0.8,
            specificity=0.7,
            actionability=0.6,
            lowest_dimension="actionability",
            improvement_suggestion="Minor improvements needed",
        )
        # composite = 0.8*0.5 + 0.7*0.3 + 0.6*0.2 = 0.4 + 0.21 + 0.12 = 0.73
        result = ValidationResult(passed=True, assessment=assessment)
        assert result.passed is True
        assert result.assessment.composite_score == pytest.approx(0.73)


class TestHypothesisSetAssessment:
    """Tests for HypothesisSetAssessment discrimination scoring."""

    def _make_assessment(self, causal: float, spec: float, action: float) -> QualityAssessment:
        """Helper to create assessment with given scores."""
        return QualityAssessment(
            causal_depth=causal,
            specificity=spec,
            actionability=action,
            lowest_dimension="actionability",
            improvement_suggestion="Test improvement suggestion here",
        )

    def test_discrimination_score_single_interpretation(self) -> None:
        """Single interpretation should have perfect discrimination."""
        assessment = HypothesisSetAssessment(interpretations=[self._make_assessment(0.8, 0.7, 0.6)])
        assert assessment.discrimination_score == 1.0

    def test_discrimination_score_identical_scores(self) -> None:
        """Identical scores = no discrimination = low score."""
        assessment = HypothesisSetAssessment(
            interpretations=[
                self._make_assessment(0.8, 0.7, 0.6),
                self._make_assessment(0.8, 0.7, 0.6),
                self._make_assessment(0.8, 0.7, 0.6),
            ]
        )
        # All same composite scores -> variance = 0 -> discrimination = 0
        assert assessment.discrimination_score == 0.0

    def test_discrimination_score_high_variance(self) -> None:
        """High variance in scores = good discrimination."""
        assessment = HypothesisSetAssessment(
            interpretations=[
                self._make_assessment(0.9, 0.9, 0.9),  # composite ~0.9
                self._make_assessment(0.3, 0.3, 0.3),  # composite ~0.3
                self._make_assessment(0.6, 0.6, 0.6),  # composite ~0.6
            ]
        )
        # High variance -> discrimination approaches 1.0
        assert assessment.discrimination_score > 0.5

    def test_all_supporting_penalty_diverse(self) -> None:
        """Diverse scores should have no penalty."""
        assessment = HypothesisSetAssessment(
            interpretations=[
                self._make_assessment(0.9, 0.9, 0.9),  # composite ~0.9 (high)
                self._make_assessment(0.3, 0.3, 0.3),  # composite ~0.3 (low)
            ]
        )
        assert assessment.all_supporting_penalty == 1.0

    def test_all_supporting_penalty_all_high(self) -> None:
        """All high scores should apply 0.5 penalty."""
        assessment = HypothesisSetAssessment(
            interpretations=[
                self._make_assessment(0.9, 0.9, 0.9),  # composite ~0.9
                self._make_assessment(0.85, 0.85, 0.85),  # composite ~0.85
                self._make_assessment(0.8, 0.8, 0.8),  # composite ~0.8
            ]
        )
        # All > 0.7 -> penalty applied
        assert assessment.all_supporting_penalty == 0.5

    def test_adjusted_composite_with_penalty(self) -> None:
        """Adjusted composite should apply both discrimination and penalty."""
        # All same high scores -> low discrimination, penalty applied
        assessment = HypothesisSetAssessment(
            interpretations=[
                self._make_assessment(0.8, 0.8, 0.8),
                self._make_assessment(0.8, 0.8, 0.8),
            ]
        )
        # avg composite = 0.8, discrimination = 0 (same scores), penalty = 0.5
        # adjusted = 0.8 * 0.0 * 0.5 = 0.0
        assert assessment.adjusted_composite == 0.0

    def test_adjusted_composite_good_investigation(self) -> None:
        """Good investigation has variance and some refuted hypotheses."""
        assessment = HypothesisSetAssessment(
            interpretations=[
                self._make_assessment(0.9, 0.8, 0.7),  # composite ~0.83
                self._make_assessment(0.4, 0.3, 0.2),  # composite ~0.33
                self._make_assessment(0.6, 0.5, 0.5),  # composite ~0.55
            ]
        )
        # Good variance, not all high -> no penalty, good discrimination
        assert assessment.discrimination_score > 0.5
        assert assessment.all_supporting_penalty == 1.0
        assert assessment.adjusted_composite > 0.3

    def test_empty_interpretations(self) -> None:
        """Empty interpretations should handle gracefully."""
        assessment = HypothesisSetAssessment(interpretations=[])
        assert assessment.all_supporting_penalty == 1.0
        assert assessment.adjusted_composite == 0.0
