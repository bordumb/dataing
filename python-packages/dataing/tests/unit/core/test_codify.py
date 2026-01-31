"""Tests for the codify module - DataQualityTest model."""

from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from dataing.core.codify import (
    AssertionType,
    DataQualityTest,
    TestThreshold,
    ThresholdType,
)

if TYPE_CHECKING:
    pass  # MagicMock already imported above


class TestAssertionType:
    """Tests for AssertionType enum."""

    def test_assertion_types_exist(self) -> None:
        """Test all expected assertion types exist."""
        assert AssertionType.NOT_NULL.value == "not_null"
        assert AssertionType.UNIQUE.value == "unique"
        assert AssertionType.ACCEPTED_VALUES.value == "accepted_values"
        assert AssertionType.IN_RANGE.value == "in_range"
        assert AssertionType.ROW_COUNT_CHANGE.value == "row_count_change"
        assert AssertionType.FRESHNESS.value == "freshness"
        assert AssertionType.REFERENTIAL_INTEGRITY.value == "referential_integrity"
        assert AssertionType.CUSTOM_SQL.value == "custom_sql"

    def test_assertion_type_from_string(self) -> None:
        """Test creating assertion type from string."""
        assert AssertionType("not_null") == AssertionType.NOT_NULL
        assert AssertionType("unique") == AssertionType.UNIQUE


class TestThresholdType:
    """Tests for ThresholdType enum."""

    def test_threshold_types_exist(self) -> None:
        """Test all threshold types exist."""
        assert ThresholdType.EXACT.value == "exact"
        assert ThresholdType.PERCENTAGE.value == "percentage"
        assert ThresholdType.RANGE.value == "range"
        assert ThresholdType.COUNT.value == "count"


class TestTestThreshold:
    """Tests for TestThreshold model."""

    def test_exact_threshold(self) -> None:
        """Test creating exact threshold."""
        threshold = TestThreshold.exact(100.0)
        assert threshold.threshold_type == ThresholdType.EXACT
        assert threshold.value == 100.0
        assert threshold.max_value is None

    def test_percentage_threshold(self) -> None:
        """Test creating percentage threshold."""
        threshold = TestThreshold.percentage(5.0)
        assert threshold.threshold_type == ThresholdType.PERCENTAGE
        assert threshold.value == 5.0
        assert threshold.unit == "percent"

    def test_range_threshold(self) -> None:
        """Test creating range threshold."""
        threshold = TestThreshold.range(0.0, 100.0)
        assert threshold.threshold_type == ThresholdType.RANGE
        assert threshold.value == 0.0
        assert threshold.max_value == 100.0

    def test_count_threshold(self) -> None:
        """Test creating count threshold."""
        threshold = TestThreshold.count(10)
        assert threshold.threshold_type == ThresholdType.COUNT
        assert threshold.value == 10.0

    def test_threshold_is_frozen(self) -> None:
        """Test that threshold is immutable."""
        threshold = TestThreshold.exact(100.0)
        with pytest.raises(ValidationError):
            threshold.value = 200.0  # type: ignore[misc]


class TestDataQualityTest:
    """Tests for DataQualityTest model."""

    @pytest.fixture
    def investigation_id(self) -> "uuid4":
        """Create a sample investigation ID."""
        return uuid4()

    def test_create_basic_test(self, investigation_id: "uuid4") -> None:
        """Test creating a basic DataQualityTest."""
        test = DataQualityTest(
            test_id="test_orders_user_id_not_null",
            name="Orders user_id not null",
            description="Ensures user_id column has no NULL values",
            assertion_type=AssertionType.NOT_NULL,
            table="orders",
            column="user_id",
            source_investigation_id=investigation_id,
            failure_description="Found 485 NULL user_id values causing join failures",
        )

        assert test.test_id == "test_orders_user_id_not_null"
        assert test.name == "Orders user_id not null"
        assert test.assertion_type == AssertionType.NOT_NULL
        assert test.table == "orders"
        assert test.column == "user_id"
        assert test.is_column_level is True
        assert test.is_table_level is False
        assert test.severity == "fail"  # default

    def test_table_level_test(self, investigation_id: "uuid4") -> None:
        """Test creating a table-level test (no column)."""
        test = DataQualityTest(
            test_id="test_orders_row_count",
            name="Orders row count stable",
            description="Row count should not change dramatically",
            assertion_type=AssertionType.ROW_COUNT_CHANGE,
            table="orders",
            column=None,
            source_investigation_id=investigation_id,
            failure_description="Row count dropped 50% unexpectedly",
        )

        assert test.column is None
        assert test.is_column_level is False
        assert test.is_table_level is True

    def test_test_with_threshold(self, investigation_id: "uuid4") -> None:
        """Test creating a test with threshold."""
        test = DataQualityTest(
            test_id="test_orders_nulls",
            name="Orders null rate check",
            description="Null rate should be below 5%",
            assertion_type=AssertionType.NOT_NULL,
            table="orders",
            column="user_id",
            threshold=TestThreshold.percentage(5.0),
            source_investigation_id=investigation_id,
            failure_description="Null rate exceeded 5%",
        )

        assert test.threshold is not None
        assert test.threshold.threshold_type == ThresholdType.PERCENTAGE
        assert test.threshold.value == 5.0

    def test_test_with_parameters(self, investigation_id: "uuid4") -> None:
        """Test creating a test with parameters."""
        test = DataQualityTest(
            test_id="test_orders_status",
            name="Orders status accepted values",
            description="Status should be valid",
            assertion_type=AssertionType.ACCEPTED_VALUES,
            table="orders",
            column="status",
            parameters={"values": ["pending", "shipped", "delivered", "cancelled"]},
            source_investigation_id=investigation_id,
            failure_description="Found invalid status values",
        )

        assert test.parameters["values"] == [
            "pending",
            "shipped",
            "delivered",
            "cancelled",
        ]

    def test_test_with_custom_sql(self, investigation_id: "uuid4") -> None:
        """Test creating a custom SQL test."""
        sql = "SELECT * FROM orders WHERE amount < 0"
        test = DataQualityTest(
            test_id="test_orders_positive_amount",
            name="Orders amount positive",
            description="Order amounts should never be negative",
            assertion_type=AssertionType.CUSTOM_SQL,
            table="orders",
            sql_expression=sql,
            source_investigation_id=investigation_id,
            failure_description="Found orders with negative amounts",
        )

        assert test.sql_expression == sql
        assert test.assertion_type == AssertionType.CUSTOM_SQL

    def test_test_with_tags(self, investigation_id: "uuid4") -> None:
        """Test creating a test with tags."""
        test = DataQualityTest(
            test_id="test_orders_amount",
            name="Orders amount in range",
            description="Amount should be reasonable",
            assertion_type=AssertionType.IN_RANGE,
            table="orders",
            column="amount",
            parameters={"min_value": 0, "max_value": 10000},
            tags=["finance", "critical"],
            source_investigation_id=investigation_id,
            failure_description="Found unreasonable amounts",
        )

        assert test.tags == ["finance", "critical"]

    def test_severity_options(self, investigation_id: "uuid4") -> None:
        """Test severity options."""
        test_warn = DataQualityTest(
            test_id="test_1",
            name="Test",
            description="Test description here",
            assertion_type=AssertionType.NOT_NULL,
            table="t",
            severity="warn",
            source_investigation_id=investigation_id,
            failure_description="Some failure description",
        )
        assert test_warn.severity == "warn"

        test_fail = DataQualityTest(
            test_id="test_2",
            name="Test",
            description="Test description here",
            assertion_type=AssertionType.NOT_NULL,
            table="t",
            severity="fail",
            source_investigation_id=investigation_id,
            failure_description="Some failure description",
        )
        assert test_fail.severity == "fail"

    def test_test_is_frozen(self, investigation_id: "uuid4") -> None:
        """Test that DataQualityTest is immutable."""
        test = DataQualityTest(
            test_id="test_1",
            name="Test",
            description="Test description here",
            assertion_type=AssertionType.NOT_NULL,
            table="orders",
            source_investigation_id=investigation_id,
            failure_description="Some failure description",
        )

        with pytest.raises(ValidationError):
            test.name = "New Name"  # type: ignore[misc]

    def test_validation_requires_test_id(self, investigation_id: "uuid4") -> None:
        """Test that test_id is required."""
        with pytest.raises(ValidationError):
            DataQualityTest(
                test_id="",  # Empty string should fail
                name="Test",
                description="Test description here",
                assertion_type=AssertionType.NOT_NULL,
                table="orders",
                source_investigation_id=investigation_id,
                failure_description="Some failure description",
            )

    def test_validation_requires_description(self, investigation_id: "uuid4") -> None:
        """Test that description must be at least 10 chars."""
        with pytest.raises(ValidationError):
            DataQualityTest(
                test_id="test_1",
                name="Test",
                description="Short",  # Too short
                assertion_type=AssertionType.NOT_NULL,
                table="orders",
                source_investigation_id=investigation_id,
                failure_description="Some failure description",
            )


class TestDataQualityTestFactoryMethods:
    """Tests for DataQualityTest factory methods."""

    @pytest.fixture
    def investigation_id(self) -> "uuid4":
        """Create a sample investigation ID."""
        return uuid4()

    def test_not_null_factory(self, investigation_id: "uuid4") -> None:
        """Test not_null factory method."""
        test = DataQualityTest.not_null(
            test_id="test_user_id",
            name="User ID not null",
            table="orders",
            column="user_id",
            source_investigation_id=investigation_id,
            failure_description="Found NULL user_id values",
        )

        assert test.assertion_type == AssertionType.NOT_NULL
        assert test.table == "orders"
        assert test.column == "user_id"
        assert "NULL" in test.description

    def test_unique_factory(self, investigation_id: "uuid4") -> None:
        """Test unique factory method."""
        test = DataQualityTest.unique(
            test_id="test_order_id",
            name="Order ID unique",
            table="orders",
            column="order_id",
            source_investigation_id=investigation_id,
            failure_description="Found duplicate order_id values",
        )

        assert test.assertion_type == AssertionType.UNIQUE
        assert "unique" in test.description

    def test_accepted_values_factory(self, investigation_id: "uuid4") -> None:
        """Test accepted_values factory method."""
        values = ["active", "inactive", "pending"]
        test = DataQualityTest.accepted_values(
            test_id="test_status",
            name="Status accepted values",
            table="users",
            column="status",
            values=values,
            source_investigation_id=investigation_id,
            failure_description="Found invalid status values",
        )

        assert test.assertion_type == AssertionType.ACCEPTED_VALUES
        assert test.parameters["values"] == values

    def test_in_range_factory(self, investigation_id: "uuid4") -> None:
        """Test in_range factory method."""
        test = DataQualityTest.in_range(
            test_id="test_amount",
            name="Amount in range",
            table="orders",
            column="amount",
            min_value=0.0,
            max_value=10000.0,
            source_investigation_id=investigation_id,
            failure_description="Found out of range amounts",
        )

        assert test.assertion_type == AssertionType.IN_RANGE
        assert test.parameters["min_value"] == 0.0
        assert test.parameters["max_value"] == 10000.0
        assert test.threshold is not None
        assert test.threshold.threshold_type == ThresholdType.RANGE

    def test_row_count_change_factory(self, investigation_id: "uuid4") -> None:
        """Test row_count_change factory method."""
        test = DataQualityTest.row_count_change(
            test_id="test_row_count",
            name="Row count stable",
            table="orders",
            max_change_percent=10.0,
            source_investigation_id=investigation_id,
            failure_description="Row count changed dramatically",
        )

        assert test.assertion_type == AssertionType.ROW_COUNT_CHANGE
        assert test.column is None
        assert test.parameters["max_change_percent"] == 10.0
        assert test.severity == "warn"  # default for row count

    def test_freshness_factory(self, investigation_id: "uuid4") -> None:
        """Test freshness factory method."""
        test = DataQualityTest.freshness(
            test_id="test_freshness",
            name="Data freshness",
            table="orders",
            column="created_at",
            max_age_hours=24.0,
            source_investigation_id=investigation_id,
            failure_description="Data is stale",
        )

        assert test.assertion_type == AssertionType.FRESHNESS
        assert test.parameters["max_age_hours"] == 24.0
        assert test.threshold is not None
        assert test.threshold.unit == "hours"

    def test_custom_sql_factory(self, investigation_id: "uuid4") -> None:
        """Test custom_sql factory method."""
        sql = "SELECT * FROM orders WHERE total != subtotal + tax"
        test = DataQualityTest.custom_sql(
            test_id="test_total_calculation",
            name="Total calculation check",
            table="orders",
            sql_expression=sql,
            description="Order total should equal subtotal plus tax",
            source_investigation_id=investigation_id,
            failure_description="Found orders with wrong totals",
        )

        assert test.assertion_type == AssertionType.CUSTOM_SQL
        assert test.sql_expression == sql

    def test_referential_integrity_factory(self, investigation_id: "uuid4") -> None:
        """Test referential_integrity factory method."""
        test = DataQualityTest.referential_integrity(
            test_id="test_user_fk",
            name="User foreign key valid",
            table="orders",
            column="user_id",
            reference_table="users",
            reference_column="id",
            source_investigation_id=investigation_id,
            failure_description="Found orphaned user_id values",
        )

        assert test.assertion_type == AssertionType.REFERENTIAL_INTEGRITY
        assert test.parameters["reference_table"] == "users"
        assert test.parameters["reference_column"] == "id"

    def test_factory_with_custom_description(self, investigation_id: "uuid4") -> None:
        """Test factory method with custom description."""
        custom_desc = "This is my custom description for this test"
        test = DataQualityTest.not_null(
            test_id="test_1",
            name="Test",
            table="t",
            column="c",
            description=custom_desc,
            source_investigation_id=investigation_id,
            failure_description="Some failure description",
        )

        assert test.description == custom_desc

    def test_factory_with_tags(self, investigation_id: "uuid4") -> None:
        """Test factory method with tags."""
        test = DataQualityTest.not_null(
            test_id="test_1",
            name="Test",
            table="t",
            column="c",
            tags=["critical", "finance"],
            source_investigation_id=investigation_id,
            failure_description="Some failure description",
        )

        assert test.tags == ["critical", "finance"]

    def test_factory_with_threshold(self, investigation_id: "uuid4") -> None:
        """Test not_null factory with threshold."""
        test = DataQualityTest.not_null(
            test_id="test_1",
            name="Test",
            table="t",
            column="c",
            threshold=TestThreshold.percentage(1.0),
            source_investigation_id=investigation_id,
            failure_description="Some failure description",
        )

        assert test.threshold is not None
        assert test.threshold.value == 1.0


class TestExtractTestsFromSynthesis:
    """Tests for extract_tests_from_synthesis function."""

    @pytest.fixture
    def investigation_id(self) -> "uuid4":
        """Create a sample investigation ID."""
        return uuid4()

    @pytest.fixture
    def mock_synthesis_null(self) -> MagicMock:
        """Create a mock synthesis response for NULL values issue."""
        from unittest.mock import MagicMock

        synthesis = MagicMock()
        synthesis.root_cause = "NULL values introduced in user_id column due to ETL failure"
        synthesis.confidence = 0.85
        synthesis.causal_chain = [
            "ETL job failed at 03:14 UTC",
            "users table not updated",
            "orders.user_id column has NULL values",
        ]
        synthesis.supporting_evidence = ["Found 485 NULL values in user_id column"]
        return synthesis

    @pytest.fixture
    def mock_synthesis_row_count(self) -> MagicMock:
        """Create a mock synthesis response for row count issue."""
        from unittest.mock import MagicMock

        synthesis = MagicMock()
        synthesis.root_cause = "Row count dropped by 50% due to missing upstream data"
        synthesis.confidence = 0.9
        synthesis.causal_chain = [
            "Upstream source returned empty response",
            "Missing rows in staging table",
            "Row count dropped dramatically",
        ]
        synthesis.supporting_evidence = ["Row count: 1000 expected, 500 actual"]
        return synthesis

    @pytest.fixture
    def mock_synthesis_freshness(self) -> MagicMock:
        """Create a mock synthesis response for freshness issue."""
        from unittest.mock import MagicMock

        synthesis = MagicMock()
        synthesis.root_cause = "Stale data in orders table, not updated for 48 hours"
        synthesis.confidence = 0.75
        synthesis.causal_chain = [
            "Scheduler was paused",
            "ETL job didn't run",
            "Data became stale",
        ]
        synthesis.supporting_evidence = ["Last update: 48 hours ago"]
        return synthesis

    @pytest.fixture
    def mock_synthesis_duplicate(self) -> MagicMock:
        """Create a mock synthesis response for duplicate issue."""
        from unittest.mock import MagicMock

        synthesis = MagicMock()
        synthesis.root_cause = "Duplicate order_id values found due to retry logic bug"
        synthesis.confidence = 0.8
        synthesis.causal_chain = [
            "Retry logic caused double inserts",
            "order_id column has duplicate values",
        ]
        synthesis.supporting_evidence = ["Found 150 duplicate order_id values"]
        return synthesis

    @pytest.fixture
    def mock_synthesis_low_confidence(self) -> MagicMock:
        """Create a mock synthesis response with low confidence."""
        from unittest.mock import MagicMock

        synthesis = MagicMock()
        synthesis.root_cause = "Some issue detected"
        synthesis.confidence = 0.5  # Below threshold
        synthesis.causal_chain = ["Step 1", "Step 2"]
        synthesis.supporting_evidence = []
        return synthesis

    @pytest.fixture
    def mock_synthesis_unexpected_values(self) -> MagicMock:
        """Create a mock synthesis response for unexpected values."""
        from unittest.mock import MagicMock

        synthesis = MagicMock()
        synthesis.root_cause = "Unexpected value 'INVALID' in status column"
        synthesis.confidence = 0.85
        synthesis.causal_chain = [
            "API returned new status code",
            "Validation not updated",
            "Invalid status in database",
        ]
        synthesis.supporting_evidence = [
            "Expected values: active, inactive, pending",
            "Found: INVALID",
        ]
        return synthesis

    def test_extract_null_test(
        self, investigation_id: "uuid4", mock_synthesis_null: MagicMock
    ) -> None:
        """Test extraction of NOT_NULL test from synthesis."""
        from dataing.core.codify import extract_tests_from_synthesis

        tests = extract_tests_from_synthesis(
            synthesis=mock_synthesis_null,
            investigation_id=investigation_id,
            table="orders",
            column="user_id",
        )

        assert len(tests) >= 1
        null_tests = [t for t in tests if t.assertion_type == AssertionType.NOT_NULL]
        assert len(null_tests) == 1
        assert null_tests[0].column == "user_id"
        assert null_tests[0].table == "orders"
        assert "auto-generated" in null_tests[0].tags

    def test_extract_row_count_test(
        self, investigation_id: "uuid4", mock_synthesis_row_count: MagicMock
    ) -> None:
        """Test extraction of ROW_COUNT_CHANGE test from synthesis."""
        from dataing.core.codify import extract_tests_from_synthesis

        tests = extract_tests_from_synthesis(
            synthesis=mock_synthesis_row_count,
            investigation_id=investigation_id,
            table="orders",
        )

        assert len(tests) >= 1
        rc_tests = [t for t in tests if t.assertion_type == AssertionType.ROW_COUNT_CHANGE]
        assert len(rc_tests) == 1
        assert rc_tests[0].table == "orders"
        assert rc_tests[0].is_table_level

    def test_extract_freshness_test(
        self, investigation_id: "uuid4", mock_synthesis_freshness: MagicMock
    ) -> None:
        """Test extraction of FRESHNESS test from synthesis."""
        from dataing.core.codify import extract_tests_from_synthesis

        tests = extract_tests_from_synthesis(
            synthesis=mock_synthesis_freshness,
            investigation_id=investigation_id,
            table="orders",
        )

        assert len(tests) >= 1
        fresh_tests = [t for t in tests if t.assertion_type == AssertionType.FRESHNESS]
        assert len(fresh_tests) == 1
        assert fresh_tests[0].table == "orders"

    def test_extract_unique_test(
        self, investigation_id: "uuid4", mock_synthesis_duplicate: MagicMock
    ) -> None:
        """Test extraction of UNIQUE test from synthesis."""
        from dataing.core.codify import extract_tests_from_synthesis

        tests = extract_tests_from_synthesis(
            synthesis=mock_synthesis_duplicate,
            investigation_id=investigation_id,
            table="orders",
            column="order_id",
        )

        assert len(tests) >= 1
        unique_tests = [t for t in tests if t.assertion_type == AssertionType.UNIQUE]
        assert len(unique_tests) == 1
        assert unique_tests[0].column == "order_id"

    def test_no_tests_below_confidence_threshold(
        self, investigation_id: "uuid4", mock_synthesis_low_confidence: MagicMock
    ) -> None:
        """Test that no tests are generated below confidence threshold."""
        from dataing.core.codify import extract_tests_from_synthesis

        tests = extract_tests_from_synthesis(
            synthesis=mock_synthesis_low_confidence,
            investigation_id=investigation_id,
            table="orders",
        )

        assert len(tests) == 0

    def test_extract_accepted_values_test(
        self, investigation_id: "uuid4", mock_synthesis_unexpected_values: MagicMock
    ) -> None:
        """Test extraction of ACCEPTED_VALUES test from synthesis."""
        from dataing.core.codify import extract_tests_from_synthesis

        tests = extract_tests_from_synthesis(
            synthesis=mock_synthesis_unexpected_values,
            investigation_id=investigation_id,
            table="users",
            column="status",
        )

        assert len(tests) >= 1
        av_tests = [t for t in tests if t.assertion_type == AssertionType.ACCEPTED_VALUES]
        assert len(av_tests) == 1
        assert av_tests[0].column == "status"
        assert "values" in av_tests[0].parameters

    def test_no_root_cause_returns_empty(self, investigation_id: "uuid4") -> None:
        """Test that no tests are generated when root_cause is None."""
        from unittest.mock import MagicMock

        from dataing.core.codify import extract_tests_from_synthesis

        synthesis = MagicMock()
        synthesis.root_cause = None
        synthesis.confidence = 0.9
        synthesis.causal_chain = []
        synthesis.supporting_evidence = []

        tests = extract_tests_from_synthesis(
            synthesis=synthesis,
            investigation_id=investigation_id,
            table="orders",
        )

        assert len(tests) == 0

    def test_fallback_to_custom_sql(self, investigation_id: "uuid4") -> None:
        """Test fallback to CUSTOM_SQL for unmatched patterns."""
        from unittest.mock import MagicMock

        from dataing.core.codify import extract_tests_from_synthesis

        synthesis = MagicMock()
        synthesis.root_cause = "Complex issue with no clear pattern"
        synthesis.confidence = 0.8
        synthesis.causal_chain = ["Step 1", "Step 2"]
        synthesis.supporting_evidence = []

        tests = extract_tests_from_synthesis(
            synthesis=synthesis,
            investigation_id=investigation_id,
            table="orders",
        )

        assert len(tests) == 1
        assert tests[0].assertion_type == AssertionType.CUSTOM_SQL
        assert tests[0].sql_expression is not None


class TestPatternMatchers:
    """Tests for pattern matching helper functions."""

    def test_matches_null_pattern(self) -> None:
        """Test NULL pattern matching."""
        from dataing.core.codify import _matches_null_pattern

        assert _matches_null_pattern("null values found")
        assert _matches_null_pattern("missing value in column")
        assert _matches_null_pattern("column is empty")
        assert not _matches_null_pattern("everything is fine")

    def test_matches_row_count_pattern(self) -> None:
        """Test row count pattern matching."""
        from dataing.core.codify import _matches_row_count_pattern

        assert _matches_row_count_pattern("row count dropped")
        assert _matches_row_count_pattern("volume drop detected")
        assert _matches_row_count_pattern("missing records")
        assert not _matches_row_count_pattern("data looks good")

    def test_matches_freshness_pattern(self) -> None:
        """Test freshness pattern matching."""
        from dataing.core.codify import _matches_freshness_pattern

        assert _matches_freshness_pattern("stale data")
        assert _matches_freshness_pattern("data is outdated")
        assert _matches_freshness_pattern("late arriving data")
        assert not _matches_freshness_pattern("fresh data")

    def test_matches_duplicate_pattern(self) -> None:
        """Test duplicate pattern matching."""
        from dataing.core.codify import _matches_duplicate_pattern

        assert _matches_duplicate_pattern("duplicate records")
        assert _matches_duplicate_pattern("not unique values")
        assert _matches_duplicate_pattern("repeated entries")
        assert not _matches_duplicate_pattern("unique values")


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_extract_accepted_values(self) -> None:
        """Test extracting accepted values from evidence."""
        from dataing.core.codify import _extract_accepted_values

        evidence = [
            "Found invalid value",
            "Expected values: active, inactive, pending",
        ]
        values = _extract_accepted_values(evidence)

        assert len(values) == 3
        assert "active" in values
        assert "inactive" in values
        assert "pending" in values

    def test_extract_accepted_values_empty(self) -> None:
        """Test extracting accepted values when not present."""
        from dataing.core.codify import _extract_accepted_values

        evidence = ["No values mentioned here"]
        values = _extract_accepted_values(evidence)

        assert len(values) == 0

    def test_extract_column_from_synthesis(self) -> None:
        """Test extracting column name from synthesis."""
        from unittest.mock import MagicMock

        from dataing.core.codify import _extract_column_from_synthesis

        synthesis = MagicMock()
        synthesis.root_cause = "NULL in column user_id"
        synthesis.causal_chain = []

        column = _extract_column_from_synthesis(synthesis)
        assert column == "user_id"

    def test_extract_column_from_table_dot_column(self) -> None:
        """Test extracting column from table.column format."""
        from unittest.mock import MagicMock

        from dataing.core.codify import _extract_column_from_synthesis

        synthesis = MagicMock()
        synthesis.root_cause = "Issue in orders.status"
        synthesis.causal_chain = []

        column = _extract_column_from_synthesis(synthesis)
        assert column == "status"
