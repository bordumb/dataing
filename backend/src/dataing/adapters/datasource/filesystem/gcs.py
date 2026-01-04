"""Google Cloud Storage adapter implementation.

This module provides a GCS adapter that implements the unified
data source interface by using DuckDB to query files stored in GCS.
"""

from __future__ import annotations

import time
from typing import Any

from dataing.adapters.datasource.errors import (
    AccessDeniedError,
    AuthenticationFailedError,
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

GCS_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="location", label="Bucket Location", collapsed_by_default=False),
        FieldGroup(id="auth", label="GCP Credentials", collapsed_by_default=False),
        FieldGroup(id="format", label="File Format", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="bucket",
            label="Bucket Name",
            type="string",
            required=True,
            group="location",
            placeholder="my-data-bucket",
        ),
        ConfigField(
            name="prefix",
            label="Path Prefix",
            type="string",
            required=False,
            group="location",
            placeholder="data/warehouse/",
            description="Optional path prefix to limit scope",
        ),
        ConfigField(
            name="credentials_json",
            label="Service Account JSON",
            type="secret",
            required=True,
            group="auth",
            description="Service account credentials JSON content",
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

GCS_CAPABILITIES = AdapterCapabilities(
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
    source_type=SourceType.GCS,
    display_name="Google Cloud Storage",
    category=SourceCategory.FILESYSTEM,
    icon="gcs",
    description="Query Parquet, CSV, and JSON files stored in Google Cloud Storage",
    capabilities=GCS_CAPABILITIES,
    config_schema=GCS_CONFIG_SCHEMA,
)
class GCSAdapter(FileSystemAdapter):
    """Google Cloud Storage adapter.

    Uses DuckDB with GCS extension to query files stored in GCS buckets.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize GCS adapter.

        Args:
            config: Configuration dictionary with:
                - bucket: GCS bucket name
                - prefix: Optional path prefix
                - credentials_json: Service account JSON credentials
                - file_format: Default file format (auto, parquet, csv, json)
        """
        super().__init__(config)
        self._conn: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.GCS

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return GCS_CAPABILITIES

    def _get_gcs_path(self, path: str = "") -> str:
        """Construct full GCS path."""
        bucket = self._config.get("bucket", "")
        prefix = self._config.get("prefix", "").strip("/")

        if path:
            if prefix:
                return f"gs://{bucket}/{prefix}/{path}"
            return f"gs://{bucket}/{path}"
        elif prefix:
            return f"gs://{bucket}/{prefix}/"
        return f"gs://{bucket}/"

    async def connect(self) -> None:
        """Establish connection to GCS via DuckDB."""
        try:
            import duckdb
        except ImportError as e:
            raise ConnectionFailedError(
                message="duckdb is not installed. Install with: pip install duckdb",
                details={"error": str(e)},
            ) from e

        try:
            self._conn = duckdb.connect(":memory:")

            self._conn.execute("INSTALL httpfs")
            self._conn.execute("LOAD httpfs")

            credentials_json = self._config.get("credentials_json", "")
            if credentials_json:
                import json
                import os
                import tempfile

                creds = (
                    json.loads(credentials_json)
                    if isinstance(credentials_json, str)
                    else credentials_json
                )

                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                    json.dump(creds, f)
                    creds_path = f.name

                try:
                    self._conn.execute(f"SET gcs_service_account_key_file = '{creds_path}'")
                finally:
                    os.unlink(creds_path)

            self._connected = True

        except Exception as e:
            error_str = str(e).lower()
            if "credentials" in error_str or "authentication" in error_str:
                raise AuthenticationFailedError(
                    message="GCS authentication failed",
                    details={"error": str(e)},
                ) from e
            raise ConnectionFailedError(
                message=f"Failed to connect to GCS: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def disconnect(self) -> None:
        """Close GCS connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test GCS connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            self._config.get("bucket", "")
            self._config.get("prefix", "")

            gcs_path = self._get_gcs_path()

            try:
                self._conn.execute(f"SELECT * FROM glob('{gcs_path}*.parquet') LIMIT 1")
            except Exception:
                pass

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version="GCS via DuckDB",
                message="Connection successful",
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_str = str(e).lower()

            if "accessdenied" in error_str or "forbidden" in error_str:
                return ConnectionTestResult(
                    success=False,
                    latency_ms=latency_ms,
                    message="Access denied to GCS bucket",
                    error_code="ACCESS_DENIED",
                )
            elif "nosuchbucket" in error_str or "not found" in error_str:
                return ConnectionTestResult(
                    success=False,
                    latency_ms=latency_ms,
                    message="GCS bucket not found",
                    error_code="CONNECTION_FAILED",
                )

            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                message=str(e),
                error_code="CONNECTION_FAILED",
            )

    async def list_files(self, pattern: str = "*") -> list[dict[str, Any]]:
        """List files in the GCS bucket."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to GCS")

        try:
            gcs_path = self._get_gcs_path()
            full_pattern = f"{gcs_path}{pattern}"

            result = self._conn.execute(f"SELECT * FROM glob('{full_pattern}')").fetchall()

            files = []
            for row in result:
                filepath = row[0]
                filename = filepath.split("/")[-1]
                files.append(
                    {
                        "path": filepath,
                        "name": filename,
                        "size": None,
                    }
                )

            return files

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to list GCS files: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def read_file(
        self,
        path: str,
        format: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Read a file from GCS."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to GCS")

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
            elif "accessdenied" in error_str:
                raise AccessDeniedError(message=str(e)) from e
            raise

    def _map_duckdb_type(self, type_code: Any) -> str:
        """Map DuckDB type code to string representation."""
        if type_code is None:
            return "unknown"
        type_str = str(type_code).lower()
        result: str = normalize_type(type_str, SourceType.DUCKDB).value
        return result

    async def infer_schema(self, path: str) -> dict[str, Any]:
        """Infer schema from a GCS file."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to GCS")

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

            filename = path.split("/")[-1]
            table_name = filename.rsplit(".", 1)[0].replace("-", "_").replace(" ", "_")

            return {
                "name": table_name,
                "table_type": "file",
                "native_type": f"GCS_{file_format.upper()}_FILE",
                "native_path": path,
                "columns": columns,
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
        """Execute a SQL query against GCS files."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to GCS")

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
        """Get GCS schema by discovering files."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to GCS")

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
                            "native_type": "GCS_FILE",
                            "native_path": file_info["path"],
                            "columns": [],
                        }
                    )

            bucket = self._config.get("bucket", "default")
            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": bucket,
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "gcs",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch GCS schema: {str(e)}",
                details={"error": str(e)},
            ) from e
