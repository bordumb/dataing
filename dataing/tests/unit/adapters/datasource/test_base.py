"""Tests for BaseAdapter abstract base class."""

import pytest
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    Column,
    ConnectionTestResult,
    NormalizedType,
    QueryLanguage,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
)


class ConcreteAdapter(BaseAdapter):
    """Concrete implementation for testing BaseAdapter."""

    def __init__(self, config: dict[str, Any], source_type: SourceType = SourceType.POSTGRESQL):
        super().__init__(config)
        self._source_type = source_type
        self._connected_flag = False

    @property
    def source_type(self) -> SourceType:
        return self._source_type

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_sql=True,
            supports_sampling=True,
            query_language=QueryLanguage.SQL,
        )

    async def connect(self) -> None:
        self._connected = True
        self._connected_flag = True

    async def disconnect(self) -> None:
        self._connected = False
        self._connected_flag = False

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            success=True,
            latency_ms=10,
            message="Connected",
        )

    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        return self._build_schema_response(
            source_id="test",
            catalogs=[
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": "public",
                            "tables": [
                                {
                                    "name": "users",
                                    "table_type": "table",
                                    "native_type": "TABLE",
                                    "native_path": "public.users",
                                    "columns": [
                                        {
                                            "name": "id",
                                            "data_type": NormalizedType.INTEGER,
                                            "native_type": "bigint",
                                            "nullable": False,
                                            "is_primary_key": True,
                                            "is_partition_key": False,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        )


class TestBaseAdapter:
    """Tests for BaseAdapter base class functionality."""

    def test_init(self):
        """Test adapter initialization."""
        config = {"host": "localhost", "port": 5432}
        adapter = ConcreteAdapter(config)
        assert adapter._config == config
        assert adapter._connected is False

    def test_is_connected_property(self):
        """Test is_connected property."""
        adapter = ConcreteAdapter({})
        assert adapter.is_connected is False
        adapter._connected = True
        assert adapter.is_connected is True

    def test_source_type_property(self):
        """Test source_type property."""
        adapter = ConcreteAdapter({}, source_type=SourceType.MYSQL)
        assert adapter.source_type == SourceType.MYSQL

    def test_capabilities_property(self):
        """Test capabilities property."""
        adapter = ConcreteAdapter({})
        caps = adapter.capabilities
        assert caps.supports_sql is True
        assert caps.supports_sampling is True
        assert caps.query_language == QueryLanguage.SQL


class TestBaseAdapterContextManager:
    """Tests for BaseAdapter async context manager."""

    @pytest.mark.asyncio
    async def test_aenter(self):
        """Test __aenter__ calls connect."""
        adapter = ConcreteAdapter({})
        result = await adapter.__aenter__()
        assert result is adapter
        assert adapter.is_connected is True

    @pytest.mark.asyncio
    async def test_aexit(self):
        """Test __aexit__ calls disconnect."""
        adapter = ConcreteAdapter({})
        await adapter.connect()
        assert adapter.is_connected is True
        await adapter.__aexit__(None, None, None)
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_context_manager_usage(self):
        """Test using adapter as context manager."""
        async with ConcreteAdapter({}) as adapter:
            assert adapter.is_connected is True
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test context manager properly disconnects on exception."""
        adapter = ConcreteAdapter({})
        try:
            async with adapter:
                assert adapter.is_connected is True
                raise ValueError("Test error")
        except ValueError:
            pass
        assert adapter.is_connected is False


class TestBuildSchemaResponse:
    """Tests for _build_schema_response helper method."""

    @pytest.mark.asyncio
    async def test_build_schema_response_basic(self):
        """Test building a basic schema response."""
        adapter = ConcreteAdapter({})
        response = await adapter.get_schema()

        assert response.source_id == "test"
        assert response.source_type == SourceType.POSTGRESQL
        assert response.source_category == SourceCategory.DATABASE
        assert isinstance(response.fetched_at, datetime)
        assert len(response.catalogs) == 1

    @pytest.mark.asyncio
    async def test_build_schema_response_catalog_structure(self):
        """Test catalog structure in schema response."""
        adapter = ConcreteAdapter({})
        response = await adapter.get_schema()

        catalog = response.catalogs[0]
        assert catalog.name == "default"
        assert len(catalog.schemas) == 1

        schema = catalog.schemas[0]
        assert schema.name == "public"
        assert len(schema.tables) == 1

    @pytest.mark.asyncio
    async def test_build_schema_response_table_structure(self):
        """Test table structure in schema response."""
        adapter = ConcreteAdapter({})
        response = await adapter.get_schema()

        table = response.catalogs[0].schemas[0].tables[0]
        assert table.name == "users"
        assert table.table_type == "table"
        assert table.native_type == "TABLE"
        assert table.native_path == "public.users"
        assert len(table.columns) == 1

    @pytest.mark.asyncio
    async def test_build_schema_response_column_structure(self):
        """Test column structure in schema response."""
        adapter = ConcreteAdapter({})
        response = await adapter.get_schema()

        column = response.catalogs[0].schemas[0].tables[0].columns[0]
        assert column.name == "id"
        assert column.data_type == NormalizedType.INTEGER
        assert column.native_type == "bigint"
        assert column.nullable is False
        assert column.is_primary_key is True

    def test_build_schema_response_with_optional_fields(self):
        """Test schema response with optional table fields."""
        adapter = ConcreteAdapter({})
        response = adapter._build_schema_response(
            source_id="test",
            catalogs=[
                {
                    "name": "catalog1",
                    "schemas": [
                        {
                            "name": "schema1",
                            "tables": [
                                {
                                    "name": "table1",
                                    "row_count": 1000,
                                    "size_bytes": 102400,
                                    "description": "Test table",
                                    "columns": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        table = response.catalogs[0].schemas[0].tables[0]
        assert table.row_count == 1000
        assert table.size_bytes == 102400
        assert table.description == "Test table"

    def test_build_schema_response_defaults(self):
        """Test schema response uses correct defaults."""
        adapter = ConcreteAdapter({})
        response = adapter._build_schema_response(
            source_id="test",
            catalogs=[
                {
                    "schemas": [
                        {
                            "tables": [
                                {
                                    "name": "minimal_table",
                                    "columns": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        catalog = response.catalogs[0]
        assert catalog.name == "default"

        schema = catalog.schemas[0]
        assert schema.name == "default"

        table = schema.tables[0]
        assert table.table_type == "table"
        assert table.native_type == "TABLE"
        assert table.native_path == "minimal_table"


class TestGetSourceCategory:
    """Tests for _get_source_category helper method."""

    def test_sql_database_category(self):
        """Test SQL databases return DATABASE category."""
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
            adapter = ConcreteAdapter({}, source_type=source_type)
            assert adapter._get_source_category() == SourceCategory.DATABASE

    def test_nosql_database_category(self):
        """Test NoSQL databases return DATABASE category."""
        nosql_types = [
            SourceType.MONGODB,
            SourceType.DYNAMODB,
            SourceType.CASSANDRA,
        ]
        for source_type in nosql_types:
            adapter = ConcreteAdapter({}, source_type=source_type)
            assert adapter._get_source_category() == SourceCategory.DATABASE

    def test_api_category(self):
        """Test APIs return API category."""
        api_types = [
            SourceType.SALESFORCE,
            SourceType.HUBSPOT,
            SourceType.STRIPE,
        ]
        for source_type in api_types:
            adapter = ConcreteAdapter({}, source_type=source_type)
            assert adapter._get_source_category() == SourceCategory.API

    def test_filesystem_category(self):
        """Test filesystems return FILESYSTEM category."""
        fs_types = [
            SourceType.S3,
            SourceType.GCS,
            SourceType.HDFS,
            SourceType.LOCAL_FILE,
        ]
        for source_type in fs_types:
            adapter = ConcreteAdapter({}, source_type=source_type)
            assert adapter._get_source_category() == SourceCategory.FILESYSTEM


class TestAbstractMethods:
    """Test that abstract methods must be implemented."""

    def test_cannot_instantiate_base_adapter(self):
        """Test that BaseAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            BaseAdapter({})
        assert "abstract" in str(exc_info.value).lower()

    def test_incomplete_implementation_fails(self):
        """Test that incomplete implementations fail to instantiate."""

        class IncompleteAdapter(BaseAdapter):
            @property
            def source_type(self) -> SourceType:
                return SourceType.POSTGRESQL

        with pytest.raises(TypeError):
            IncompleteAdapter({})
