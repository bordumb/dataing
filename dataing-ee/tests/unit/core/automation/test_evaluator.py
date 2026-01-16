"""Unit tests for automation rule evaluator."""

import pytest
from dataing_ee.core.automation.evaluator import RuleEvaluator


class TestRuleEvaluator:
    """Test rule condition evaluation."""

    @pytest.fixture
    def evaluator(self) -> RuleEvaluator:
        """Create evaluator instance."""
        return RuleEvaluator()

    @pytest.fixture
    def sample_issue(self) -> dict:
        """Sample issue data for testing."""
        return {
            "id": "123",
            "title": "Database connection failed",
            "description": "Connection timeout after 30 seconds",
            "status": "open",
            "priority": "P1",
            "severity": "high",
            "source_provider": "monte_carlo",
            "dataset_id": "warehouse.analytics.orders",
            "labels": ["database", "urgent", "production"],
        }

    def test_empty_conditions_match(self, evaluator: RuleEvaluator) -> None:
        """Empty conditions should always match."""
        result = evaluator.evaluate({}, {"any": "data"})
        assert result.matched is True

    def test_equals_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test equals operator."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "equals", "value": "high"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_equals_case_insensitive(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test equals is case insensitive."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "equals", "value": "HIGH"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_not_equals_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test not_equals operator."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "not_equals", "value": "low"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_in_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test in operator."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "in", "value": ["high", "critical"]},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_not_in_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test not_in operator."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "not_in", "value": ["low", "medium"]},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_contains_operator_string(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test contains operator on string."""
        conditions = {
            "all": [
                {"field": "title", "operator": "contains", "value": "connection"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_contains_operator_list(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test contains operator on list."""
        conditions = {
            "all": [
                {"field": "labels", "operator": "contains", "value": "urgent"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_starts_with_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test starts_with operator."""
        conditions = {
            "all": [
                {"field": "title", "operator": "starts_with", "value": "Database"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_ends_with_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test ends_with operator."""
        conditions = {
            "all": [
                {"field": "title", "operator": "ends_with", "value": "failed"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_exists_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test exists operator."""
        conditions = {
            "all": [
                {"field": "dataset_id", "operator": "exists"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_not_exists_operator(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test not_exists operator."""
        conditions = {
            "all": [
                {"field": "assignee_id", "operator": "not_exists"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_all_conditions_must_match(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test all conditions (AND) must match."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "equals", "value": "high"},
                {"field": "status", "operator": "equals", "value": "open"},
                {"field": "source_provider", "operator": "equals", "value": "monte_carlo"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_all_conditions_fail_if_one_fails(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test all conditions fail if any condition fails."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "equals", "value": "high"},
                {"field": "status", "operator": "equals", "value": "closed"},  # Fails
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is False
        assert len(result.failed_conditions) == 1

    def test_any_conditions_match_if_one_matches(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test any conditions (OR) match if any condition matches."""
        conditions = {
            "any": [
                {"field": "severity", "operator": "equals", "value": "critical"},  # Fails
                {"field": "severity", "operator": "equals", "value": "high"},  # Matches
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is True

    def test_any_conditions_fail_if_all_fail(
        self,
        evaluator: RuleEvaluator,
        sample_issue: dict,
    ) -> None:
        """Test any conditions fail if all conditions fail."""
        conditions = {
            "any": [
                {"field": "severity", "operator": "equals", "value": "low"},
                {"field": "severity", "operator": "equals", "value": "medium"},
            ]
        }
        result = evaluator.evaluate(conditions, sample_issue)
        assert result.matched is False

    def test_nested_field_access(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test dot notation for nested fields."""
        issue = {
            "metadata": {
                "source": {
                    "type": "webhook",
                }
            }
        }
        conditions = {
            "all": [
                {"field": "metadata.source.type", "operator": "equals", "value": "webhook"},
            ]
        }
        result = evaluator.evaluate(conditions, issue)
        assert result.matched is True

    def test_validate_conditions_valid(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test validation passes for valid conditions."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "in", "value": ["high", "critical"]},
                {"field": "status", "operator": "equals", "value": "open"},
            ]
        }
        errors = evaluator.validate_conditions(conditions)
        assert errors == []

    def test_validate_conditions_missing_field(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test validation fails for missing field."""
        conditions = {
            "all": [
                {"operator": "equals", "value": "high"},  # Missing field
            ]
        }
        errors = evaluator.validate_conditions(conditions)
        assert len(errors) == 1
        assert "missing 'field'" in errors[0]

    def test_validate_conditions_invalid_operator(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test validation fails for invalid operator."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "invalid_op", "value": "high"},
            ]
        }
        errors = evaluator.validate_conditions(conditions)
        assert len(errors) == 1
        assert "invalid operator" in errors[0]

    def test_validate_conditions_in_requires_list(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test validation fails when IN operator doesn't have list value."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "in", "value": "high"},  # Should be list
            ]
        }
        errors = evaluator.validate_conditions(conditions)
        assert len(errors) == 1
        assert "must be a list" in errors[0]


class TestConditionOperators:
    """Test individual condition operators."""

    @pytest.fixture
    def evaluator(self) -> RuleEvaluator:
        """Create evaluator instance."""
        return RuleEvaluator()

    def test_greater_than_numeric(self, evaluator: RuleEvaluator) -> None:
        """Test greater_than with numeric values."""
        conditions = {
            "all": [
                {"field": "count", "operator": "greater_than", "value": 10},
            ]
        }
        result = evaluator.evaluate(conditions, {"count": 15})
        assert result.matched is True

        result = evaluator.evaluate(conditions, {"count": 5})
        assert result.matched is False

    def test_less_than_numeric(self, evaluator: RuleEvaluator) -> None:
        """Test less_than with numeric values."""
        conditions = {
            "all": [
                {"field": "count", "operator": "less_than", "value": 10},
            ]
        }
        result = evaluator.evaluate(conditions, {"count": 5})
        assert result.matched is True

        result = evaluator.evaluate(conditions, {"count": 15})
        assert result.matched is False

    def test_missing_field_returns_false(self, evaluator: RuleEvaluator) -> None:
        """Test that missing field returns false for non-exists operators."""
        conditions = {
            "all": [
                {"field": "missing_field", "operator": "equals", "value": "anything"},
            ]
        }
        result = evaluator.evaluate(conditions, {"other_field": "value"})
        assert result.matched is False
