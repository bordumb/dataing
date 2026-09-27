"""Tests for the adapter registry."""

import inspect

import pytest
import sqlglot

from dataing.adapters.datasource import (
    AdapterRegistry,
    SourceType,
    get_registry,
)

# Registered adapters known to be abstract while their fix is in flight. strict=True
# fails the run as soon as one turns concrete, so an entry cannot outlive its bug.
_KNOWN_ABSTRACT: dict[SourceType, pytest.MarkDecorator] = {}


class TestAdapterRegistry:
    """Tests for AdapterRegistry singleton."""

    def test_singleton_pattern(self):
        """Verify registry is a singleton."""
        registry1 = AdapterRegistry.get_instance()
        registry2 = AdapterRegistry.get_instance()
        assert registry1 is registry2

    def test_get_registry_function(self):
        """Verify get_registry returns the singleton."""
        registry = get_registry()
        assert isinstance(registry, AdapterRegistry)
        assert registry is AdapterRegistry.get_instance()

    def test_registered_types(self):
        """Verify adapters are registered."""
        registry = get_registry()

        # Should have at least the core CE adapters
        # Note: Salesforce, HubSpot, Stripe are EE-only
        expected_types = [
            SourceType.POSTGRESQL,
            SourceType.DUCKDB,
            SourceType.MYSQL,
            SourceType.TRINO,
            SourceType.SNOWFLAKE,
            SourceType.BIGQUERY,
            SourceType.MONGODB,
            SourceType.S3,
        ]

        for source_type in expected_types:
            assert registry.is_registered(source_type), f"{source_type} not registered"

    def test_list_types(self):
        """Verify list_types returns definitions."""
        registry = get_registry()
        types_list = registry.list_types()

        assert len(types_list) > 0

        # Each type should have required fields
        for type_def in types_list:
            assert type_def.type is not None
            assert type_def.display_name is not None
            assert type_def.category is not None
            assert type_def.capabilities is not None
            assert type_def.config_schema is not None

    @pytest.mark.parametrize(
        "source_type",
        [
            pytest.param(
                type_def.type,
                id=type_def.type.value,
                marks=_KNOWN_ABSTRACT.get(type_def.type, ()),
            )
            for type_def in get_registry().list_types()
        ],
    )
    def test_registered_adapter_is_concrete(self, source_type: SourceType):
        """Every registered adapter implements all abstract methods, so create() works."""
        adapter_class = get_registry().get_adapter_class(source_type)

        assert adapter_class is not None
        assert not inspect.isabstract(adapter_class), (
            f"{adapter_class.__name__} is registered but abstract, missing: "
            f"{sorted(adapter_class.__abstractmethods__)}"
        )

    def test_get_definition(self):
        """Verify get_definition returns correct definition."""
        registry = get_registry()
        pg_def = registry.get_definition(SourceType.POSTGRESQL)

        assert pg_def is not None
        assert pg_def.type == SourceType.POSTGRESQL
        assert pg_def.display_name == "PostgreSQL"
        assert pg_def.capabilities.supports_sql is True

    def test_create_adapter(self):
        """Verify create returns adapter instance."""
        registry = get_registry()

        # Create a DuckDB adapter (doesn't need external connection)
        config = {"path": ":memory:", "source_type": "database"}
        adapter = registry.create(SourceType.DUCKDB, config)

        assert adapter is not None
        assert adapter.source_type == SourceType.DUCKDB

    def test_create_adapter_by_string(self):
        """Verify create works with string source type."""
        registry = get_registry()

        config = {"path": ":memory:", "source_type": "database"}
        adapter = registry.create("duckdb", config)

        assert adapter is not None
        assert adapter.source_type == SourceType.DUCKDB

    def test_create_unregistered_type_raises(self):
        """Verify creating unregistered type raises error."""
        registry = get_registry()

        with pytest.raises(ValueError) as exc_info:
            registry.create("nonexistent_type", {})

        assert "nonexistent_type" in str(exc_info.value)

    def test_is_registered(self):
        """Verify is_registered returns correct values."""
        registry = get_registry()

        assert registry.is_registered(SourceType.POSTGRESQL) is True
        assert registry.is_registered(SourceType.DUCKDB) is True

    def test_get_adapter_class(self):
        """Verify get_adapter_class returns correct class."""
        registry = get_registry()

        from dataing.adapters.datasource import DuckDBAdapter, PostgresAdapter

        assert registry.get_adapter_class(SourceType.POSTGRESQL) == PostgresAdapter
        assert registry.get_adapter_class(SourceType.DUCKDB) == DuckDBAdapter


class TestSqlDialects:
    """Tests that SQL sources declare the dialect their engine speaks."""

    @pytest.mark.parametrize(
        ("source_type", "dialect"),
        [
            (SourceType.POSTGRESQL, "postgres"),
            (SourceType.MYSQL, "mysql"),
            (SourceType.TRINO, "trino"),
            (SourceType.SNOWFLAKE, "snowflake"),
            (SourceType.BIGQUERY, "bigquery"),
            (SourceType.REDSHIFT, "redshift"),
            (SourceType.DUCKDB, "duckdb"),
            (SourceType.SQLITE, "sqlite"),
            # File sources are queried through DuckDB
            (SourceType.LOCAL_FILE, "duckdb"),
            (SourceType.S3, "duckdb"),
            (SourceType.GCS, "duckdb"),
            (SourceType.HDFS, "duckdb"),
        ],
    )
    def test_sql_dialect(self, source_type, dialect):
        """Verify each SQL source is validated in its engine's dialect."""
        type_def = get_registry().get_definition(source_type)

        assert type_def is not None
        assert type_def.capabilities.sql_dialect == dialect

    def test_every_sql_source_has_a_known_dialect(self):
        """Verify no SQL-capable source is registered without a parseable dialect."""
        for type_def in get_registry().list_types():
            if not type_def.capabilities.supports_sql:
                continue
            dialect = type_def.capabilities.sql_dialect
            assert dialect is not None, f"{type_def.type.value} has no sql_dialect"
            sqlglot.Dialect.get_or_raise(dialect)
