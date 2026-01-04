"""Tests for APIAdapter base class."""

import pytest
from typing import Any

from dataing.adapters.datasource.api.base import APIAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    Column,
    ConnectionTestResult,
    NormalizedType,
    QueryLanguage,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceType,
    Table,
)


class ConcreteAPIAdapter(APIAdapter):
    """Concrete implementation for testing APIAdapter."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._query_results: list[QueryResult] = []
        self._query_index = 0

    @property
    def source_type(self) -> SourceType:
        return SourceType.SALESFORCE

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            success=True,
            latency_ms=50,
            message="Connected",
        )

    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        return self._build_schema_response(
            source_id="test",
            catalogs=[],
        )

    async def query_object(
        self,
        object_name: str,
        query: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Return mock results."""
        if self._query_results:
            result = self._query_results[self._query_index % len(self._query_results)]
            self._query_index += 1
            return result
        return QueryResult(
            columns=[
                {"name": "Id", "data_type": "string"},
                {"name": "Name", "data_type": "string"},
            ],
            rows=[
                {"Id": "001xx", "Name": "Acme Corp"},
            ],
            row_count=1,
        )

    async def describe_object(self, object_name: str) -> Table:
        """Return object description."""
        return Table(
            name=object_name,
            table_type="object",
            native_type="SALESFORCE_OBJECT",
            native_path=object_name,
            columns=[
                Column(
                    name="Id",
                    data_type=NormalizedType.STRING,
                    native_type="id",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="Name",
                    data_type=NormalizedType.STRING,
                    native_type="string",
                    nullable=True,
                ),
            ],
        )

    async def list_objects(self) -> list[str]:
        """Return list of objects."""
        return ["Account", "Contact", "Opportunity", "Lead"]

    def set_query_results(self, results: list[QueryResult]) -> None:
        """Set mock query results for testing."""
        self._query_results = results
        self._query_index = 0


class TestAPIAdapterCapabilities:
    """Tests for APIAdapter default capabilities."""

    def test_default_capabilities(self):
        """Test default capability values."""
        adapter = ConcreteAPIAdapter({})
        caps = adapter.capabilities

        assert caps.supports_sql is False
        assert caps.supports_sampling is True
        assert caps.supports_row_count is True
        assert caps.supports_column_stats is False
        assert caps.supports_preview is True
        assert caps.supports_write is False
        assert caps.rate_limit_requests_per_minute == 100
        assert caps.max_concurrent_queries == 1
        assert caps.query_language == QueryLanguage.SCAN_ONLY


class TestAPIAdapterQueryObject:
    """Tests for APIAdapter.query_object method."""

    @pytest.mark.asyncio
    async def test_query_object_basic(self):
        """Test basic object query."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()

        result = await adapter.query_object("Account")

        assert result.row_count >= 1
        assert len(result.columns) >= 2

    @pytest.mark.asyncio
    async def test_query_object_with_query(self):
        """Test object query with custom query."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()

        result = await adapter.query_object(
            "Account",
            query="SELECT Id, Name FROM Account WHERE IsActive = true",
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_query_object_with_limit(self):
        """Test object query with limit."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()

        result = await adapter.query_object("Account", limit=50)

        assert result is not None


class TestAPIAdapterDescribeObject:
    """Tests for APIAdapter.describe_object method."""

    @pytest.mark.asyncio
    async def test_describe_object_basic(self):
        """Test basic object description."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()

        table = await adapter.describe_object("Account")

        assert table.name == "Account"
        assert table.table_type == "object"
        assert len(table.columns) >= 2

    @pytest.mark.asyncio
    async def test_describe_object_columns(self):
        """Test object description has correct columns."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()

        table = await adapter.describe_object("Contact")

        # Check column properties
        id_col = next((c for c in table.columns if c.name == "Id"), None)
        assert id_col is not None
        assert id_col.is_primary_key is True
        assert id_col.data_type == NormalizedType.STRING


class TestAPIAdapterListObjects:
    """Tests for APIAdapter.list_objects method."""

    @pytest.mark.asyncio
    async def test_list_objects_basic(self):
        """Test listing available objects."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()

        objects = await adapter.list_objects()

        assert len(objects) >= 4
        assert "Account" in objects
        assert "Contact" in objects


class TestAPIAdapterPreview:
    """Tests for APIAdapter.preview method."""

    @pytest.mark.asyncio
    async def test_preview_calls_query_object(self):
        """Test that preview delegates to query_object."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()
        adapter.set_query_results([
            QueryResult(
                columns=[{"name": "Id", "data_type": "string"}],
                rows=[{"Id": "1"}, {"Id": "2"}, {"Id": "3"}],
                row_count=3,
            )
        ])

        result = await adapter.preview("Account", n=10)

        assert result.row_count == 3


class TestAPIAdapterSample:
    """Tests for APIAdapter.sample method."""

    @pytest.mark.asyncio
    async def test_sample_calls_query_object(self):
        """Test that sample delegates to query_object."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()
        adapter.set_query_results([
            QueryResult(
                columns=[{"name": "Id", "data_type": "string"}],
                rows=[{"Id": "abc"}, {"Id": "def"}],
                row_count=2,
            )
        ])

        result = await adapter.sample("Lead", n=50)

        # Sample returns first N records for APIs
        assert result.row_count == 2

    @pytest.mark.asyncio
    async def test_sample_with_different_objects(self):
        """Test sampling different objects."""
        adapter = ConcreteAPIAdapter({})
        await adapter.connect()

        result1 = await adapter.sample("Account", n=10)
        result2 = await adapter.sample("Contact", n=10)

        assert result1 is not None
        assert result2 is not None


class TestAPIAdapterAbstractMethods:
    """Test that abstract methods must be implemented."""

    def test_cannot_instantiate_api_adapter(self):
        """Test that APIAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            APIAdapter({})
        assert "abstract" in str(exc_info.value).lower()

    def test_incomplete_implementation_fails(self):
        """Test that incomplete implementations fail."""

        class IncompleteAPIAdapter(APIAdapter):
            @property
            def source_type(self) -> SourceType:
                return SourceType.SALESFORCE

        with pytest.raises(TypeError):
            IncompleteAPIAdapter({})
