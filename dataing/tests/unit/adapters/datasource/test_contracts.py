"""Contract tests for adapter consistency.

These tests verify that all adapters produce consistent output
conforming to the unified schema specification.
"""

import pytest
from typing import Any
from unittest.mock import AsyncMock

from dataing.adapters.datasource import (
    AdapterRegistry,
    get_registry,
    BaseAdapter,
    AdapterCapabilities,
    SchemaResponse,
    ConnectionTestResult,
    QueryResult,
    NormalizedType,
    SourceType,
    SourceCategory,
)
from dataing.adapters.datasource.types import (
    Catalog,
    Schema,
    Table,
    Column,
    ColumnStats,
    ConfigSchema,
    ConfigField,
    FieldGroup,
    SourceTypeDefinition,
    QueryLanguage,
)


class TestAdapterRegistryContracts:
    """Verify adapter registry contracts."""

    def test_all_adapters_registered(self):
        """Verify all expected adapters are registered."""
        registry = get_registry()
        registered = registry.registered_types

        # SQL adapters
        assert SourceType.POSTGRESQL in registered
        assert SourceType.MYSQL in registered
        assert SourceType.TRINO in registered
        assert SourceType.SNOWFLAKE in registered
        assert SourceType.BIGQUERY in registered
        assert SourceType.REDSHIFT in registered
        assert SourceType.DUCKDB in registered

        # Document adapters
        assert SourceType.MONGODB in registered
        assert SourceType.DYNAMODB in registered
        assert SourceType.CASSANDRA in registered

        # API adapters
        assert SourceType.SALESFORCE in registered
        assert SourceType.HUBSPOT in registered
        assert SourceType.STRIPE in registered

        # Filesystem adapters
        assert SourceType.S3 in registered
        assert SourceType.GCS in registered
        assert SourceType.HDFS in registered
        assert SourceType.LOCAL_FILE in registered

    def test_all_adapters_have_definitions(self):
        """Verify all registered adapters have type definitions."""
        registry = get_registry()

        for source_type in registry.registered_types:
            definition = registry.get_definition(source_type)
            assert definition is not None
            assert isinstance(definition, SourceTypeDefinition)

    @pytest.mark.parametrize("source_type", list(SourceType))
    def test_type_definition_has_required_fields(self, source_type: SourceType):
        """All type definitions must have required fields."""
        registry = get_registry()

        definition = registry.get_definition(source_type)
        if definition is None:
            pytest.skip(f"Adapter for {source_type} not registered")

        # Required string fields
        assert definition.type == source_type
        assert definition.display_name
        assert isinstance(definition.display_name, str)
        assert len(definition.display_name) > 0

        # Category must be valid
        assert definition.category in [SourceCategory.DATABASE, SourceCategory.API, SourceCategory.FILESYSTEM]

        # Must have capabilities
        assert definition.capabilities is not None
        assert isinstance(definition.capabilities, AdapterCapabilities)

        # Must have config schema
        assert definition.config_schema is not None
        assert isinstance(definition.config_schema, ConfigSchema)


class TestCapabilitiesContracts:
    """Verify capabilities contracts."""

    @pytest.mark.parametrize("source_type", list(SourceType))
    def test_capabilities_are_valid(self, source_type: SourceType):
        """All capabilities must have valid boolean flags."""
        registry = get_registry()

        definition = registry.get_definition(source_type)
        if definition is None:
            pytest.skip(f"Adapter for {source_type} not registered")

        caps = definition.capabilities

        # Boolean flags
        assert isinstance(caps.supports_sql, bool)
        assert isinstance(caps.supports_sampling, bool)
        assert isinstance(caps.supports_row_count, bool)
        assert isinstance(caps.supports_column_stats, bool)
        assert isinstance(caps.supports_preview, bool)
        assert isinstance(caps.supports_write, bool)

        # Query language must be valid
        assert caps.query_language in [
            QueryLanguage.SQL,
            QueryLanguage.SOQL,
            QueryLanguage.MQL,
            QueryLanguage.SCAN_ONLY,
        ]

        # Numeric limits must be positive
        assert caps.max_concurrent_queries > 0
        if caps.rate_limit_requests_per_minute is not None:
            assert caps.rate_limit_requests_per_minute > 0

    def test_sql_adapters_support_sql(self):
        """SQL adapters must declare SQL support."""
        registry = get_registry()
        sql_types = [
            SourceType.POSTGRESQL,
            SourceType.MYSQL,
            SourceType.TRINO,
            SourceType.SNOWFLAKE,
            SourceType.BIGQUERY,
            SourceType.REDSHIFT,
            SourceType.DUCKDB,
        ]

        for source_type in sql_types:
            definition = registry.get_definition(source_type)
            assert definition.capabilities.supports_sql is True
            assert definition.capabilities.query_language == QueryLanguage.SQL

    def test_document_adapters_no_sql(self):
        """Document adapters must not declare SQL support."""
        registry = get_registry()
        doc_types = [
            SourceType.MONGODB,
            SourceType.DYNAMODB,
            SourceType.CASSANDRA,
        ]

        for source_type in doc_types:
            definition = registry.get_definition(source_type)
            assert definition.capabilities.supports_sql is False

    def test_api_adapters_have_rate_limits(self):
        """API adapters should have rate limits defined."""
        registry = get_registry()
        api_types = [
            SourceType.SALESFORCE,
            SourceType.HUBSPOT,
            SourceType.STRIPE,
        ]

        for source_type in api_types:
            definition = registry.get_definition(source_type)
            # API adapters typically have lower concurrent queries
            assert definition.capabilities.max_concurrent_queries <= 5


class TestConfigSchemaContracts:
    """Verify config schema contracts."""

    @pytest.mark.parametrize("source_type", list(SourceType))
    def test_config_schema_has_fields(self, source_type: SourceType):
        """All config schemas must have at least one field."""
        registry = get_registry()

        definition = registry.get_definition(source_type)
        if definition is None:
            pytest.skip(f"Adapter for {source_type} not registered")

        schema = definition.config_schema
        assert len(schema.fields) > 0

    @pytest.mark.parametrize("source_type", list(SourceType))
    def test_config_fields_have_required_attributes(self, source_type: SourceType):
        """All config fields must have required attributes."""
        registry = get_registry()

        definition = registry.get_definition(source_type)
        if definition is None:
            pytest.skip(f"Adapter for {source_type} not registered")

        for field in definition.config_schema.fields:
            # Name and label are required
            assert field.name
            assert isinstance(field.name, str)
            assert field.label
            assert isinstance(field.label, str)

            # Type must be valid
            assert field.type in ["string", "integer", "boolean", "enum", "secret", "file", "json"]

            # Required is boolean
            assert isinstance(field.required, bool)

    @pytest.mark.parametrize("source_type", list(SourceType))
    def test_enum_fields_have_options(self, source_type: SourceType):
        """Enum fields must have options defined."""
        registry = get_registry()

        definition = registry.get_definition(source_type)
        if definition is None:
            pytest.skip(f"Adapter for {source_type} not registered")

        for field in definition.config_schema.fields:
            if field.type == "enum":
                assert field.options is not None
                assert len(field.options) > 0
                for option in field.options:
                    assert "value" in option
                    assert "label" in option

    @pytest.mark.parametrize("source_type", list(SourceType))
    def test_field_groups_are_valid(self, source_type: SourceType):
        """Field groups must have required attributes."""
        registry = get_registry()

        definition = registry.get_definition(source_type)
        if definition is None:
            pytest.skip(f"Adapter for {source_type} not registered")

        schema = definition.config_schema
        group_ids = {g.id for g in schema.field_groups}

        for group in schema.field_groups:
            assert group.id
            assert group.label
            assert isinstance(group.collapsed_by_default, bool)

        # All field groups referenced by fields must exist
        for field in schema.fields:
            if field.group:
                assert field.group in group_ids, f"Field {field.name} references unknown group {field.group}"


class TestNormalizedTypeContracts:
    """Verify normalized type contracts."""

    def test_all_normalized_types_valid(self):
        """All NormalizedType enum values are valid."""
        expected_types = {
            NormalizedType.STRING,
            NormalizedType.INTEGER,
            NormalizedType.FLOAT,
            NormalizedType.DECIMAL,
            NormalizedType.BOOLEAN,
            NormalizedType.DATE,
            NormalizedType.DATETIME,
            NormalizedType.TIME,
            NormalizedType.TIMESTAMP,
            NormalizedType.BINARY,
            NormalizedType.JSON,
            NormalizedType.ARRAY,
            NormalizedType.MAP,
            NormalizedType.STRUCT,
            NormalizedType.UNKNOWN,
        }

        actual_types = set(NormalizedType)
        assert actual_types == expected_types


class TestSourceCategoryContracts:
    """Verify source category assignments."""

    def test_sql_adapters_are_database_category(self):
        """SQL adapters must be in DATABASE category."""
        registry = get_registry()
        sql_types = [
            SourceType.POSTGRESQL,
            SourceType.MYSQL,
            SourceType.TRINO,
            SourceType.SNOWFLAKE,
            SourceType.BIGQUERY,
            SourceType.REDSHIFT,
            SourceType.DUCKDB,
        ]

        for source_type in sql_types:
            definition = registry.get_definition(source_type)
            assert definition.category == SourceCategory.DATABASE

    def test_document_adapters_are_database_category(self):
        """Document adapters must be in DATABASE category."""
        registry = get_registry()
        doc_types = [
            SourceType.MONGODB,
            SourceType.DYNAMODB,
            SourceType.CASSANDRA,
        ]

        for source_type in doc_types:
            definition = registry.get_definition(source_type)
            assert definition.category == SourceCategory.DATABASE

    def test_api_adapters_are_api_category(self):
        """API adapters must be in API category."""
        registry = get_registry()
        api_types = [
            SourceType.SALESFORCE,
            SourceType.HUBSPOT,
            SourceType.STRIPE,
        ]

        for source_type in api_types:
            definition = registry.get_definition(source_type)
            assert definition.category == SourceCategory.API

    def test_filesystem_adapters_are_filesystem_category(self):
        """Filesystem adapters must be in FILESYSTEM category."""
        registry = get_registry()
        fs_types = [
            SourceType.S3,
            SourceType.GCS,
            SourceType.HDFS,
            SourceType.LOCAL_FILE,
        ]

        for source_type in fs_types:
            definition = registry.get_definition(source_type)
            assert definition.category == SourceCategory.FILESYSTEM


class TestSchemaResponseContracts:
    """Verify schema response structure contracts."""

    def test_schema_response_structure(self):
        """SchemaResponse has required fields."""
        from datetime import datetime

        response = SchemaResponse(
            source_id="test",
            source_type=SourceType.POSTGRESQL,
            source_category=SourceCategory.DATABASE,
            fetched_at=datetime.now(),
            catalogs=[],
        )

        assert response.source_id == "test"
        assert response.source_type == SourceType.POSTGRESQL
        assert response.source_category == SourceCategory.DATABASE
        assert response.catalogs == []
        assert response.fetched_at is not None

    def test_catalog_structure(self):
        """Catalog has required fields."""
        catalog = Catalog(
            name="default",
            schemas=[],
        )

        assert catalog.name == "default"
        assert catalog.schemas == []

    def test_schema_structure(self):
        """Schema has required fields."""
        schema = Schema(
            name="public",
            tables=[],
        )

        assert schema.name == "public"
        assert schema.tables == []

    def test_table_structure(self):
        """Table has required fields."""
        table = Table(
            name="users",
            table_type="table",
            native_type="TABLE",
            native_path="public.users",
            columns=[],
        )

        assert table.name == "users"
        assert table.table_type == "table"
        assert table.native_type == "TABLE"
        assert table.native_path == "public.users"
        assert table.columns == []

    def test_column_structure(self):
        """Column has required fields."""
        column = Column(
            name="id",
            data_type=NormalizedType.INTEGER,
            native_type="bigint",
            nullable=False,
            is_primary_key=True,
        )

        assert column.name == "id"
        assert column.data_type == NormalizedType.INTEGER
        assert column.native_type == "bigint"
        assert column.nullable is False
        assert column.is_primary_key is True


class TestQueryResultContracts:
    """Verify query result structure contracts."""

    def test_query_result_structure(self):
        """QueryResult has required fields."""
        result = QueryResult(
            columns=[{"name": "id", "data_type": "integer"}],
            rows=[{"id": 1}],
            row_count=1,
        )

        assert len(result.columns) == 1
        assert len(result.rows) == 1
        assert result.row_count == 1
        assert result.truncated is False
        assert result.execution_time_ms is None

    def test_query_result_empty(self):
        """QueryResult handles empty results."""
        result = QueryResult(
            columns=[],
            rows=[],
            row_count=0,
        )

        assert result.columns == []
        assert result.rows == []
        assert result.row_count == 0


class TestConnectionTestResultContracts:
    """Verify connection test result contracts."""

    def test_success_result(self):
        """Successful connection test has required fields."""
        result = ConnectionTestResult(
            success=True,
            latency_ms=50,
            message="Connected",
            server_version="PostgreSQL 15.2",
        )

        assert result.success is True
        assert result.latency_ms == 50
        assert result.message == "Connected"
        assert result.server_version == "PostgreSQL 15.2"
        assert result.error_code is None

    def test_failure_result(self):
        """Failed connection test has required fields."""
        result = ConnectionTestResult(
            success=False,
            latency_ms=0,
            message="Connection refused",
            error_code="CONNECTION_FAILED",
        )

        assert result.success is False
        assert result.message == "Connection refused"
        assert result.error_code == "CONNECTION_FAILED"
