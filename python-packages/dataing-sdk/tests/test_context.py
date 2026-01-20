"""Tests for SDK Context object."""

from datetime import datetime, UTC

import pytest

from dataing_sdk import (
    AssetRef,
    Context,
    ContextBundle,
    DataingClient,
    ResolvedAsset,
    ValidationError,
    from_sql,
)


class TestContext:
    """Tests for Context class."""

    def test_context_properties(self) -> None:
        """Test Context exposes bundle properties."""
        bundle = ContextBundle(
            bundle_id="test-bundle-123",
            resolved_assets=[
                ResolvedAsset(
                    asset=AssetRef(platform="postgres", name="db.schema.orders"),
                    datasource_id="ds-1",
                    dataset_id="postgres://db.schema.orders",
                    dataset_type="TABLE",
                )
            ],
            default_datasource_id="ds-1",
            lineage={"root": "postgres://db.schema.orders"},
            operational={"freshness": {}},
            anomalies=[],
            bundle_hash="abc123",
            expires_at=datetime.now(UTC),
        )
        client = DataingClient(api_key="test")
        ctx = Context(bundle, client)

        assert ctx.bundle_id == "test-bundle-123"
        assert ctx.bundle_hash == "abc123"
        assert len(ctx.resolved_assets) == 1
        assert ctx.resolved_assets[0].dataset_id == "postgres://db.schema.orders"
        assert ctx.default_datasource_id == "ds-1"
        assert ctx.lineage == {"root": "postgres://db.schema.orders"}
        assert ctx.operational == {"freshness": {}}
        assert ctx.anomalies == []

    def test_context_assets_property(self) -> None:
        """Test Context.assets returns original asset refs."""
        bundle = ContextBundle(
            bundle_id="test-bundle",
            resolved_assets=[
                ResolvedAsset(
                    asset=AssetRef(platform="postgres", name="db.schema.orders"),
                    datasource_id="ds-1",
                    dataset_id="postgres://db.schema.orders",
                ),
                ResolvedAsset(
                    asset=AssetRef(platform="postgres", name="db.schema.customers"),
                    datasource_id="ds-1",
                    dataset_id="postgres://db.schema.customers",
                ),
            ],
            bundle_hash="abc",
            expires_at=datetime.now(UTC),
        )
        client = DataingClient(api_key="test")
        ctx = Context(bundle, client)

        assets = ctx.assets
        assert len(assets) == 2
        assert assets[0].name == "db.schema.orders"
        assert assets[1].name == "db.schema.customers"

    def test_context_repr(self) -> None:
        """Test Context string representation."""
        bundle = ContextBundle(
            bundle_id="test-bundle-123456789",
            resolved_assets=[
                ResolvedAsset(
                    asset=AssetRef(platform="postgres", name="table"),
                    dataset_id="postgres://table",
                )
            ],
            bundle_hash="abc",
            expires_at=datetime.now(UTC),
        )
        client = DataingClient(api_key="test")
        ctx = Context(bundle, client)

        repr_str = repr(ctx)
        assert "test-bun" in repr_str  # First 8 chars
        assert "assets=1" in repr_str


class TestFromSql:
    """Tests for from_sql function."""

    def test_from_sql_requires_platform_or_datasource(self) -> None:
        """Test from_sql raises without platform or datasource_id."""
        with pytest.raises(ValidationError, match="requires either datasource_id"):
            from_sql("SELECT * FROM orders")

    def test_from_sql_with_default_platform(self) -> None:
        """Test from_sql with default_platform."""
        assets = from_sql(
            "SELECT * FROM orders",
            default_platform="postgres",
        )
        assert len(assets) == 1
        assert assets[0].platform == "postgres"
        assert assets[0].name == "orders"

    def test_from_sql_with_datasource_id(self) -> None:
        """Test from_sql with datasource_id."""
        assets = from_sql(
            "SELECT * FROM orders",
            datasource_id="ds-123",
            default_platform="postgres",
        )
        assert len(assets) == 1
        assert assets[0].datasource_id == "ds-123"

    def test_from_sql_multiple_tables(self) -> None:
        """Test from_sql extracts multiple tables."""
        assets = from_sql(
            "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id",
            default_platform="postgres",
        )
        assert len(assets) == 2
        names = {a.name for a in assets}
        assert "customers" in names
        assert "orders" in names

    def test_from_sql_qualified_names(self) -> None:
        """Test from_sql handles qualified table names."""
        assets = from_sql(
            "SELECT * FROM ecommerce.public.orders",
            default_platform="postgres",
        )
        assert len(assets) == 1
        assert assets[0].name == "ecommerce.public.orders"

    def test_from_sql_with_default_schema(self) -> None:
        """Test from_sql applies default_schema to unqualified tables."""
        assets = from_sql(
            "SELECT * FROM orders",
            default_platform="postgres",
            default_schema="public",
        )
        assert len(assets) == 1
        assert assets[0].name == "public.orders"

    def test_from_sql_with_default_database_and_schema(self) -> None:
        """Test from_sql applies default_database and default_schema."""
        assets = from_sql(
            "SELECT * FROM orders",
            default_platform="snowflake",
            default_database="analytics",
            default_schema="raw",
        )
        assert len(assets) == 1
        assert assets[0].name == "analytics.raw.orders"

    def test_from_sql_subquery(self) -> None:
        """Test from_sql extracts tables from subqueries."""
        assets = from_sql(
            "SELECT * FROM (SELECT * FROM orders) sub JOIN customers c ON sub.id = c.id",
            default_platform="postgres",
        )
        names = {a.name for a in assets}
        assert "orders" in names
        assert "customers" in names

    def test_from_sql_cte(self) -> None:
        """Test from_sql extracts tables from CTEs."""
        assets = from_sql(
            """
            WITH recent_orders AS (SELECT * FROM orders WHERE created_at > '2024-01-01')
            SELECT * FROM recent_orders r JOIN customers c ON r.customer_id = c.id
            """,
            default_platform="postgres",
        )
        names = {a.name for a in assets}
        assert "orders" in names
        assert "customers" in names
        # Note: CTE names may be included since they're referenced as tables
        # This is expected sqlglot behavior

    def test_from_sql_returns_sorted(self) -> None:
        """Test from_sql returns assets sorted by name."""
        assets = from_sql(
            "SELECT * FROM zebra, apple, mango",
            default_platform="postgres",
        )
        names = [a.name for a in assets]
        assert names == sorted(names)
