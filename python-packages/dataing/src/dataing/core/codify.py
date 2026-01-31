"""Codify - Generate regression tests from investigations.

This module provides the abstract representation of data quality tests that can
be rendered to multiple test frameworks (Great Expectations, dbt, Soda, SQL).

Every investigation that identifies a root cause can be "codified" into a
regression test that prevents the same issue from recurring.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from dataing.agents.models import SynthesisResponse


class AssertionType(str, Enum):
    """Types of data quality assertions.

    These map to common test patterns across all major data quality frameworks.
    """

    NOT_NULL = "not_null"
    """Column should not contain NULL values."""

    UNIQUE = "unique"
    """Column values should be unique (no duplicates)."""

    ACCEPTED_VALUES = "accepted_values"
    """Column values should be within an allowed set."""

    IN_RANGE = "in_range"
    """Numeric column values should be within a specified range."""

    ROW_COUNT_CHANGE = "row_count_change"
    """Row count should not change by more than a threshold percentage."""

    FRESHNESS = "freshness"
    """Data should not be older than a specified age."""

    REFERENTIAL_INTEGRITY = "referential_integrity"
    """Foreign key values should exist in the referenced table."""

    CUSTOM_SQL = "custom_sql"
    """Custom SQL assertion that should return 0 rows (no failures)."""


class ThresholdType(str, Enum):
    """Types of thresholds for test assertions."""

    EXACT = "exact"
    """Exact value match."""

    PERCENTAGE = "percentage"
    """Percentage threshold (e.g., max 5% nulls)."""

    RANGE = "range"
    """Value must be within a range."""

    COUNT = "count"
    """Maximum count of failures allowed."""


class AssertionThreshold(BaseModel):
    """Threshold configuration for a test assertion.

    Attributes:
        threshold_type: How to interpret the threshold values.
        value: The threshold value (or min for ranges).
        max_value: Maximum value for range thresholds.
        unit: Optional unit for the threshold (e.g., "percent", "hours").
    """

    model_config = ConfigDict(frozen=True)

    threshold_type: ThresholdType
    value: float
    max_value: float | None = None
    unit: str | None = None

    @classmethod
    def exact(cls, value: float) -> AssertionThreshold:
        """Create an exact value threshold."""
        return cls(threshold_type=ThresholdType.EXACT, value=value)

    @classmethod
    def percentage(cls, max_percent: float) -> AssertionThreshold:
        """Create a percentage threshold (e.g., max 5% failures)."""
        return cls(
            threshold_type=ThresholdType.PERCENTAGE,
            value=max_percent,
            unit="percent",
        )

    @classmethod
    def range(cls, min_value: float, max_value: float) -> AssertionThreshold:
        """Create a range threshold."""
        return cls(
            threshold_type=ThresholdType.RANGE,
            value=min_value,
            max_value=max_value,
        )

    @classmethod
    def count(cls, max_failures: int) -> AssertionThreshold:
        """Create a count threshold (max number of failures allowed)."""
        return cls(
            threshold_type=ThresholdType.COUNT,
            value=float(max_failures),
        )


# Alias for backward compatibility
TestThreshold = AssertionThreshold


class DataQualityTest(BaseModel):
    """Abstract representation of a data quality test.

    This model is framework-agnostic and can be rendered to multiple formats:
    - Great Expectations (expectation suite JSON)
    - dbt (schema.yml test definition)
    - Soda (SodaCL check YAML)
    - SQL (assertion query)

    Attributes:
        test_id: Unique identifier for this test.
        name: Human-readable name for the test.
        description: Detailed description of what this test catches.
        assertion_type: The type of assertion being made.
        table: Target table for the test.
        column: Target column (None for table-level tests).
        parameters: Additional parameters specific to the assertion type.
        threshold: Optional threshold for the assertion.
        sql_expression: Custom SQL for CUSTOM_SQL assertion type.
        severity: Whether test failure should warn or fail the pipeline.
        source_investigation_id: ID of the investigation that generated this test.
        failure_description: Original incident summary from the investigation.
        tags: Optional tags for categorization.
        metadata: Optional additional metadata.
    """

    model_config = ConfigDict(frozen=True)

    test_id: str = Field(..., min_length=1, description="Unique test identifier")
    name: str = Field(..., min_length=1, description="Human-readable test name")
    description: str = Field(..., min_length=10, description="What this test catches")
    assertion_type: AssertionType
    table: str = Field(..., min_length=1, description="Target table name")
    column: str | None = Field(
        default=None, description="Target column (None for table-level tests)"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Assertion-specific parameters",
    )
    threshold: AssertionThreshold | None = Field(
        default=None, description="Threshold for the assertion"
    )
    sql_expression: str | None = Field(default=None, description="Custom SQL for CUSTOM_SQL type")
    severity: Literal["warn", "fail"] = Field(
        default="fail", description="Pipeline behavior on test failure"
    )
    source_investigation_id: UUID = Field(..., description="Investigation that generated this test")
    failure_description: str = Field(..., min_length=10, description="Original incident summary")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @property
    def is_column_level(self) -> bool:
        """Check if this is a column-level test."""
        return self.column is not None

    @property
    def is_table_level(self) -> bool:
        """Check if this is a table-level test."""
        return self.column is None

    @classmethod
    def not_null(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        column: str,
        source_investigation_id: UUID,
        failure_description: str,
        description: str | None = None,
        threshold: AssertionThreshold | None = None,
        severity: Literal["warn", "fail"] = "fail",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create a NOT_NULL assertion test.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Target table name.
            column: Target column name.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Optional description override.
            threshold: Optional threshold (e.g., allow 1% nulls).
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for NOT_NULL assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=description or f"Column {column} should not contain NULL values",
            assertion_type=AssertionType.NOT_NULL,
            table=table,
            column=column,
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            threshold=threshold,
            severity=severity,
            tags=tags or [],
        )

    @classmethod
    def unique(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        column: str,
        source_investigation_id: UUID,
        failure_description: str,
        description: str | None = None,
        severity: Literal["warn", "fail"] = "fail",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create a UNIQUE assertion test.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Target table name.
            column: Target column name.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Optional description override.
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for UNIQUE assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=description or f"Column {column} values should be unique",
            assertion_type=AssertionType.UNIQUE,
            table=table,
            column=column,
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            severity=severity,
            tags=tags or [],
        )

    @classmethod
    def accepted_values(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        column: str,
        values: list[str],
        source_investigation_id: UUID,
        failure_description: str,
        description: str | None = None,
        severity: Literal["warn", "fail"] = "fail",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create an ACCEPTED_VALUES assertion test.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Target table name.
            column: Target column name.
            values: List of accepted values.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Optional description override.
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for ACCEPTED_VALUES assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=(description or f"Column {column} values should be one of: {values}"),
            assertion_type=AssertionType.ACCEPTED_VALUES,
            table=table,
            column=column,
            parameters={"values": values},
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            severity=severity,
            tags=tags or [],
        )

    @classmethod
    def in_range(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        column: str,
        min_value: float,
        max_value: float,
        source_investigation_id: UUID,
        failure_description: str,
        description: str | None = None,
        severity: Literal["warn", "fail"] = "fail",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create an IN_RANGE assertion test.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Target table name.
            column: Target column name.
            min_value: Minimum allowed value.
            max_value: Maximum allowed value.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Optional description override.
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for IN_RANGE assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=(
                description
                or f"Column {column} values should be between {min_value} and {max_value}"
            ),
            assertion_type=AssertionType.IN_RANGE,
            table=table,
            column=column,
            parameters={"min_value": min_value, "max_value": max_value},
            threshold=AssertionThreshold.range(min_value, max_value),
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            severity=severity,
            tags=tags or [],
        )

    @classmethod
    def row_count_change(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        max_change_percent: float,
        source_investigation_id: UUID,
        failure_description: str,
        description: str | None = None,
        severity: Literal["warn", "fail"] = "warn",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create a ROW_COUNT_CHANGE assertion test.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Target table name.
            max_change_percent: Maximum allowed row count change percentage.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Optional description override.
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for ROW_COUNT_CHANGE assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=(
                description or f"Row count should not change by more than {max_change_percent}%"
            ),
            assertion_type=AssertionType.ROW_COUNT_CHANGE,
            table=table,
            column=None,
            parameters={"max_change_percent": max_change_percent},
            threshold=AssertionThreshold.percentage(max_change_percent),
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            severity=severity,
            tags=tags or [],
        )

    @classmethod
    def freshness(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        column: str,
        max_age_hours: float,
        source_investigation_id: UUID,
        failure_description: str,
        description: str | None = None,
        severity: Literal["warn", "fail"] = "fail",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create a FRESHNESS assertion test.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Target table name.
            column: Timestamp column to check.
            max_age_hours: Maximum allowed data age in hours.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Optional description override.
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for FRESHNESS assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=(
                description or f"Data in {column} should not be older than {max_age_hours} hours"
            ),
            assertion_type=AssertionType.FRESHNESS,
            table=table,
            column=column,
            parameters={"max_age_hours": max_age_hours},
            threshold=AssertionThreshold(
                threshold_type=ThresholdType.EXACT,
                value=max_age_hours,
                unit="hours",
            ),
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            severity=severity,
            tags=tags or [],
        )

    @classmethod
    def custom_sql(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        sql_expression: str,
        source_investigation_id: UUID,
        failure_description: str,
        description: str,
        column: str | None = None,
        severity: Literal["warn", "fail"] = "fail",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create a CUSTOM_SQL assertion test.

        The SQL expression should return rows that FAIL the test.
        An empty result set means the test passes.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Target table name.
            sql_expression: SQL query that returns failing rows.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Description of what this test catches.
            column: Optional column reference.
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for CUSTOM_SQL assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=description,
            assertion_type=AssertionType.CUSTOM_SQL,
            table=table,
            column=column,
            sql_expression=sql_expression,
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            severity=severity,
            tags=tags or [],
        )

    @classmethod
    def referential_integrity(
        cls,
        *,
        test_id: str,
        name: str,
        table: str,
        column: str,
        reference_table: str,
        reference_column: str,
        source_investigation_id: UUID,
        failure_description: str,
        description: str | None = None,
        severity: Literal["warn", "fail"] = "fail",
        tags: list[str] | None = None,
    ) -> DataQualityTest:
        """Create a REFERENTIAL_INTEGRITY assertion test.

        Args:
            test_id: Unique test identifier.
            name: Human-readable test name.
            table: Source table name.
            column: Foreign key column name.
            reference_table: Referenced table name.
            reference_column: Referenced column name.
            source_investigation_id: Investigation ID.
            failure_description: Original incident summary.
            description: Optional description override.
            severity: Pipeline behavior on failure.
            tags: Optional categorization tags.

        Returns:
            DataQualityTest configured for REFERENTIAL_INTEGRITY assertion.
        """
        return cls(
            test_id=test_id,
            name=name,
            description=(
                description
                or f"Values in {table}.{column} should exist in "
                f"{reference_table}.{reference_column}"
            ),
            assertion_type=AssertionType.REFERENTIAL_INTEGRITY,
            table=table,
            column=column,
            parameters={
                "reference_table": reference_table,
                "reference_column": reference_column,
            },
            source_investigation_id=source_investigation_id,
            failure_description=failure_description,
            severity=severity,
            tags=tags or [],
        )


# Minimum confidence threshold for test generation
MIN_CONFIDENCE_FOR_TEST = 0.6

# Default freshness threshold in hours
DEFAULT_FRESHNESS_HOURS = 24.0

# Default row count change threshold percentage
DEFAULT_ROW_COUNT_CHANGE_PERCENT = 10.0


def extract_tests_from_synthesis(
    synthesis: SynthesisResponse,
    investigation_id: UUID,
    table: str,
    column: str | None = None,
) -> list[DataQualityTest]:
    """Extract testable assertions from investigation synthesis.

    Uses rule-based extraction to map root cause patterns to test types.
    Generates tests when confidence is above threshold (0.6).

    Args:
        synthesis: The synthesis response from an investigation.
        investigation_id: ID of the source investigation.
        table: Target table for the tests.
        column: Optional target column (extracted from synthesis if not provided).

    Returns:
        List of DataQualityTest objects that can be rendered to various formats.
    """
    # Import here to avoid circular imports

    tests: list[DataQualityTest] = []

    # Check confidence threshold
    if synthesis.confidence < MIN_CONFIDENCE_FOR_TEST:
        return tests

    if synthesis.root_cause is None:
        return tests

    root_cause_lower = synthesis.root_cause.lower()
    failure_desc = synthesis.root_cause

    # Extract column from root cause or causal chain if not provided
    detected_column = column or _extract_column_from_synthesis(synthesis)

    # Rule-based extraction: NULL values
    if _matches_null_pattern(root_cause_lower):
        if detected_column:
            tests.append(
                DataQualityTest.not_null(
                    test_id=f"test_{table}_{detected_column}_not_null",
                    name=f"{table}.{detected_column} not null",
                    table=table,
                    column=detected_column,
                    source_investigation_id=investigation_id,
                    failure_description=failure_desc,
                    tags=["auto-generated", "null-check"],
                )
            )

    # Rule-based extraction: Unexpected/invalid values
    if _matches_unexpected_value_pattern(root_cause_lower):
        if detected_column:
            # Try to extract accepted values from evidence
            accepted_values = _extract_accepted_values(synthesis.supporting_evidence)
            if accepted_values:
                tests.append(
                    DataQualityTest.accepted_values(
                        test_id=f"test_{table}_{detected_column}_accepted_values",
                        name=f"{table}.{detected_column} accepted values",
                        table=table,
                        column=detected_column,
                        values=accepted_values,
                        source_investigation_id=investigation_id,
                        failure_description=failure_desc,
                        tags=["auto-generated", "value-check"],
                    )
                )

    # Rule-based extraction: Row count issues
    if _matches_row_count_pattern(root_cause_lower):
        tests.append(
            DataQualityTest.row_count_change(
                test_id=f"test_{table}_row_count_change",
                name=f"{table} row count stability",
                table=table,
                max_change_percent=DEFAULT_ROW_COUNT_CHANGE_PERCENT,
                source_investigation_id=investigation_id,
                failure_description=failure_desc,
                tags=["auto-generated", "volume-check"],
            )
        )

    # Rule-based extraction: Freshness/staleness issues
    if _matches_freshness_pattern(root_cause_lower):
        # Use detected column if it looks like a timestamp, otherwise use defaults
        freshness_column = detected_column if detected_column else "updated_at"
        tests.append(
            DataQualityTest.freshness(
                test_id=f"test_{table}_freshness",
                name=f"{table} data freshness",
                table=table,
                column=freshness_column,
                max_age_hours=DEFAULT_FRESHNESS_HOURS,
                source_investigation_id=investigation_id,
                failure_description=failure_desc,
                tags=["auto-generated", "freshness-check"],
            )
        )

    # Rule-based extraction: Duplicate issues
    if _matches_duplicate_pattern(root_cause_lower):
        if detected_column:
            tests.append(
                DataQualityTest.unique(
                    test_id=f"test_{table}_{detected_column}_unique",
                    name=f"{table}.{detected_column} unique",
                    table=table,
                    column=detected_column,
                    source_investigation_id=investigation_id,
                    failure_description=failure_desc,
                    tags=["auto-generated", "uniqueness-check"],
                )
            )

    # Rule-based extraction: Referential integrity issues
    if _matches_referential_pattern(root_cause_lower):
        ref_info = _extract_reference_info(synthesis)
        if detected_column and ref_info:
            tests.append(
                DataQualityTest.referential_integrity(
                    test_id=f"test_{table}_{detected_column}_fk",
                    name=f"{table}.{detected_column} foreign key valid",
                    table=table,
                    column=detected_column,
                    reference_table=ref_info["table"],
                    reference_column=ref_info["column"],
                    source_investigation_id=investigation_id,
                    failure_description=failure_desc,
                    tags=["auto-generated", "referential-integrity"],
                )
            )

    # Fallback: Generate custom SQL test for complex cases not matched above
    if not tests:
        # Generate a custom SQL assertion from the evidence
        sql_assertion = _generate_custom_sql_assertion(synthesis, table, detected_column)
        if sql_assertion:
            tests.append(
                DataQualityTest.custom_sql(
                    test_id=f"test_{table}_custom_assertion",
                    name=f"{table} custom data quality check",
                    table=table,
                    sql_expression=sql_assertion,
                    description=(f"Custom assertion based on investigation: {failure_desc[:100]}"),
                    column=detected_column,
                    source_investigation_id=investigation_id,
                    failure_description=failure_desc,
                    tags=["auto-generated", "custom-sql"],
                )
            )

    return tests


def _matches_null_pattern(text: str) -> bool:
    """Check if text indicates NULL value issues."""
    patterns = [
        "null",
        "missing value",
        "empty",
        "blank",
        "not populated",
        "none value",
    ]
    return any(p in text for p in patterns)


def _matches_unexpected_value_pattern(text: str) -> bool:
    """Check if text indicates unexpected/invalid value issues."""
    patterns = [
        "unexpected value",
        "invalid value",
        "incorrect value",
        "wrong value",
        "bad value",
        "outlier",
        "out of range",
        "not in expected",
        "unexpected status",
        "invalid status",
    ]
    return any(p in text for p in patterns)


def _matches_row_count_pattern(text: str) -> bool:
    """Check if text indicates row count issues."""
    patterns = [
        "row count",
        "record count",
        "volume drop",
        "volume spike",
        "fewer rows",
        "more rows than expected",
        "missing rows",
        "missing records",
        "dropped records",
    ]
    return any(p in text for p in patterns)


def _matches_freshness_pattern(text: str) -> bool:
    """Check if text indicates data freshness issues."""
    patterns = [
        "stale",
        "freshness",
        "outdated",
        "not updated",
        "old data",
        "delayed",
        "late arriving",
        "latency",
    ]
    return any(p in text for p in patterns)


def _matches_duplicate_pattern(text: str) -> bool:
    """Check if text indicates duplicate issues."""
    patterns = [
        "duplicate",
        "duplicated",
        "not unique",
        "repeated",
        "multiple copies",
    ]
    return any(p in text for p in patterns)


def _matches_referential_pattern(text: str) -> bool:
    """Check if text indicates referential integrity issues."""
    patterns = [
        "orphan",
        "foreign key",
        "referential",
        "missing parent",
        "no matching",
        "dangling reference",
        "broken reference",
        "missing reference",
    ]
    return any(p in text for p in patterns)


def _extract_column_from_synthesis(synthesis: SynthesisResponse) -> str | None:
    """Try to extract column name from synthesis text.

    Looks for common column reference patterns in root cause and causal chain.

    Args:
        synthesis: The synthesis response.

    Returns:
        Column name if found, None otherwise.
    """
    import re

    text = f"{synthesis.root_cause or ''} {' '.join(synthesis.causal_chain)}"

    # Pattern: "column X", "the X column", "X column"
    match = re.search(r"(?:column\s+|the\s+)([a-z_][a-z0-9_]*)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).lower()

    # Pattern: "table.column"
    match = re.search(r"\b\w+\.([a-z_][a-z0-9_]*)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).lower()

    # Pattern: "in X field", "the X field"
    match = re.search(r"(?:in|the)\s+([a-z_][a-z0-9_]*)\s+field", text, re.IGNORECASE)
    if match:
        return match.group(1).lower()

    return None


def _extract_accepted_values(evidence: list[str]) -> list[str]:
    """Extract accepted values from evidence.

    Looks for patterns like "expected values: A, B, C" or "valid values are X, Y, Z".

    Args:
        evidence: List of evidence strings.

    Returns:
        List of accepted values if found, empty list otherwise.
    """
    import re

    for item in evidence:
        # Pattern: "expected/valid/accepted values: X, Y, Z"
        match = re.search(
            r"(?:expected|valid|accepted|allowed)\s+values?[:\s]+([^.]+)",
            item,
            re.IGNORECASE,
        )
        if match:
            values_str = match.group(1)
            # Split by comma or 'or'
            values = re.split(r",\s*|\s+or\s+", values_str)
            return [v.strip().strip("'\"") for v in values if v.strip()]

    return []


def _extract_reference_info(
    synthesis: SynthesisResponse,
) -> dict[str, str] | None:
    """Extract reference table and column from synthesis.

    Looks for patterns indicating foreign key relationships.

    Args:
        synthesis: The synthesis response.

    Returns:
        Dict with 'table' and 'column' keys if found, None otherwise.
    """
    import re

    text = f"{synthesis.root_cause or ''} {' '.join(synthesis.causal_chain)}"

    # Pattern: "in TABLE" or "from TABLE"
    table_match = re.search(
        r"(?:in|from|reference[sd]?)\s+([a-z_][a-z0-9_]*)\s+table",
        text,
        re.IGNORECASE,
    )

    if table_match:
        ref_table = table_match.group(1).lower()
        # Assume 'id' column for the reference
        return {"table": ref_table, "column": "id"}

    return None


def _generate_custom_sql_assertion(
    synthesis: SynthesisResponse,
    table: str,
    column: str | None,
) -> str | None:
    """Generate a custom SQL assertion from synthesis.

    Creates a basic assertion query based on the root cause description.

    Args:
        synthesis: The synthesis response.
        table: Target table.
        column: Optional column reference.

    Returns:
        SQL assertion string or None if cannot generate.
    """
    if not synthesis.root_cause:
        return None

    # For complex cases, generate a placeholder SQL that returns rows failing the test
    # The user should customize this
    root_cause_snippet = synthesis.root_cause[:100]
    if column:
        return f"""-- Auto-generated from investigation
-- Root cause: {root_cause_snippet}
-- TODO: Customize this assertion
SELECT *
FROM {table}
WHERE {column} IS NULL
   OR {column} NOT IN (SELECT DISTINCT valid_value FROM reference_values)
LIMIT 100"""
    else:
        return f"""-- Auto-generated from investigation
-- Root cause: {root_cause_snippet}
-- TODO: Customize this assertion
SELECT *
FROM {table}
WHERE 1=0  -- Replace with actual assertion condition
LIMIT 100"""
