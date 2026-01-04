"""Local file system adapter implementation.

This module provides a local file system adapter that implements the unified
data source interface by using DuckDB to query local Parquet, CSV, and JSON files.
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
from dataing.adapters.datasource.filesystem.base import FileSystemAdapter
from dataing.adapters.datasource.registry import register_adapter
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

LOCAL_FILE_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="location", label="File Location", collapsed_by_default=False),
        FieldGroup(id="format", label="File Format", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="path",
            label="Directory Path",
            type="string",
            required=True,
            group="location",
            placeholder="/path/to/data",
            description="Path to directory containing data files",
        ),
        ConfigField(
            name="recursive",
            label="Include Subdirectories",
            type="boolean",
            required=False,
            group="location",
            default_value=False,
            description="Search for files in subdirectories",
        ),
        ConfigField(
            name="file_format",
            label="Default File Format",
            type="enum",
            required=False,
            group="format",
            default_value="auto",
            options=[
                {"value": "auto", "label": "Auto-detect"},
                {"value": "parquet", "label": "Parquet"},
                {"value": "csv", "label": "CSV"},
                {"value": "json", "label": "JSON/JSONL"},
            ],
        ),
    ],
)

LOCAL_FILE_CAPABILITIES = AdapterCapabilities(
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
    source_type=SourceType.LOCAL_FILE,
    display_name="Local Files",
    category=SourceCategory.FILESYSTEM,
    icon="folder",
    description="Query Parquet, CSV, and JSON files from local filesystem",
    capabilities=LOCAL_FILE_CAPABILITIES,
    config_schema=LOCAL_FILE_CONFIG_SCHEMA,
)
class LocalFileAdapter(FileSystemAdapter):
    """Local file system adapter.

    Uses DuckDB to query files stored on the local filesystem.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize local file adapter.

        Args:
            config: Configuration dictionary with:
                - path: Directory path containing data files
                - recursive: Search subdirectories (optional)
                - file_format: Default file format (auto, parquet, csv, json)
        """
        super().__init__(config)
        self._conn: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.LOCAL_FILE

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return LOCAL_FILE_CAPABILITIES

    def _get_base_path(self) -> str:
        """Get the configured base path."""
        path = self._config.get("path", ".")
        result: str = os.path.abspath(os.path.expanduser(path))
        return result

    async def connect(self) -> None:
        """Establish connection to local file system via DuckDB."""
        try:
            import duckdb
        except ImportError as e:
            raise ConnectionFailedError(
                message="duckdb is not installed. Install with: pip install duckdb",
                details={"error": str(e)},
            ) from e

        try:
            base_path = self._get_base_path()

            if not os.path.exists(base_path):
                raise ConnectionFailedError(
                    message=f"Directory does not exist: {base_path}",
                    details={"path": base_path},
                )

            if not os.path.isdir(base_path):
                raise ConnectionFailedError(
                    message=f"Path is not a directory: {base_path}",
                    details={"path": base_path},
                )

            self._conn = duckdb.connect(":memory:")
            self._connected = True

        except ConnectionFailedError:
            raise
        except Exception as e:
            raise ConnectionFailedError(
                message=f"Failed to connect to local filesystem: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def disconnect(self) -> None:
        """Close DuckDB connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test local filesystem connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            base_path = self._get_base_path()

            file_count = 0
            for entry in os.listdir(base_path):
                if entry.endswith((".parquet", ".csv", ".json", ".jsonl")):
                    file_count += 1

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version="Local FS via DuckDB",
                message=f"Connection successful. Found {file_count} data files.",
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                message=str(e),
                error_code="CONNECTION_FAILED",
            )

    async def list_files(self, pattern: str = "*") -> list[dict[str, Any]]:
        """List files in the local directory."""
        if not self._connected:
            raise ConnectionFailedError(message="Not connected to local filesystem")

        try:
            base_path = self._get_base_path()
            recursive = self._config.get("recursive", False)

            files = []

            if recursive:
                for root, _, filenames in os.walk(base_path):
                    for filename in filenames:
                        if self._matches_pattern(filename, pattern):
                            filepath = os.path.join(root, filename)
                            try:
                                size = os.path.getsize(filepath)
                            except Exception:
                                size = None
                            files.append(
                                {
                                    "path": filepath,
                                    "name": filename,
                                    "size": size,
                                }
                            )
            else:
                for entry in os.listdir(base_path):
                    filepath = os.path.join(base_path, entry)
                    if os.path.isfile(filepath) and self._matches_pattern(entry, pattern):
                        try:
                            size = os.path.getsize(filepath)
                        except Exception:
                            size = None
                        files.append(
                            {
                                "path": filepath,
                                "name": entry,
                                "size": size,
                            }
                        )

            return files

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to list files: {str(e)}",
                details={"error": str(e)},
            ) from e

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Check if filename matches the pattern."""
        import fnmatch

        return fnmatch.fnmatch(filename, pattern)

    async def read_file(
        self,
        path: str,
        format: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Read a local file."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to local filesystem")

        start_time = time.time()
        try:
            file_format = format or self._config.get("file_format", "auto")

            if file_format == "auto":
                if path.endswith(".parquet"):
                    file_format = "parquet"
                elif path.endswith(".csv"):
                    file_format = "csv"
                elif path.endswith(".json") or path.endswith(".jsonl"):
                    file_format = "json"
                else:
                    file_format = "parquet"

            if file_format == "parquet":
                sql = f"SELECT * FROM read_parquet('{path}') LIMIT {limit}"
            elif file_format == "csv":
                sql = f"SELECT * FROM read_csv_auto('{path}') LIMIT {limit}"
            else:
                sql = f"SELECT * FROM read_json_auto('{path}') LIMIT {limit}"

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

            columns = [
                {"name": col[0], "data_type": self._map_duckdb_type(col[1])} for col in columns_info
            ]
            column_names = [col[0] for col in columns_info]
            row_dicts = [dict(zip(column_names, row, strict=False)) for row in rows]

            return QueryResult(
                columns=columns,
                rows=row_dicts,
                row_count=len(row_dicts),
                truncated=len(rows) >= limit,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            error_str = str(e).lower()
            if "syntax error" in error_str or "parser error" in error_str:
                raise QuerySyntaxError(message=str(e), query=path) from e
            raise

    def _map_duckdb_type(self, type_code: Any) -> str:
        """Map DuckDB type code to string representation."""
        if type_code is None:
            return "unknown"
        type_str = str(type_code).lower()
        result: str = normalize_type(type_str, SourceType.DUCKDB).value
        return result

    async def infer_schema(self, path: str) -> dict[str, Any]:
        """Infer schema from a local file."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to local filesystem")

        try:
            file_format = self._config.get("file_format", "auto")

            if file_format == "auto":
                if path.endswith(".parquet"):
                    file_format = "parquet"
                elif path.endswith(".csv"):
                    file_format = "csv"
                else:
                    file_format = "json"

            if file_format == "parquet":
                sql = f"DESCRIBE SELECT * FROM read_parquet('{path}')"
            elif file_format == "csv":
                sql = f"DESCRIBE SELECT * FROM read_csv_auto('{path}')"
            else:
                sql = f"DESCRIBE SELECT * FROM read_json_auto('{path}')"

            result = self._conn.execute(sql)
            rows = result.fetchall()

            columns = []
            for row in rows:
                col_name = row[0]
                col_type = row[1]
                columns.append(
                    {
                        "name": col_name,
                        "data_type": normalize_type(col_type, SourceType.DUCKDB),
                        "native_type": col_type,
                        "nullable": True,
                        "is_primary_key": False,
                        "is_partition_key": False,
                    }
                )

            filename = os.path.basename(path)
            table_name = filename.rsplit(".", 1)[0].replace("-", "_").replace(" ", "_")

            try:
                size = os.path.getsize(path)
            except Exception:
                size = None

            return {
                "name": table_name,
                "table_type": "file",
                "native_type": f"LOCAL_{file_format.upper()}_FILE",
                "native_path": path,
                "columns": columns,
                "size_bytes": size,
            }

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to infer schema from {path}: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Execute a SQL query against local files."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to local filesystem")

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

            columns = [
                {"name": col[0], "data_type": self._map_duckdb_type(col[1])} for col in columns_info
            ]
            column_names = [col[0] for col in columns_info]
            row_dicts = [dict(zip(column_names, row, strict=False)) for row in rows]

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
                raise QuerySyntaxError(message=str(e), query=sql[:200]) from e
            elif "timeout" in error_str:
                raise QueryTimeoutError(message=str(e), timeout_seconds=timeout_seconds) from e
            raise

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get local filesystem schema by discovering files."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to local filesystem")

        try:
            file_extensions = ["*.parquet", "*.csv", "*.json", "*.jsonl"]
            all_files = []

            for ext in file_extensions:
                try:
                    files = await self.list_files(ext)
                    all_files.extend(files)
                except Exception:
                    pass

            if filter and filter.table_pattern:
                all_files = [f for f in all_files if filter.table_pattern in f["name"]]

            if filter and filter.max_tables:
                all_files = all_files[: filter.max_tables]

            tables = []
            for file_info in all_files:
                try:
                    table_def = await self.infer_schema(file_info["path"])
                    tables.append(table_def)
                except Exception:
                    tables.append(
                        {
                            "name": file_info["name"].rsplit(".", 1)[0],
                            "table_type": "file",
                            "native_type": "LOCAL_FILE",
                            "native_path": file_info["path"],
                            "columns": [],
                            "size_bytes": file_info.get("size"),
                        }
                    )

            base_path = self._get_base_path()
            dir_name = os.path.basename(base_path) or "root"

            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": dir_name,
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "local",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch local filesystem schema: {str(e)}",
                details={"error": str(e)},
            ) from e
