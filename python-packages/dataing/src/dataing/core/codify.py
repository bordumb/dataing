"""Codify - Generate regression tests from investigations.

This module provides the abstract representation of data quality tests that can
be rendered to multiple test frameworks (Great Expectations, dbt, Soda, SQL).

Every investigation that identifies a root cause can be "codified" into a
regression test that prevents the same issue from recurring.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
