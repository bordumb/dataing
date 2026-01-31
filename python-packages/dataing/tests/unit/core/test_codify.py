"""Tests for the codify module - DataQualityTest model."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from dataing.core.codify import (
    AssertionType,
    DataQualityTest,
    TestThreshold,
    ThresholdType,
)


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
