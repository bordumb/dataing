"""Tests for data source type definitions."""

import pytest
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    Catalog,
    Column,
    ColumnStats,
    ConfigField,
    ConfigSchema,
    ConnectionTestResult,
    FieldGroup,
    NormalizedType,
    QueryLanguage,
    QueryResult,
    Schema,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
    SourceTypeDefinition,
    Table,
)


class TestNormalizedType:
    """Tests for NormalizedType enum."""

    def test_all_types_defined(self):
        """Verify all expected normalized types exist."""
        expected_types = [
            "string",
            "integer",
            "float",
            "decimal",
            "boolean",
            "date",
            "datetime",
            "time",
            "timestamp",
            "binary",
            "json",
            "array",
            "map",
            "struct",
            "unknown",
        ]
        for type_name in expected_types:
            assert hasattr(NormalizedType, type_name.upper())

    def test_type_values(self):
        """Verify type values match names."""
        assert NormalizedType.STRING.value == "string"
        assert NormalizedType.INTEGER.value == "integer"
        assert NormalizedType.TIMESTAMP.value == "timestamp"


class TestSourceType:
    """Tests for SourceType enum."""

    def test_sql_databases(self):
        """Verify SQL database types exist."""
        sql_types = ["POSTGRESQL", "MYSQL", "TRINO", "SNOWFLAKE", "BIGQUERY", "REDSHIFT", "DUCKDB"]
        for type_name in sql_types:
            assert hasattr(SourceType, type_name)

    def test_nosql_databases(self):
        """Verify NoSQL database types exist."""
        nosql_types = ["MONGODB", "DYNAMODB", "CASSANDRA"]
        for type_name in nosql_types:
            assert hasattr(SourceType, type_name)

    def test_api_sources(self):
        """Verify API source types exist."""
        api_types = ["SALESFORCE", "HUBSPOT", "STRIPE"]
        for type_name in api_types:
            assert hasattr(SourceType, type_name)

    def test_filesystem_sources(self):
        """Verify filesystem source types exist."""
        fs_types = ["S3", "GCS", "HDFS", "LOCAL_FILE"]
        for type_name in fs_types:
            assert hasattr(SourceType, type_name)


class TestColumn:
    """Tests for Column model."""

    def test_column_creation(self):
        """Test creating a column."""
        col = Column(
            name="id",
            data_type=NormalizedType.INTEGER,
            native_type="bigint",
            nullable=False,
            is_primary_key=True,
        )
        assert col.name == "id"
        assert col.data_type == NormalizedType.INTEGER
        assert col.native_type == "bigint"
        assert col.nullable is False
        assert col.is_primary_key is True
        assert col.is_partition_key is False

    def test_column_with_stats(self):
        """Test creating a column with statistics."""
        stats = ColumnStats(
            null_count=10,
            null_rate=0.1,
            distinct_count=100,
            min_value="1",
            max_value="1000",
            sample_values=["1", "50", "100"],
        )
        col = Column(
            name="value",
            data_type=NormalizedType.INTEGER,
            native_type="int",
            stats=stats,
        )
        assert col.stats is not None
        assert col.stats.null_count == 10
        assert col.stats.distinct_count == 100


class TestTable:
    """Tests for Table model."""

    def test_table_creation(self):
        """Test creating a table."""
        columns = [
            Column(name="id", data_type=NormalizedType.INTEGER, native_type="int"),
            Column(name="name", data_type=NormalizedType.STRING, native_type="varchar"),
        ]
        table = Table(
            name="users",
            table_type="table",
            native_type="TABLE",
            native_path="public.users",
            columns=columns,
            row_count=1000,
        )
        assert table.name == "users"
        assert table.table_type == "table"
        assert len(table.columns) == 2
        assert table.row_count == 1000


class TestSchemaResponse:
    """Tests for SchemaResponse model."""

    def test_schema_response_creation(self):
        """Test creating a schema response."""
        from datetime import datetime

        columns = [
            Column(name="id", data_type=NormalizedType.INTEGER, native_type="int"),
        ]
        tables = [
            Table(
                name="users",
                table_type="table",
                native_type="TABLE",
                native_path="public.users",
                columns=columns,
            )
        ]
        schemas = [Schema(name="public", tables=tables)]
        catalogs = [Catalog(name="default", schemas=schemas)]

        response = SchemaResponse(
            source_id="ds_123",
            source_type=SourceType.POSTGRESQL,
            source_category=SourceCategory.DATABASE,
            fetched_at=datetime.now(),
            catalogs=catalogs,
        )

        assert response.source_id == "ds_123"
        assert response.source_type == SourceType.POSTGRESQL
        assert len(response.catalogs) == 1
        assert len(response.catalogs[0].schemas) == 1
        assert len(response.catalogs[0].schemas[0].tables) == 1


class TestQueryResult:
    """Tests for QueryResult model."""

    def test_query_result_creation(self):
        """Test creating a query result."""
        columns = [
            {"name": "id", "data_type": "integer"},
            {"name": "name", "data_type": "string"},
        ]
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = QueryResult(
            columns=columns,
            rows=rows,
            row_count=2,
            execution_time_ms=50,
        )
        assert len(result.columns) == 2
        assert len(result.rows) == 2
        assert result.row_count == 2
        assert result.truncated is False


class TestConnectionTestResult:
    """Tests for ConnectionTestResult model."""

    def test_success_result(self):
        """Test successful connection result."""
        result = ConnectionTestResult(
            success=True,
            latency_ms=45,
            server_version="PostgreSQL 15.2",
            message="Connection successful",
        )
        assert result.success is True
        assert result.latency_ms == 45
        assert result.error_code is None

    def test_failure_result(self):
        """Test failed connection result."""
        result = ConnectionTestResult(
            success=False,
            message="Authentication failed",
            error_code="AUTHENTICATION_FAILED",
        )
        assert result.success is False
        assert result.error_code == "AUTHENTICATION_FAILED"


class TestConfigSchema:
    """Tests for ConfigSchema model."""

    def test_config_schema_creation(self):
        """Test creating a config schema."""
        field_groups = [
            FieldGroup(id="connection", label="Connection"),
            FieldGroup(id="auth", label="Authentication"),
        ]
        fields = [
            ConfigField(
                name="host",
                label="Host",
                type="string",
                required=True,
                group="connection",
            ),
            ConfigField(
                name="password",
                label="Password",
                type="secret",
                required=True,
                group="auth",
            ),
        ]
        schema = ConfigSchema(field_groups=field_groups, fields=fields)

        assert len(schema.field_groups) == 2
        assert len(schema.fields) == 2
        assert schema.fields[0].type == "string"
        assert schema.fields[1].type == "secret"


class TestAdapterCapabilities:
    """Tests for AdapterCapabilities model."""

    def test_default_capabilities(self):
        """Test default capability values."""
        caps = AdapterCapabilities()
        assert caps.supports_sql is False
        assert caps.supports_write is False
        assert caps.max_concurrent_queries == 1

    def test_sql_adapter_capabilities(self):
        """Test SQL adapter capabilities."""
        caps = AdapterCapabilities(
            supports_sql=True,
            supports_sampling=True,
            supports_row_count=True,
            supports_column_stats=True,
            query_language=QueryLanguage.SQL,
            max_concurrent_queries=10,
        )
        assert caps.supports_sql is True
        assert caps.query_language == QueryLanguage.SQL
        assert caps.max_concurrent_queries == 10
