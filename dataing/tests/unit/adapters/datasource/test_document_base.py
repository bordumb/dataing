"""Tests for DocumentAdapter base class."""

import pytest
from typing import Any

from dataing.adapters.datasource.document.base import DocumentAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    ConnectionTestResult,
    QueryLanguage,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceType,
)


class ConcreteDocumentAdapter(DocumentAdapter):
    """Concrete implementation for testing DocumentAdapter."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._scan_results: list[QueryResult] = []
        self._scan_index = 0

    @property
    def source_type(self) -> SourceType:
        return SourceType.MONGODB

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            success=True,
            latency_ms=10,
            message="Connected",
        )

    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        return self._build_schema_response(
            source_id="test",
            catalogs=[],
        )

    async def scan_collection(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> QueryResult:
        """Return mock results."""
        if self._scan_results:
            result = self._scan_results[self._scan_index % len(self._scan_results)]
            self._scan_index += 1
            return result
        return QueryResult(
            columns=[{"name": "_id", "data_type": "string"}],
            rows=[{"_id": "abc123"}],
            row_count=1,
        )

    async def sample(
        self,
        collection: str,
        n: int = 100,
    ) -> QueryResult:
        """Return sample documents."""
        return await self.scan_collection(collection, limit=n)

    async def count_documents(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
    ) -> int:
        """Return document count."""
        return 100

    async def aggregate(
        self,
        collection: str,
        pipeline: list[dict[str, Any]],
    ) -> QueryResult:
        """Return aggregation results."""
        return QueryResult(
            columns=[{"name": "count", "data_type": "integer"}],
            rows=[{"count": 10}],
            row_count=1,
        )

    async def infer_schema(
        self,
        collection: str,
        sample_size: int = 100,
    ) -> dict[str, Any]:
        """Return inferred schema."""
        return {
            "_id": "string",
            "name": "string",
            "age": "integer",
        }

    def set_scan_results(self, results: list[QueryResult]) -> None:
        """Set mock scan results for testing."""
        self._scan_results = results
        self._scan_index = 0


class TestDocumentAdapterCapabilities:
    """Tests for DocumentAdapter default capabilities."""

    def test_default_capabilities(self):
        """Test default capability values."""
        adapter = ConcreteDocumentAdapter({})
        caps = adapter.capabilities

        assert caps.supports_sql is False
        assert caps.supports_sampling is True
        assert caps.supports_row_count is True
        assert caps.supports_column_stats is False
        assert caps.supports_preview is True
        assert caps.supports_write is False
        assert caps.query_language == QueryLanguage.SCAN_ONLY
        assert caps.max_concurrent_queries == 5


class TestDocumentAdapterScanCollection:
    """Tests for DocumentAdapter.scan_collection method."""

    @pytest.mark.asyncio
    async def test_scan_collection_basic(self):
        """Test basic collection scan."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        result = await adapter.scan_collection("users")

        assert result.row_count >= 1
        assert len(result.columns) >= 1

    @pytest.mark.asyncio
    async def test_scan_collection_with_filter(self):
        """Test collection scan with filter."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        result = await adapter.scan_collection(
            "users",
            filter={"active": True},
            limit=50,
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_scan_collection_with_skip(self):
        """Test collection scan with skip."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        result = await adapter.scan_collection(
            "users",
            skip=10,
            limit=20,
        )

        assert result is not None


class TestDocumentAdapterSample:
    """Tests for DocumentAdapter.sample method."""

    @pytest.mark.asyncio
    async def test_sample_basic(self):
        """Test basic sampling."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        result = await adapter.sample("users", n=10)

        assert result is not None
        assert result.row_count >= 0

    @pytest.mark.asyncio
    async def test_sample_with_custom_size(self):
        """Test sampling with custom size."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        result = await adapter.sample("users", n=50)

        assert result is not None


class TestDocumentAdapterPreview:
    """Tests for DocumentAdapter.preview method."""

    @pytest.mark.asyncio
    async def test_preview_calls_scan_collection(self):
        """Test that preview delegates to scan_collection."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()
        adapter.set_scan_results([
            QueryResult(
                columns=[{"name": "id", "data_type": "string"}],
                rows=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
                row_count=3,
            )
        ])

        result = await adapter.preview("users", n=10)

        assert result.row_count == 3


class TestDocumentAdapterCountDocuments:
    """Tests for DocumentAdapter.count_documents method."""

    @pytest.mark.asyncio
    async def test_count_documents_basic(self):
        """Test basic document count."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        count = await adapter.count_documents("users")

        assert count == 100

    @pytest.mark.asyncio
    async def test_count_documents_with_filter(self):
        """Test document count with filter."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        count = await adapter.count_documents("users", filter={"active": True})

        assert count >= 0


class TestDocumentAdapterAggregate:
    """Tests for DocumentAdapter.aggregate method."""

    @pytest.mark.asyncio
    async def test_aggregate_basic(self):
        """Test basic aggregation."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        result = await adapter.aggregate(
            "users",
            [{"$group": {"_id": "$status", "count": {"$sum": 1}}}],
        )

        assert result is not None
        assert result.row_count >= 0


class TestDocumentAdapterInferSchema:
    """Tests for DocumentAdapter.infer_schema method."""

    @pytest.mark.asyncio
    async def test_infer_schema_basic(self):
        """Test basic schema inference."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        schema = await adapter.infer_schema("users")

        assert "_id" in schema
        assert "name" in schema
        assert "age" in schema

    @pytest.mark.asyncio
    async def test_infer_schema_with_sample_size(self):
        """Test schema inference with custom sample size."""
        adapter = ConcreteDocumentAdapter({})
        await adapter.connect()

        schema = await adapter.infer_schema("users", sample_size=50)

        assert schema is not None


class TestDocumentAdapterAbstractMethods:
    """Test that abstract methods must be implemented."""

    def test_cannot_instantiate_document_adapter(self):
        """Test that DocumentAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            DocumentAdapter({})
        assert "abstract" in str(exc_info.value).lower()

    def test_incomplete_implementation_fails(self):
        """Test that incomplete implementations fail."""

        class IncompleteDocumentAdapter(DocumentAdapter):
            @property
            def source_type(self) -> SourceType:
                return SourceType.MONGODB

        with pytest.raises(TypeError):
            IncompleteDocumentAdapter({})
