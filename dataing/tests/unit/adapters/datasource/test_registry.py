"""Tests for the adapter registry."""

import pytest
from dataing.adapters.datasource import (
    AdapterRegistry,
    get_registry,
    SourceType,
)


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
        registered = registry.registered_types

        # Should have at least the core adapters
        expected_types = [
            SourceType.POSTGRESQL,
            SourceType.DUCKDB,
            SourceType.MYSQL,
            SourceType.TRINO,
            SourceType.SNOWFLAKE,
            SourceType.BIGQUERY,
            SourceType.MONGODB,
            SourceType.SALESFORCE,
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

        from dataing.adapters.datasource import PostgresAdapter, DuckDBAdapter

        assert registry.get_adapter_class(SourceType.POSTGRESQL) == PostgresAdapter
        assert registry.get_adapter_class(SourceType.DUCKDB) == DuckDBAdapter
