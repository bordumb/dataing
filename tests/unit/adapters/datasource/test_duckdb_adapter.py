"""Tests for the DuckDB adapter."""

import os
import tempfile
import pytest
from dataing.adapters.datasource import DuckDBAdapter, SourceType, NormalizedType


@pytest.fixture
def memory_adapter():
    """Create a DuckDB adapter with in-memory database."""
    return DuckDBAdapter({"path": ":memory:", "source_type": "database", "read_only": False})


@pytest.fixture
async def connected_adapter(memory_adapter):
    """Create and connect a DuckDB adapter."""
    await memory_adapter.connect()
    yield memory_adapter
    await memory_adapter.disconnect()


class TestDuckDBAdapter:
    """Tests for DuckDBAdapter."""

    def test_source_type(self, memory_adapter):
        """Test source type is correct."""
        assert memory_adapter.source_type == SourceType.DUCKDB

    def test_capabilities(self, memory_adapter):
        """Test capabilities are correct."""
        caps = memory_adapter.capabilities
        assert caps.supports_sql is True
        assert caps.supports_sampling is True
        assert caps.supports_row_count is True
        assert caps.supports_preview is True

    @pytest.mark.asyncio
    async def test_connect(self, memory_adapter):
        """Test connecting to DuckDB."""
        assert memory_adapter.is_connected is False
        await memory_adapter.connect()
        assert memory_adapter.is_connected is True
        await memory_adapter.disconnect()
        assert memory_adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_context_manager(self, memory_adapter):
        """Test async context manager."""
        assert memory_adapter.is_connected is False
        async with memory_adapter:
            assert memory_adapter.is_connected is True
        assert memory_adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_test_connection(self, connected_adapter):
        """Test connection testing."""
        result = await connected_adapter.test_connection()
        assert result.success is True
        assert result.latency_ms is not None
        assert "DuckDB" in result.server_version

    @pytest.mark.asyncio
    async def test_execute_query(self, connected_adapter):
        """Test executing a query."""
        result = await connected_adapter.execute_query("SELECT 1 as num, 'hello' as text")
        assert result.row_count == 1
        assert len(result.columns) == 2
        assert result.rows[0]["num"] == 1
        assert result.rows[0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_execute_query_multiple_rows(self, connected_adapter):
        """Test executing query with multiple rows."""
        # Create a table and insert data
        await connected_adapter.execute_query(
            "CREATE TABLE test_table (id INTEGER, name VARCHAR)"
        )
        await connected_adapter.execute_query(
            "INSERT INTO test_table VALUES (1, 'Alice'), (2, 'Bob'), (3, 'Charlie')"
        )

        result = await connected_adapter.execute_query("SELECT * FROM test_table")
        assert result.row_count == 3
        assert len(result.columns) == 2

    @pytest.mark.asyncio
    async def test_get_schema(self, connected_adapter):
        """Test schema discovery."""
        # Create a table
        await connected_adapter.execute_query(
            "CREATE TABLE users (id INTEGER, name VARCHAR, created_at TIMESTAMP)"
        )

        schema = await connected_adapter.get_schema()
        assert schema.source_type == SourceType.DUCKDB
        assert len(schema.catalogs) >= 1

        # Find the users table
        found = False
        for catalog in schema.catalogs:
            for db_schema in catalog.schemas:
                for table in db_schema.tables:
                    if table.name == "users":
                        found = True
                        assert len(table.columns) == 3
        assert found, "users table not found in schema"

    @pytest.mark.asyncio
    async def test_schema_filter(self, connected_adapter):
        """Test schema filter."""
        await connected_adapter.execute_query("CREATE TABLE orders (id INTEGER)")
        await connected_adapter.execute_query("CREATE TABLE products (id INTEGER)")

        from dataing.adapters.datasource import SchemaFilter

        # Filter by table pattern
        filter = SchemaFilter(table_pattern="orders")
        schema = await connected_adapter.get_schema(filter)

        # Should find orders but not products
        found_tables = []
        for catalog in schema.catalogs:
            for db_schema in catalog.schemas:
                for table in db_schema.tables:
                    found_tables.append(table.name)

        # The filter uses LIKE, so 'orders' should match
        assert any("orders" in t for t in found_tables)


class TestDuckDBDirectoryMode:
    """Tests for DuckDB directory mode."""

    @pytest.mark.asyncio
    async def test_directory_mode_with_parquet(self):
        """Test reading parquet files from directory."""
        # Create a temporary directory with a parquet file
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a parquet file using DuckDB
            import duckdb

            conn = duckdb.connect(":memory:")
            conn.execute(
                f"COPY (SELECT 1 as id, 'test' as name) TO '{tmpdir}/test.parquet'"
            )
            conn.close()

            # Create adapter in directory mode
            adapter = DuckDBAdapter({
                "path": tmpdir,
                "source_type": "directory",
            })

            async with adapter:
                result = await adapter.test_connection()
                assert result.success is True

                # The parquet file should be registered as a view
                schema = await adapter.get_schema()
                assert len(schema.catalogs) >= 1

    @pytest.mark.asyncio
    async def test_directory_mode_with_csv(self):
        """Test reading CSV files from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a CSV file
            csv_path = os.path.join(tmpdir, "data.csv")
            with open(csv_path, "w") as f:
                f.write("id,name\n1,Alice\n2,Bob\n")

            adapter = DuckDBAdapter({
                "path": tmpdir,
                "source_type": "directory",
            })

            async with adapter:
                result = await adapter.test_connection()
                assert result.success is True


class TestDuckDBAdapterErrors:
    """Tests for DuckDB adapter error handling."""

    @pytest.mark.asyncio
    async def test_connect_file_not_found(self):
        """Test connect raises error for non-existent database file."""
        from dataing.adapters.datasource.errors import ConnectionFailedError

        adapter = DuckDBAdapter({
            "path": "/nonexistent/path/to/db.duckdb",
            "source_type": "database",
        })

        with pytest.raises(ConnectionFailedError) as exc_info:
            await adapter.connect()
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_query_not_connected(self):
        """Test execute_query fails when not connected."""
        from dataing.adapters.datasource.errors import ConnectionFailedError

        adapter = DuckDBAdapter({"path": ":memory:", "source_type": "database"})

        with pytest.raises(ConnectionFailedError):
            await adapter.execute_query("SELECT 1")

    @pytest.mark.asyncio
    async def test_execute_query_syntax_error(self, connected_adapter):
        """Test execute_query raises QuerySyntaxError for bad SQL."""
        from dataing.adapters.datasource.errors import QuerySyntaxError

        with pytest.raises(QuerySyntaxError):
            await connected_adapter.execute_query("SELEC * FROM users")

    @pytest.mark.asyncio
    async def test_get_schema_not_connected(self):
        """Test get_schema fails when not connected."""
        from dataing.adapters.datasource.errors import ConnectionFailedError

        adapter = DuckDBAdapter({"path": ":memory:", "source_type": "database"})

        with pytest.raises(ConnectionFailedError):
            await adapter.get_schema()


class TestDuckDBAdapterTypeMapping:
    """Tests for DuckDB type mapping."""

    @pytest.mark.asyncio
    async def test_map_duckdb_type_integer(self, connected_adapter):
        """Test integer type mapping."""
        result = await connected_adapter.execute_query("SELECT 1 as num")
        assert result.columns[0]["data_type"] == "integer"

    @pytest.mark.asyncio
    async def test_map_duckdb_type_string(self, connected_adapter):
        """Test string type mapping."""
        result = await connected_adapter.execute_query("SELECT 'hello' as text")
        assert result.columns[0]["data_type"] == "string"

    @pytest.mark.asyncio
    async def test_map_duckdb_type_boolean(self, connected_adapter):
        """Test boolean type mapping."""
        result = await connected_adapter.execute_query("SELECT true as flag")
        assert result.columns[0]["data_type"] == "boolean"


class TestDuckDBAdapterSampling:
    """Tests for DuckDB sampling functionality."""

    def test_build_sample_query(self):
        """Test sample query uses DuckDB-specific syntax."""
        adapter = DuckDBAdapter({"path": ":memory:", "source_type": "database"})
        query = adapter._build_sample_query("users", 100)

        assert "SELECT * FROM users" in query
        assert "USING SAMPLE 100 ROWS" in query

    @pytest.mark.asyncio
    async def test_sample_method(self, connected_adapter):
        """Test sample method works correctly."""
        await connected_adapter.execute_query(
            "CREATE TABLE sample_test (id INTEGER, value VARCHAR)"
        )
        await connected_adapter.execute_query(
            "INSERT INTO sample_test SELECT i, 'val' || i FROM range(100) t(i)"
        )

        result = await connected_adapter.sample("sample_test", n=10)
        assert result.row_count <= 10

    @pytest.mark.asyncio
    async def test_preview_method(self, connected_adapter):
        """Test preview method works correctly."""
        await connected_adapter.execute_query(
            "CREATE TABLE preview_test (id INTEGER)"
        )
        await connected_adapter.execute_query(
            "INSERT INTO preview_test SELECT i FROM range(50) t(i)"
        )

        result = await connected_adapter.preview("preview_test", n=10)
        assert result.row_count == 10


class TestDuckDBAdapterQueryLimit:
    """Tests for query result limiting."""

    @pytest.mark.asyncio
    async def test_execute_query_with_limit(self, connected_adapter):
        """Test execute_query respects limit parameter."""
        await connected_adapter.execute_query(
            "CREATE TABLE limit_test (id INTEGER)"
        )
        await connected_adapter.execute_query(
            "INSERT INTO limit_test SELECT i FROM range(100) t(i)"
        )

        result = await connected_adapter.execute_query(
            "SELECT * FROM limit_test",
            limit=10,
        )

        assert result.row_count <= 10
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_execute_query_empty_result(self, connected_adapter):
        """Test execute_query with no results."""
        await connected_adapter.execute_query("CREATE TABLE empty_table (id INTEGER)")

        result = await connected_adapter.execute_query("SELECT * FROM empty_table")

        assert result.row_count == 0
        # DuckDB still returns column info even for empty results
        assert len(result.columns) >= 1
        assert result.rows == []
