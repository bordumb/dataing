"""DuckDB adapter implementation.

This module provides a DuckDB adapter that implements the unified
data source interface with full schema discovery and query capabilities.
DuckDB can also be used to query parquet files and other file formats.
"""

from __future__ import annotations

import os
import time
from typing import Any

from dataing.adapters.datasource.errors import (
    ConnectionFailedError,
    QuerySyntaxError,
    QueryTimeoutError,
    SchemaFetchFailedError,
)
from dataing.adapters.datasource.registry import register_adapter
from dataing.adapters.datasource.sql.base import SQLAdapter
from dataing.adapters.datasource.type_mapping import normalize_type
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    ConfigField,
    ConfigSchema,
    ConnectionTestResult,
    FieldGroup,
    QueryLanguage,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
)

DUCKDB_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="source", label="Data Source", collapsed_by_default=False),
    ],
    fields=[
        ConfigField(
            name="source_type",
            label="Source Type",
            type="enum",
            required=True,
            group="source",
            default_value="directory",
            options=[
                {"value": "directory", "label": "Directory of files"},
                {"value": "database", "label": "DuckDB database file"},
            ],
        ),
        ConfigField(
            name="path",
            label="Path",
            type="string",
            required=True,
            group="source",
            placeholder="/path/to/data or /path/to/db.duckdb",
            description="Path to directory with parquet/CSV files, or .duckdb file",
        ),
        ConfigField(
            name="read_only",
            label="Read Only",
            type="boolean",
            required=False,
            group="source",
            default_value=True,
            description="Open database in read-only mode",
        ),
    ],
)

DUCKDB_CAPABILITIES = AdapterCapabilities(
    supports_sql=True,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=True,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SQL,
    max_concurrent_queries=5,
)


@register_adapter(
    source_type=SourceType.DUCKDB,
    display_name="DuckDB",
    category=SourceCategory.DATABASE,
    icon="duckdb",
    description="Connect to DuckDB databases or query parquet/CSV files directly",
    capabilities=DUCKDB_CAPABILITIES,
    config_schema=DUCKDB_CONFIG_SCHEMA,
)
class DuckDBAdapter(SQLAdapter):
    """DuckDB database adapter.

    Provides schema discovery and query execution for DuckDB databases
    and direct file querying (parquet, CSV, etc.).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize DuckDB adapter.

        Args:
            config: Configuration dictionary with:
                - path: Path to database file or directory
                - source_type: "database" or "directory"
                - read_only: Whether to open read-only (default: True)
        """
        super().__init__(config)
        self._conn: Any = None
        self._source_id: str = ""
        self._is_directory_mode = config.get("source_type", "directory") == "directory"

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.DUCKDB

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return DUCKDB_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to DuckDB."""
        try:
            import duckdb
        except ImportError as e:
            raise ConnectionFailedError(
                message="duckdb is not installed. Install with: pip install duckdb",
                details={"error": str(e)},
            ) from e

        path = self._config.get("path", ":memory:")
        read_only = self._config.get("read_only", True)

        try:
            if self._is_directory_mode:
                # In directory mode, use in-memory database
                self._conn = duckdb.connect(":memory:")
                # Register parquet files as views
                await self._register_directory_files()
            elif path == ":memory:":
                # In-memory mode - cannot be read-only
                self._conn = duckdb.connect(":memory:")
            else:
                # Database file mode
                if not os.path.exists(path):
                    raise ConnectionFailedError(
                        message=f"Database file not found: {path}",
                        details={"path": path},
                    )
                self._conn = duckdb.connect(path, read_only=read_only)

            self._connected = True
        except Exception as e:
            if "ConnectionFailedError" in type(e).__name__:
                raise
            raise ConnectionFailedError(
                message=f"Failed to connect to DuckDB: {str(e)}",
                details={"error": str(e), "path": path},
            ) from e

    async def _register_directory_files(self) -> None:
        """Register files in directory as DuckDB views."""
        path = self._config.get("path", "")
        if not path or not os.path.isdir(path):
            return

        # Find all parquet and CSV files
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            if not os.path.isfile(filepath):
                continue

            # Create view name from filename (without extension)
            view_name = os.path.splitext(filename)[0]
            # Clean up view name to be valid SQL identifier
            view_name = view_name.replace("-", "_").replace(" ", "_")

            if filename.endswith(".parquet"):
                sql = f"CREATE VIEW IF NOT EXISTS {view_name} AS "
                sql += f"SELECT * FROM read_parquet('{filepath}')"
                self._conn.execute(sql)
            elif filename.endswith(".csv"):
                sql = f"CREATE VIEW IF NOT EXISTS {view_name} AS "
                sql += f"SELECT * FROM read_csv_auto('{filepath}')"
                self._conn.execute(sql)
            elif filename.endswith(".json") or filename.endswith(".jsonl"):
                sql = f"CREATE VIEW IF NOT EXISTS {view_name} AS "
                sql += f"SELECT * FROM read_json_auto('{filepath}')"
                self._conn.execute(sql)

    async def disconnect(self) -> None:
        """Close DuckDB connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test DuckDB connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            result = self._conn.execute("SELECT version()").fetchone()
            version = result[0] if result else "Unknown"

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"DuckDB {version}",
                message="Connection successful",
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                message=str(e),
                error_code="CONNECTION_FAILED",
            )

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Execute a SQL query against DuckDB."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to DuckDB")

        start_time = time.time()
        try:
            result = self._conn.execute(sql)
            columns_info = result.description
            rows = result.fetchall()

            execution_time_ms = int((time.time() - start_time) * 1000)

            if not columns_info:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            # Build column metadata
            columns = [
                {"name": col[0], "data_type": self._map_duckdb_type(col[1])} for col in columns_info
            ]
            column_names = [col[0] for col in columns_info]

            # Convert rows to dicts
            row_dicts = [dict(zip(column_names, row, strict=False)) for row in rows]

            # Apply limit if needed
            truncated = False
            if limit and len(row_dicts) > limit:
                row_dicts = row_dicts[:limit]
                truncated = True

            return QueryResult(
                columns=columns,
                rows=row_dicts,
                row_count=len(row_dicts),
                truncated=truncated,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            error_str = str(e).lower()
            if "syntax error" in error_str or "parser error" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=sql[:200],
                ) from e
            elif "timeout" in error_str:
                raise QueryTimeoutError(
                    message=str(e),
                    timeout_seconds=timeout_seconds,
                ) from e
            else:
                raise

    def _map_duckdb_type(self, type_code: Any) -> str:
        """Map DuckDB type code to string representation."""
        if type_code is None:
            return "unknown"
        type_str = str(type_code).lower()
        result: str = normalize_type(type_str, SourceType.DUCKDB).value
        return result

    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        """Fetch table metadata from DuckDB."""
        sql = """
            SELECT
                database_name as table_catalog,
                schema_name as table_schema,
                table_name,
                table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """
        result = await self.execute_query(sql)
        return list(result.rows)

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get DuckDB schema."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to DuckDB")

        try:
            # Build filter conditions
            conditions = ["table_schema NOT IN ('pg_catalog', 'information_schema')"]
            if filter:
                if filter.table_pattern:
                    conditions.append(f"table_name LIKE '{filter.table_pattern}'")
                if filter.schema_pattern:
                    conditions.append(f"table_schema LIKE '{filter.schema_pattern}'")
                if not filter.include_views:
                    conditions.append("table_type = 'BASE TABLE'")

            where_clause = " AND ".join(conditions)
            limit_clause = f"LIMIT {filter.max_tables}" if filter else "LIMIT 1000"

            # Get tables
            tables_sql = f"""
                SELECT
                    table_schema,
                    table_name,
                    table_type
                FROM information_schema.tables
                WHERE {where_clause}
                ORDER BY table_schema, table_name
                {limit_clause}
            """
            tables_result = await self.execute_query(tables_sql)

            # Get columns
            columns_sql = f"""
                SELECT
                    table_schema,
                    table_name,
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    ordinal_position
                FROM information_schema.columns
                WHERE {where_clause}
                ORDER BY table_schema, table_name, ordinal_position
            """
            columns_result = await self.execute_query(columns_sql)

            # Organize into schema response
            schema_map: dict[str, dict[str, dict[str, Any]]] = {}
            for row in tables_result.rows:
                schema_name = row["table_schema"]
                table_name = row["table_name"]
                table_type_raw = row["table_type"]

                table_type = "view" if "view" in table_type_raw.lower() else "table"

                if schema_name not in schema_map:
                    schema_map[schema_name] = {}
                schema_map[schema_name][table_name] = {
                    "name": table_name,
                    "table_type": table_type,
                    "native_type": table_type_raw,
                    "native_path": f"{schema_name}.{table_name}",
                    "columns": [],
                }

            # Add columns
            for row in columns_result.rows:
                schema_name = row["table_schema"]
                table_name = row["table_name"]
                if schema_name in schema_map and table_name in schema_map[schema_name]:
                    col_data = {
                        "name": row["column_name"],
                        "data_type": normalize_type(row["data_type"], SourceType.DUCKDB),
                        "native_type": row["data_type"],
                        "nullable": row["is_nullable"] == "YES",
                        "is_primary_key": False,
                        "is_partition_key": False,
                        "default_value": row["column_default"],
                    }
                    schema_map[schema_name][table_name]["columns"].append(col_data)

            # Build catalog structure
            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": schema_name,
                            "tables": list(tables.values()),
                        }
                        for schema_name, tables in schema_map.items()
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "duckdb",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch DuckDB schema: {str(e)}",
                details={"error": str(e)},
            ) from e

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build DuckDB-specific sampling query using TABLESAMPLE."""
        return f"SELECT * FROM {table} USING SAMPLE {n} ROWS"
