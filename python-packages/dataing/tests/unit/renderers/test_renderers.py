"""Tests for data quality test renderers."""

import json
from uuid import UUID

import pytest

from dataing.core.codify import AssertionThreshold, DataQualityTest
from dataing.renderers import (
    DbtRenderer,
    GXRenderer,
    RenderFormat,
    SodaRenderer,
    SQLRenderer,
    get_renderer,
)


# Fixtures
@pytest.fixture
def investigation_id() -> UUID:
    """Sample investigation ID."""
    return UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def not_null_test(investigation_id: UUID) -> DataQualityTest:
    """Sample NOT_NULL test."""
    return DataQualityTest.not_null(
        test_id="test_orders_customer_id_not_null",
        name="orders.customer_id not null",
        table="orders",
        column="customer_id",
        source_investigation_id=investigation_id,
        failure_description="NULL customer_id values detected in orders table",
    )


@pytest.fixture
def unique_test(investigation_id: UUID) -> DataQualityTest:
    """Sample UNIQUE test."""
    return DataQualityTest.unique(
        test_id="test_users_email_unique",
        name="users.email unique",
        table="users",
        column="email",
        source_investigation_id=investigation_id,
        failure_description="Duplicate email addresses found in users table",
    )


@pytest.fixture
def accepted_values_test(investigation_id: UUID) -> DataQualityTest:
    """Sample ACCEPTED_VALUES test."""
    return DataQualityTest.accepted_values(
        test_id="test_orders_status_values",
        name="orders.status accepted values",
        table="orders",
        column="status",
        values=["pending", "completed", "cancelled"],
        source_investigation_id=investigation_id,
        failure_description="Invalid status values found in orders",
    )


@pytest.fixture
def in_range_test(investigation_id: UUID) -> DataQualityTest:
    """Sample IN_RANGE test."""
    return DataQualityTest.in_range(
        test_id="test_products_price_range",
        name="products.price in range",
        table="products",
        column="price",
        min_value=0.0,
        max_value=10000.0,
        source_investigation_id=investigation_id,
        failure_description="Product prices outside expected range",
    )


@pytest.fixture
def row_count_test(investigation_id: UUID) -> DataQualityTest:
    """Sample ROW_COUNT_CHANGE test."""
    return DataQualityTest.row_count_change(
        test_id="test_orders_row_count",
        name="orders row count stability",
        table="orders",
        max_change_percent=10.0,
        source_investigation_id=investigation_id,
        failure_description="Order volume dropped unexpectedly",
    )


@pytest.fixture
def freshness_test(investigation_id: UUID) -> DataQualityTest:
    """Sample FRESHNESS test."""
    return DataQualityTest.freshness(
        test_id="test_events_freshness",
        name="events data freshness",
        table="events",
        column="created_at",
        max_age_hours=24.0,
        source_investigation_id=investigation_id,
        failure_description="Event data is stale",
    )


@pytest.fixture
def referential_test(investigation_id: UUID) -> DataQualityTest:
    """Sample REFERENTIAL_INTEGRITY test."""
    return DataQualityTest.referential_integrity(
        test_id="test_orders_customer_fk",
        name="orders.customer_id foreign key valid",
        table="orders",
        column="customer_id",
        reference_table="customers",
        reference_column="id",
        source_investigation_id=investigation_id,
        failure_description="Orphan orders found with missing customers",
    )


@pytest.fixture
def custom_sql_test(investigation_id: UUID) -> DataQualityTest:
    """Sample CUSTOM_SQL test."""
    return DataQualityTest.custom_sql(
        test_id="test_orders_custom",
        name="orders custom check",
        table="orders",
        sql_expression="SELECT * FROM orders WHERE total < 0",
        description="Order totals should never be negative",
        source_investigation_id=investigation_id,
        failure_description="Negative order totals found",
    )


@pytest.fixture
def all_tests(
    not_null_test: DataQualityTest,
    unique_test: DataQualityTest,
    accepted_values_test: DataQualityTest,
    in_range_test: DataQualityTest,
    row_count_test: DataQualityTest,
    freshness_test: DataQualityTest,
    referential_test: DataQualityTest,
    custom_sql_test: DataQualityTest,
) -> list[DataQualityTest]:
    """All sample tests."""
    return [
        not_null_test,
        unique_test,
        accepted_values_test,
        in_range_test,
        row_count_test,
        freshness_test,
        referential_test,
        custom_sql_test,
    ]


# Base Renderer Tests
class TestBaseRenderer:
    """Tests for BaseRenderer."""

    def test_format_provenance_comment(self, not_null_test: DataQualityTest) -> None:
        """Test provenance comment formatting."""
        renderer = GXRenderer()  # Use concrete impl
        comment = renderer._format_provenance_comment(not_null_test, prefix="#")

        assert "Generated by Dataing" in comment
        assert str(not_null_test.source_investigation_id) in comment
        assert not_null_test.name in comment


# Get Renderer Tests
class TestGetRenderer:
    """Tests for get_renderer function."""

    def test_get_gx_renderer(self) -> None:
        """Test getting GX renderer."""
        renderer = get_renderer("gx")
        assert isinstance(renderer, GXRenderer)
        assert renderer.format == RenderFormat.GX

    def test_get_dbt_renderer(self) -> None:
        """Test getting dbt renderer."""
        renderer = get_renderer("dbt")
        assert isinstance(renderer, DbtRenderer)
        assert renderer.format == RenderFormat.DBT

    def test_get_soda_renderer(self) -> None:
        """Test getting Soda renderer."""
        renderer = get_renderer("soda")
        assert isinstance(renderer, SodaRenderer)
        assert renderer.format == RenderFormat.SODA

    def test_get_sql_renderer(self) -> None:
        """Test getting SQL renderer."""
        renderer = get_renderer("sql")
        assert isinstance(renderer, SQLRenderer)
        assert renderer.format == RenderFormat.SQL

    def test_get_renderer_by_enum(self) -> None:
        """Test getting renderer by enum."""
        renderer = get_renderer(RenderFormat.GX)
        assert isinstance(renderer, GXRenderer)

    def test_get_renderer_invalid(self) -> None:
        """Test getting invalid renderer raises error."""
        with pytest.raises(ValueError, match="Unsupported format"):
            get_renderer("invalid")


# GX Renderer Tests
class TestGXRenderer:
    """Tests for Great Expectations renderer."""

    def test_format(self) -> None:
        """Test renderer format."""
        renderer = GXRenderer()
        assert renderer.format == RenderFormat.GX

    def test_render_not_null(self, not_null_test: DataQualityTest) -> None:
        """Test rendering NOT_NULL expectation."""
        renderer = GXRenderer()
        result = renderer.render(not_null_test)
        expectation = json.loads(result)

        assert expectation["expectation_type"] == "expect_column_values_to_not_be_null"
        assert expectation["kwargs"]["column"] == "customer_id"
        assert expectation["meta"]["generated_by"] == "dataing"

    def test_render_unique(self, unique_test: DataQualityTest) -> None:
        """Test rendering UNIQUE expectation."""
        renderer = GXRenderer()
        result = renderer.render(unique_test)
        expectation = json.loads(result)

        assert expectation["expectation_type"] == "expect_column_values_to_be_unique"
        assert expectation["kwargs"]["column"] == "email"

    def test_render_accepted_values(self, accepted_values_test: DataQualityTest) -> None:
        """Test rendering ACCEPTED_VALUES expectation."""
        renderer = GXRenderer()
        result = renderer.render(accepted_values_test)
        expectation = json.loads(result)

        assert expectation["expectation_type"] == "expect_column_values_to_be_in_set"
        assert expectation["kwargs"]["value_set"] == ["pending", "completed", "cancelled"]

    def test_render_in_range(self, in_range_test: DataQualityTest) -> None:
        """Test rendering IN_RANGE expectation."""
        renderer = GXRenderer()
        result = renderer.render(in_range_test)
        expectation = json.loads(result)

        assert expectation["expectation_type"] == "expect_column_values_to_be_between"
        assert expectation["kwargs"]["min_value"] == 0.0
        assert expectation["kwargs"]["max_value"] == 10000.0

    def test_render_custom_sql(self, custom_sql_test: DataQualityTest) -> None:
        """Test rendering CUSTOM_SQL expectation."""
        renderer = GXRenderer()
        result = renderer.render(custom_sql_test)
        expectation = json.loads(result)

        assert expectation["expectation_type"] == "expect_query_to_return_no_rows"
        assert "SELECT * FROM orders WHERE total < 0" in expectation["kwargs"]["query"]

    def test_render_many_creates_suite(
        self, not_null_test: DataQualityTest, unique_test: DataQualityTest
    ) -> None:
        """Test rendering multiple tests as expectation suite."""
        renderer = GXRenderer()
        result = renderer.render_many([not_null_test, unique_test])
        suite = json.loads(result)

        assert "meta" in suite
        assert suite["meta"]["generated_by"] == "dataing"
        assert len(suite["expectations"]) == 2

    def test_render_python(self, not_null_test: DataQualityTest) -> None:
        """Test rendering as Python code."""
        renderer = GXRenderer()
        result = renderer.render_python(not_null_test)

        assert "validator.expect(" in result
        assert '"expect_column_values_to_not_be_null"' in result
        assert 'column="customer_id"' in result

    def test_render_not_null_with_threshold(self, investigation_id: UUID) -> None:
        """Test NOT_NULL with threshold renders mostly parameter."""
        test = DataQualityTest.not_null(
            test_id="test_with_threshold",
            name="test with threshold",
            table="orders",
            column="optional_field",
            source_investigation_id=investigation_id,
            failure_description="Some nulls allowed",
            threshold=AssertionThreshold.percentage(5.0),  # Allow 5% nulls
        )
        renderer = GXRenderer()
        result = renderer.render(test)
        expectation = json.loads(result)

        assert expectation["kwargs"]["mostly"] == 0.95


# dbt Renderer Tests
class TestDbtRenderer:
    """Tests for dbt renderer."""

    def test_format(self) -> None:
        """Test renderer format."""
        renderer = DbtRenderer()
        assert renderer.format == RenderFormat.DBT

    def test_render_not_null(self, not_null_test: DataQualityTest) -> None:
        """Test rendering NOT_NULL test."""
        renderer = DbtRenderer()
        result = renderer.render(not_null_test)

        assert "# Generated by Dataing" in result
        assert "columns:" in result
        assert "- name: customer_id" in result
        assert "- not_null:" in result

    def test_render_unique(self, unique_test: DataQualityTest) -> None:
        """Test rendering UNIQUE test."""
        renderer = DbtRenderer()
        result = renderer.render(unique_test)

        assert "- unique:" in result

    def test_render_accepted_values(self, accepted_values_test: DataQualityTest) -> None:
        """Test rendering ACCEPTED_VALUES test."""
        renderer = DbtRenderer()
        result = renderer.render(accepted_values_test)

        assert "- accepted_values:" in result
        assert "pending" in result
        assert "completed" in result

    def test_render_referential(self, referential_test: DataQualityTest) -> None:
        """Test rendering REFERENTIAL_INTEGRITY test."""
        renderer = DbtRenderer()
        result = renderer.render(referential_test)

        assert "- relationships:" in result
        assert "customers" in result

    def test_render_many_groups_by_table(
        self, not_null_test: DataQualityTest, accepted_values_test: DataQualityTest
    ) -> None:
        """Test render_many groups tests by table."""
        renderer = DbtRenderer()
        result = renderer.render_many([not_null_test, accepted_values_test])

        # Should have version and models
        assert "version: 2" in result
        assert "models:" in result
        # Both tests are on 'orders' table
        assert result.count("- name: orders") == 1

    def test_severity_config(self, not_null_test: DataQualityTest) -> None:
        """Test severity configuration."""
        renderer = DbtRenderer()
        result = renderer.render(not_null_test)

        # Default severity is 'fail' -> 'error' in dbt
        assert "severity: error" in result


# Soda Renderer Tests
class TestSodaRenderer:
    """Tests for Soda renderer."""

    def test_format(self) -> None:
        """Test renderer format."""
        renderer = SodaRenderer()
        assert renderer.format == RenderFormat.SODA

    def test_render_not_null(self, not_null_test: DataQualityTest) -> None:
        """Test rendering NOT_NULL check."""
        renderer = SodaRenderer()
        result = renderer.render(not_null_test)

        assert "# Generated by Dataing" in result
        assert "checks for orders:" in result
        assert "missing_count(customer_id) = 0" in result

    def test_render_unique(self, unique_test: DataQualityTest) -> None:
        """Test rendering UNIQUE check."""
        renderer = SodaRenderer()
        result = renderer.render(unique_test)

        assert "duplicate_count(email) = 0" in result

    def test_render_freshness(self, freshness_test: DataQualityTest) -> None:
        """Test rendering FRESHNESS check."""
        renderer = SodaRenderer()
        result = renderer.render(freshness_test)

        assert "freshness(created_at) < 24h" in result

    def test_render_referential(self, referential_test: DataQualityTest) -> None:
        """Test rendering REFERENTIAL_INTEGRITY check."""
        renderer = SodaRenderer()
        result = renderer.render(referential_test)

        assert "reference(customer_id, customers, id)" in result

    def test_render_many_groups_by_table(
        self, not_null_test: DataQualityTest, unique_test: DataQualityTest
    ) -> None:
        """Test render_many groups checks by table."""
        renderer = SodaRenderer()
        result = renderer.render_many([not_null_test, unique_test])

        # Should group by table
        assert "checks for orders:" in result
        assert "checks for users:" in result

    def test_check_name_includes_investigation(self, not_null_test: DataQualityTest) -> None:
        """Test check name includes investigation reference."""
        renderer = SodaRenderer()
        result = renderer.render(not_null_test)

        # Should include truncated investigation ID
        assert "(from inv_12345678)" in result


# SQL Renderer Tests
class TestSQLRenderer:
    """Tests for SQL renderer."""

    def test_format(self) -> None:
        """Test renderer format."""
        renderer = SQLRenderer()
        assert renderer.format == RenderFormat.SQL

    def test_render_not_null(self, not_null_test: DataQualityTest) -> None:
        """Test rendering NOT_NULL query."""
        renderer = SQLRenderer()
        result = renderer.render(not_null_test)

        assert "-- Generated by Dataing" in result
        assert "SELECT COUNT(*) AS null_count" in result
        assert "FROM orders" in result
        assert "WHERE customer_id IS NULL" in result
        assert "-- EXPECTED: 0 rows" in result

    def test_render_unique(self, unique_test: DataQualityTest) -> None:
        """Test rendering UNIQUE query."""
        renderer = SQLRenderer()
        result = renderer.render(unique_test)

        assert "SELECT email, COUNT(*) AS duplicate_count" in result
        assert "GROUP BY email" in result
        assert "HAVING COUNT(*) > 1" in result

    def test_render_accepted_values(self, accepted_values_test: DataQualityTest) -> None:
        """Test rendering ACCEPTED_VALUES query."""
        renderer = SQLRenderer()
        result = renderer.render(accepted_values_test)

        assert "NOT IN ('pending', 'completed', 'cancelled')" in result

    def test_render_in_range(self, in_range_test: DataQualityTest) -> None:
        """Test rendering IN_RANGE query."""
        renderer = SQLRenderer()
        result = renderer.render(in_range_test)

        assert "price < 0.0 OR price > 10000.0" in result

    def test_render_freshness(self, freshness_test: DataQualityTest) -> None:
        """Test rendering FRESHNESS query."""
        renderer = SQLRenderer()
        result = renderer.render(freshness_test)

        assert "MAX(created_at)" in result
        assert "age_hours" in result
        assert "24" in result

    def test_render_referential(self, referential_test: DataQualityTest) -> None:
        """Test rendering REFERENTIAL_INTEGRITY query."""
        renderer = SQLRenderer()
        result = renderer.render(referential_test)

        assert "LEFT JOIN customers" in result
        assert "orphan_count" in result
        assert "ref.id IS NULL" in result

    def test_render_custom_sql(self, custom_sql_test: DataQualityTest) -> None:
        """Test rendering CUSTOM_SQL query."""
        renderer = SQLRenderer()
        result = renderer.render(custom_sql_test)

        assert "SELECT * FROM orders WHERE total < 0" in result

    def test_render_many_with_headers(
        self, not_null_test: DataQualityTest, unique_test: DataQualityTest
    ) -> None:
        """Test render_many includes headers and separators."""
        renderer = SQLRenderer()
        result = renderer.render_many([not_null_test, unique_test])

        assert "-- Generated by Dataing" in result
        assert "-- Test 1:" in result
        assert "-- Test 2:" in result


# Integration Tests
class TestRendererIntegration:
    """Integration tests for all renderers."""

    def test_all_renderers_handle_all_assertion_types(
        self, all_tests: list[DataQualityTest]
    ) -> None:
        """Verify all renderers can handle all assertion types."""
        renderers = [GXRenderer(), DbtRenderer(), SodaRenderer(), SQLRenderer()]

        for renderer in renderers:
            for test in all_tests:
                # Should not raise
                result = renderer.render(test)
                assert result, f"{renderer.__class__.__name__} failed on {test.assertion_type}"
                assert len(result) > 0

    def test_render_many_empty_list(self) -> None:
        """Test rendering empty list produces valid output."""
        renderers = [GXRenderer(), DbtRenderer(), SodaRenderer(), SQLRenderer()]

        for renderer in renderers:
            result = renderer.render_many([])
            assert result is not None

    def test_provenance_included_in_all_formats(self, not_null_test: DataQualityTest) -> None:
        """Test all renderers include provenance information."""
        renderers = [GXRenderer(), DbtRenderer(), SodaRenderer(), SQLRenderer()]

        for renderer in renderers:
            result = renderer.render(not_null_test)

            # Each should reference the investigation ID in some form
            inv_id = str(not_null_test.source_investigation_id)
            assert (
                inv_id in result or inv_id[:8] in result
            ), f"{renderer.__class__.__name__} missing provenance"
