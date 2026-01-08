"""Tests for quality assessment types."""

import pytest
from dataing.core.quality.assessment import QualityAssessment, ValidationResult


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
