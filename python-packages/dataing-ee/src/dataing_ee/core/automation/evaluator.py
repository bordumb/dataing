"""Rule condition evaluator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from dataing_ee.models.automation import ConditionOperator

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of evaluating a rule's conditions."""

    matched: bool
    matched_conditions: dict[str, Any] = field(default_factory=dict)
    failed_conditions: list[dict[str, Any]] = field(default_factory=list)


class RuleEvaluator:
    """Evaluate rule conditions against issue data."""

    def evaluate(
        self,
        conditions: dict[str, Any],
        issue_data: dict[str, Any],
    ) -> EvaluationResult:
        """Evaluate conditions against issue data.

        Args:
            conditions: Rule conditions (DSL format)
            issue_data: Issue fields to evaluate against

        Returns:
            EvaluationResult with match status and details
        """
        if not conditions:
            # Empty conditions = always match
            return EvaluationResult(matched=True)

        matched_conditions: dict[str, Any] = {}
        failed_conditions: list[dict[str, Any]] = []

        # Handle "all" (AND) conditions
        if "all" in conditions:
            all_matched = True
            for condition in conditions["all"]:
                result = self._evaluate_condition(condition, issue_data)
                if result:
                    matched_conditions[condition.get("field", "unknown")] = condition
                else:
                    all_matched = False
                    failed_conditions.append(condition)

            return EvaluationResult(
                matched=all_matched,
                matched_conditions=matched_conditions,
                failed_conditions=failed_conditions,
            )

        # Handle "any" (OR) conditions
        if "any" in conditions:
            any_matched = False
            for condition in conditions["any"]:
                result = self._evaluate_condition(condition, issue_data)
                if result:
                    any_matched = True
                    matched_conditions[condition.get("field", "unknown")] = condition
                else:
                    failed_conditions.append(condition)

            return EvaluationResult(
                matched=any_matched,
                matched_conditions=matched_conditions,
                failed_conditions=failed_conditions,
            )

        # Handle single condition (legacy format)
        if "field" in conditions:
            result = self._evaluate_condition(conditions, issue_data)
            if result:
                return EvaluationResult(
                    matched=True,
                    matched_conditions={conditions.get("field", "unknown"): conditions},
                )
            return EvaluationResult(
                matched=False,
                failed_conditions=[conditions],
            )

        # Unknown format
        logger.warning(f"unknown_condition_format: {conditions}")
        return EvaluationResult(matched=False)

    def _evaluate_condition(
        self,
        condition: dict[str, Any],
        issue_data: dict[str, Any],
    ) -> bool:
        """Evaluate a single condition."""
        field_name = condition.get("field")
        operator = condition.get("operator", ConditionOperator.EQUALS)
        expected_value = condition.get("value")

        if not field_name:
            return False

        # Get actual value from issue data (supports dot notation)
        actual_value = self._get_field_value(issue_data, field_name)

        return self._compare_values(actual_value, operator, expected_value)

    def _get_field_value(
        self,
        data: dict[str, Any],
        field_path: str,
    ) -> Any:
        """Get field value using dot notation."""
        keys = field_path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _compare_values(
        self,
        actual: Any,
        operator: str,
        expected: Any,
    ) -> bool:
        """Compare actual value against expected using operator."""
        # Handle exists/not_exists operators
        if operator == ConditionOperator.EXISTS:
            return actual is not None
        if operator == ConditionOperator.NOT_EXISTS:
            return actual is None

        # For other operators, if actual is None, comparison fails
        if actual is None:
            return False

        # Normalize string comparisons to lowercase
        if isinstance(actual, str):
            actual_lower = actual.lower()
        else:
            actual_lower = actual

        if isinstance(expected, str):
            expected_lower = expected.lower()
        else:
            expected_lower = expected

        # Handle different operators
        if operator == ConditionOperator.EQUALS:
            return actual_lower == expected_lower

        if operator == ConditionOperator.NOT_EQUALS:
            return actual_lower != expected_lower

        if operator == ConditionOperator.IN:
            if isinstance(expected, list):
                expected_list = [v.lower() if isinstance(v, str) else v for v in expected]
                return actual_lower in expected_list
            return False

        if operator == ConditionOperator.NOT_IN:
            if isinstance(expected, list):
                expected_list = [v.lower() if isinstance(v, str) else v for v in expected]
                return actual_lower not in expected_list
            return True

        if operator == ConditionOperator.CONTAINS:
            if isinstance(actual, str) and isinstance(expected, str):
                return expected_lower in actual_lower
            if isinstance(actual, list):
                return expected_lower in [v.lower() if isinstance(v, str) else v for v in actual]
            return False

        if operator == ConditionOperator.NOT_CONTAINS:
            if isinstance(actual, str) and isinstance(expected, str):
                return expected_lower not in actual_lower
            if isinstance(actual, list):
                return expected_lower not in [
                    v.lower() if isinstance(v, str) else v for v in actual
                ]
            return True

        if operator == ConditionOperator.STARTS_WITH:
            if isinstance(actual, str) and isinstance(expected, str):
                return actual_lower.startswith(expected_lower)
            return False

        if operator == ConditionOperator.ENDS_WITH:
            if isinstance(actual, str) and isinstance(expected, str):
                return actual_lower.endswith(expected_lower)
            return False

        if operator == ConditionOperator.GREATER_THAN:
            try:
                return float(actual) > float(expected)
            except (ValueError, TypeError):
                return False

        if operator == ConditionOperator.LESS_THAN:
            try:
                return float(actual) < float(expected)
            except (ValueError, TypeError):
                return False

        # Unknown operator
        logger.warning(f"unknown_operator: {operator}")
        return False

    def validate_conditions(
        self,
        conditions: dict[str, Any],
    ) -> list[str]:
        """Validate condition DSL structure.

        Returns list of validation errors (empty if valid).
        """
        errors: list[str] = []

        if not conditions:
            return errors

        # Check for valid structure
        if "all" not in conditions and "any" not in conditions and "field" not in conditions:
            errors.append("Conditions must have 'all', 'any', or 'field' key")
            return errors

        # Validate condition lists
        for key in ["all", "any"]:
            if key in conditions:
                if not isinstance(conditions[key], list):
                    errors.append(f"'{key}' must be a list of conditions")
                else:
                    for i, cond in enumerate(conditions[key]):
                        cond_errors = self._validate_single_condition(cond, f"{key}[{i}]")
                        errors.extend(cond_errors)

        # Validate single condition
        if "field" in conditions:
            errors.extend(self._validate_single_condition(conditions, "condition"))

        return errors

    def _validate_single_condition(
        self,
        condition: dict[str, Any],
        path: str,
    ) -> list[str]:
        """Validate a single condition."""
        errors: list[str] = []

        if not isinstance(condition, dict):
            errors.append(f"{path}: must be a dict")
            return errors

        if "field" not in condition:
            errors.append(f"{path}: missing 'field' key")

        operator = condition.get("operator", ConditionOperator.EQUALS)
        valid_operators = [
            ConditionOperator.EQUALS,
            ConditionOperator.NOT_EQUALS,
            ConditionOperator.IN,
            ConditionOperator.NOT_IN,
            ConditionOperator.CONTAINS,
            ConditionOperator.NOT_CONTAINS,
            ConditionOperator.STARTS_WITH,
            ConditionOperator.ENDS_WITH,
            ConditionOperator.GREATER_THAN,
            ConditionOperator.LESS_THAN,
            ConditionOperator.EXISTS,
            ConditionOperator.NOT_EXISTS,
        ]
        if operator not in valid_operators:
            errors.append(f"{path}: invalid operator '{operator}'")

        # Some operators require value
        if operator not in [ConditionOperator.EXISTS, ConditionOperator.NOT_EXISTS]:
            if "value" not in condition:
                errors.append(f"{path}: missing 'value' for operator '{operator}'")

        # IN/NOT_IN require list value
        if operator in [ConditionOperator.IN, ConditionOperator.NOT_IN]:
            value = condition.get("value")
            if value is not None and not isinstance(value, list):
                errors.append(f"{path}: 'value' must be a list for operator '{operator}'")

        return errors
