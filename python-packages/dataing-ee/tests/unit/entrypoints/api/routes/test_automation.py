"""Unit tests for Automation API routes (EE)."""

import pytest
from dataing_ee.core.automation.evaluator import RuleEvaluator
from dataing_ee.core.automation.executor import ActionExecutor
from dataing_ee.entrypoints.api.routes.automation import (
    DryRunRequest,
    RuleCreate,
    RuleUpdate,
)
from dataing_ee.models.automation import ActionType


class TestRuleCreateSchema:
    """Test RuleCreate Pydantic schema."""

    def test_valid_create(self) -> None:
        """Test valid creation payload."""
        payload = RuleCreate(
            name="High Severity Auto-Investigate",
            description="Automatically spawn investigation for high severity issues",
            conditions={
                "all": [
                    {"field": "severity", "operator": "in", "value": ["high", "critical"]},
                ]
            },
            actions=[
                {"type": "spawn_investigation", "params": {"profile": "standard"}},
                {"type": "set_priority", "params": {"value": "P1"}},
            ],
            rate_limit_per_hour=50,
        )
        assert payload.name == "High Severity Auto-Investigate"
        assert payload.rate_limit_per_hour == 50
        assert len(payload.actions) == 2

    def test_minimal_create(self) -> None:
        """Test minimal creation payload."""
        payload = RuleCreate(name="Test Rule")
        assert payload.name == "Test Rule"
        assert payload.enabled is True
        assert payload.conditions == {}
        assert payload.actions == []
        assert payload.rate_limit_per_hour == 100

    def test_empty_name_invalid(self) -> None:
        """Test empty name is rejected."""
        with pytest.raises(ValueError):
            RuleCreate(name="")

    def test_rate_limit_bounds(self) -> None:
        """Test rate limit bounds."""
        # Valid min
        payload = RuleCreate(name="Test", rate_limit_per_hour=1)
        assert payload.rate_limit_per_hour == 1

        # Valid max
        payload = RuleCreate(name="Test", rate_limit_per_hour=10000)
        assert payload.rate_limit_per_hour == 10000

        # Invalid - too low
        with pytest.raises(ValueError):
            RuleCreate(name="Test", rate_limit_per_hour=0)

        # Invalid - too high
        with pytest.raises(ValueError):
            RuleCreate(name="Test", rate_limit_per_hour=10001)


class TestRuleUpdateSchema:
    """Test RuleUpdate Pydantic schema."""

    def test_all_none(self) -> None:
        """Test all fields can be None."""
        update = RuleUpdate()
        assert update.name is None
        assert update.enabled is None
        assert update.conditions is None
        assert update.actions is None
        assert update.rate_limit_per_hour is None

    def test_partial_update(self) -> None:
        """Test partial update."""
        update = RuleUpdate(name="New Name", enabled=False)
        assert update.name == "New Name"
        assert update.enabled is False
        assert update.conditions is None


class TestDryRunRequestSchema:
    """Test DryRunRequest Pydantic schema."""

    def test_with_issue_id(self) -> None:
        """Test with issue_id."""
        from uuid import uuid4

        issue_id = uuid4()
        request = DryRunRequest(issue_id=issue_id)
        assert request.issue_id == issue_id
        assert request.sample_data is None

    def test_with_sample_data(self) -> None:
        """Test with sample_data."""
        request = DryRunRequest(
            sample_data={
                "title": "Test Issue",
                "severity": "high",
            }
        )
        assert request.sample_data is not None
        assert request.sample_data["severity"] == "high"

    def test_empty_request(self) -> None:
        """Test empty request is valid (will be caught at route level)."""
        request = DryRunRequest()
        assert request.issue_id is None
        assert request.sample_data is None


class TestRuleEvaluatorValidation:
    """Test rule evaluator validation."""

    @pytest.fixture
    def evaluator(self) -> RuleEvaluator:
        """Create evaluator instance."""
        return RuleEvaluator()

    def test_valid_all_conditions(self, evaluator: RuleEvaluator) -> None:
        """Test valid all conditions."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "equals", "value": "high"},
                {"field": "status", "operator": "not_equals", "value": "closed"},
            ]
        }
        errors = evaluator.validate_conditions(conditions)
        assert errors == []

    def test_valid_any_conditions(self, evaluator: RuleEvaluator) -> None:
        """Test valid any conditions."""
        conditions = {
            "any": [
                {"field": "severity", "operator": "equals", "value": "high"},
                {"field": "severity", "operator": "equals", "value": "critical"},
            ]
        }
        errors = evaluator.validate_conditions(conditions)
        assert errors == []

    def test_invalid_structure(self, evaluator: RuleEvaluator) -> None:
        """Test invalid structure."""
        conditions = {
            "invalid_key": [{"field": "test"}],
        }
        errors = evaluator.validate_conditions(conditions)
        assert len(errors) > 0

    def test_exists_without_value(self, evaluator: RuleEvaluator) -> None:
        """Test exists operator doesn't require value."""
        conditions = {
            "all": [
                {"field": "assignee_id", "operator": "exists"},
            ]
        }
        errors = evaluator.validate_conditions(conditions)
        assert errors == []


class TestActionExecutorValidation:
    """Test action executor validation."""

    @pytest.fixture
    def executor(self) -> ActionExecutor:
        """Create executor instance."""
        return ActionExecutor()

    def test_valid_actions(self, executor: ActionExecutor) -> None:
        """Test valid actions."""
        actions = [
            {"type": "spawn_investigation", "params": {"profile": "standard"}},
            {"type": "set_priority", "params": {"value": "P1"}},
            {"type": "add_label", "params": {"label": "urgent"}},
        ]
        errors = executor.validate_actions(actions)
        assert errors == []

    def test_invalid_action_type(self, executor: ActionExecutor) -> None:
        """Test invalid action type."""
        actions = [
            {"type": "invalid_action", "params": {}},
        ]
        errors = executor.validate_actions(actions)
        assert len(errors) == 1
        assert "invalid action type" in errors[0]

    def test_missing_type(self, executor: ActionExecutor) -> None:
        """Test missing type."""
        actions = [
            {"params": {"value": "P1"}},  # Missing type
        ]
        errors = executor.validate_actions(actions)
        assert len(errors) == 1
        assert "missing 'type'" in errors[0]

    def test_actions_not_list(self, executor: ActionExecutor) -> None:
        """Test actions must be a list."""
        errors = executor.validate_actions({"type": "set_priority"})  # type: ignore
        assert len(errors) == 1
        assert "must be a list" in errors[0]

    def test_all_valid_action_types(self, executor: ActionExecutor) -> None:
        """Test all valid action types."""
        valid_types = [
            ActionType.SPAWN_INVESTIGATION,
            ActionType.SET_PRIORITY,
            ActionType.SET_SEVERITY,
            ActionType.SET_STATUS,
            ActionType.ADD_LABEL,
            ActionType.REMOVE_LABEL,
            ActionType.ASSIGN_TO,
            ActionType.NOTIFY,
            ActionType.ADD_COMMENT,
        ]
        for action_type in valid_types:
            actions = [{"type": action_type, "params": {}}]
            errors = executor.validate_actions(actions)
            assert errors == [], f"Failed for action type: {action_type}"


class TestConditionMatching:
    """Test condition matching scenarios."""

    @pytest.fixture
    def evaluator(self) -> RuleEvaluator:
        """Create evaluator instance."""
        return RuleEvaluator()

    def test_monte_carlo_high_severity_rule(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test example rule from spec."""
        conditions = {
            "all": [
                {"field": "severity", "operator": "in", "value": ["high", "critical"]},
                {"field": "source_provider", "operator": "equals", "value": "monte_carlo"},
            ]
        }

        # Should match
        issue1 = {
            "severity": "high",
            "source_provider": "monte_carlo",
        }
        result = evaluator.evaluate(conditions, issue1)
        assert result.matched is True

        # Should not match - wrong severity
        issue2 = {
            "severity": "low",
            "source_provider": "monte_carlo",
        }
        result = evaluator.evaluate(conditions, issue2)
        assert result.matched is False

        # Should not match - wrong provider
        issue3 = {
            "severity": "high",
            "source_provider": "jira",
        }
        result = evaluator.evaluate(conditions, issue3)
        assert result.matched is False

    def test_production_label_rule(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test rule matching on labels."""
        conditions = {
            "all": [
                {"field": "labels", "operator": "contains", "value": "production"},
            ]
        }

        # Should match
        issue1 = {"labels": ["production", "database"]}
        result = evaluator.evaluate(conditions, issue1)
        assert result.matched is True

        # Should not match
        issue2 = {"labels": ["staging", "database"]}
        result = evaluator.evaluate(conditions, issue2)
        assert result.matched is False

    def test_title_keyword_rule(
        self,
        evaluator: RuleEvaluator,
    ) -> None:
        """Test rule matching on title keywords."""
        conditions = {
            "any": [
                {"field": "title", "operator": "contains", "value": "outage"},
                {"field": "title", "operator": "contains", "value": "down"},
                {"field": "title", "operator": "contains", "value": "critical"},
            ]
        }

        # Should match - contains "outage"
        issue1 = {"title": "Database outage in production"}
        result = evaluator.evaluate(conditions, issue1)
        assert result.matched is True

        # Should match - contains "down"
        issue2 = {"title": "Server down - needs attention"}
        result = evaluator.evaluate(conditions, issue2)
        assert result.matched is True

        # Should not match
        issue3 = {"title": "Minor performance degradation"}
        result = evaluator.evaluate(conditions, issue3)
        assert result.matched is False
