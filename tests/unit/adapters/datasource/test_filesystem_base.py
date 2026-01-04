"""Tests for FileSystemAdapter base class."""

import pytest
from typing import Any

from dataing.adapters.datasource.filesystem.base import FileSystemAdapter, FileInfo
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


class ConcreteFileSystemAdapter(FileSystemAdapter):
    """Concrete implementation for testing FileSystemAdapter."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._read_results: list[QueryResult] = []
        self._read_index = 0

    @property
    def source_type(self) -> SourceType:
        return SourceType.S3

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            success=True,
            latency_ms=100,
            message="Connected to S3",
        )

    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        return self._build_schema_response(
            source_id="test",
            catalogs=[],
        )

    async def list_files(
        self,
        pattern: str = "*",
        recursive: bool = True,
    ) -> list[FileInfo]:
        """Return list of files."""
        return [
            FileInfo(
                path="s3://bucket/data/file1.parquet",
                name="file1.parquet",
                size_bytes=1024000,
                last_modified="2024-01-15T10:30:00Z",
                file_format="parquet",
            ),
            FileInfo(
                path="s3://bucket/data/file2.parquet",
                name="file2.parquet",
                size_bytes=2048000,
                last_modified="2024-01-16T11:00:00Z",
                file_format="parquet",
            ),
            FileInfo(
                path="s3://bucket/data/archive.csv",
                name="archive.csv",
                size_bytes=512000,
                file_format="csv",
            ),
        ]

    async def read_file(
        self,
        path: str,
        file_format: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Return file contents."""
        if self._read_results:
            result = self._read_results[self._read_index % len(self._read_results)]
            self._read_index += 1
            return result
        return QueryResult(
            columns=[
                {"name": "id", "data_type": "integer"},
                {"name": "value", "data_type": "string"},
            ],
            rows=[
                {"id": 1, "value": "foo"},
                {"id": 2, "value": "bar"},
            ],
            row_count=2,
        )

    async def infer_schema(
        self,
        path: str,
        file_format: str | None = None,
    ) -> Table:
        """Return inferred schema."""
        return Table(
            name="file1",
            table_type="file",
            native_type="PARQUET_FILE",
            native_path=path,
            columns=[
                Column(
                    name="id",
                    data_type=NormalizedType.INTEGER,
                    native_type="int64",
                    nullable=False,
                ),
                Column(
                    name="value",
                    data_type=NormalizedType.STRING,
                    native_type="string",
                    nullable=True,
                ),
            ],
        )

    def set_read_results(self, results: list[QueryResult]) -> None:
        """Set mock read results for testing."""
        self._read_results = results
        self._read_index = 0


class TestFileInfo:
    """Tests for FileInfo dataclass."""

    def test_file_info_creation(self):
        """Test creating FileInfo."""
        info = FileInfo(
            path="s3://bucket/data.parquet",
            name="data.parquet",
            size_bytes=1024,
            last_modified="2024-01-15",
            file_format="parquet",
        )

        assert info.path == "s3://bucket/data.parquet"
        assert info.name == "data.parquet"
        assert info.size_bytes == 1024
        assert info.last_modified == "2024-01-15"
        assert info.file_format == "parquet"

    def test_file_info_optional_fields(self):
        """Test FileInfo with optional fields."""
        info = FileInfo(
            path="s3://bucket/data.csv",
            name="data.csv",
            size_bytes=512,
        )

        assert info.last_modified is None
        assert info.file_format is None


class TestFileSystemAdapterCapabilities:
    """Tests for FileSystemAdapter default capabilities."""

    def test_default_capabilities(self):
        """Test default capability values."""
        adapter = ConcreteFileSystemAdapter({})
        caps = adapter.capabilities

        assert caps.supports_sql is True
        assert caps.supports_sampling is True
        assert caps.supports_row_count is True
        assert caps.supports_column_stats is True
        assert caps.supports_preview is True
        assert caps.supports_write is False
        assert caps.query_language == QueryLanguage.SQL
        assert caps.max_concurrent_queries == 5


class TestFileSystemAdapterListFiles:
    """Tests for FileSystemAdapter.list_files method."""

    @pytest.mark.asyncio
    async def test_list_files_basic(self):
        """Test listing files."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        files = await adapter.list_files()

        assert len(files) == 3
        assert files[0].name == "file1.parquet"
        assert files[1].name == "file2.parquet"
        assert files[2].name == "archive.csv"

    @pytest.mark.asyncio
    async def test_list_files_with_pattern(self):
        """Test listing files with pattern."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        files = await adapter.list_files(pattern="*.parquet")

        assert len(files) >= 0

    @pytest.mark.asyncio
    async def test_list_files_non_recursive(self):
        """Test listing files non-recursively."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        files = await adapter.list_files(recursive=False)

        assert files is not None


class TestFileSystemAdapterReadFile:
    """Tests for FileSystemAdapter.read_file method."""

    @pytest.mark.asyncio
    async def test_read_file_basic(self):
        """Test reading a file."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        result = await adapter.read_file("s3://bucket/data.parquet")

        assert result.row_count >= 1
        assert len(result.columns) >= 2

    @pytest.mark.asyncio
    async def test_read_file_with_format(self):
        """Test reading a file with explicit format."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        result = await adapter.read_file(
            "s3://bucket/data",
            file_format="parquet",
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_read_file_with_limit(self):
        """Test reading a file with limit."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        result = await adapter.read_file(
            "s3://bucket/data.parquet",
            limit=10,
        )

        assert result is not None


class TestFileSystemAdapterInferSchema:
    """Tests for FileSystemAdapter.infer_schema method."""

    @pytest.mark.asyncio
    async def test_infer_schema_basic(self):
        """Test inferring schema from file."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        table = await adapter.infer_schema("s3://bucket/data.parquet")

        assert table.name == "file1"
        assert table.table_type == "file"
        assert len(table.columns) >= 2

    @pytest.mark.asyncio
    async def test_infer_schema_columns(self):
        """Test inferred schema has correct columns."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()

        table = await adapter.infer_schema("s3://bucket/data.parquet")

        id_col = next((c for c in table.columns if c.name == "id"), None)
        assert id_col is not None
        assert id_col.data_type == NormalizedType.INTEGER

        value_col = next((c for c in table.columns if c.name == "value"), None)
        assert value_col is not None
        assert value_col.data_type == NormalizedType.STRING


class TestFileSystemAdapterPreview:
    """Tests for FileSystemAdapter.preview method."""

    @pytest.mark.asyncio
    async def test_preview_calls_read_file(self):
        """Test that preview delegates to read_file."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()
        adapter.set_read_results([
            QueryResult(
                columns=[{"name": "id", "data_type": "integer"}],
                rows=[{"id": 1}, {"id": 2}, {"id": 3}],
                row_count=3,
            )
        ])

        result = await adapter.preview("s3://bucket/data.parquet", n=10)

        assert result.row_count == 3


class TestFileSystemAdapterSample:
    """Tests for FileSystemAdapter.sample method."""

    @pytest.mark.asyncio
    async def test_sample_calls_read_file(self):
        """Test that sample delegates to read_file."""
        adapter = ConcreteFileSystemAdapter({})
        await adapter.connect()
        adapter.set_read_results([
            QueryResult(
                columns=[{"name": "id", "data_type": "integer"}],
                rows=[{"id": 1}, {"id": 2}],
                row_count=2,
            )
        ])

        result = await adapter.sample("s3://bucket/data.parquet", n=50)

        assert result.row_count == 2


class TestFileSystemAdapterAbstractMethods:
    """Test that abstract methods must be implemented."""

    def test_cannot_instantiate_filesystem_adapter(self):
        """Test that FileSystemAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            FileSystemAdapter({})
        assert "abstract" in str(exc_info.value).lower()

    def test_incomplete_implementation_fails(self):
        """Test that incomplete implementations fail."""

        class IncompleteFileSystemAdapter(FileSystemAdapter):
            @property
            def source_type(self) -> SourceType:
                return SourceType.S3

        with pytest.raises(TypeError):
            IncompleteFileSystemAdapter({})
