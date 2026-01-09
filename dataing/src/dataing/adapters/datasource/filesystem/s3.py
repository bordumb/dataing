"""S3 adapter implementation.

This module provides an S3 adapter that implements the unified
data source interface using DuckDB for file querying.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from dataing.adapters.datasource.errors import (
    AccessDeniedError,
    AuthenticationFailedError,
    ConnectionFailedError,
    SchemaFetchFailedError,
)
from dataing.adapters.datasource.filesystem.base import FileInfo, FileSystemAdapter
from dataing.adapters.datasource.registry import register_adapter
from dataing.adapters.datasource.type_mapping import normalize_type
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    Column,
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
    Table,
)

S3_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="location", label="Bucket Location", collapsed_by_default=False),
        FieldGroup(id="auth", label="AWS Credentials", collapsed_by_default=False),
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
            name="region",
            label="AWS Region",
            type="enum",
            required=True,
            group="location",
            default_value="us-east-1",
            options=[
                {"value": "us-east-1", "label": "US East (N. Virginia)"},
                {"value": "us-east-2", "label": "US East (Ohio)"},
                {"value": "us-west-1", "label": "US West (N. California)"},
                {"value": "us-west-2", "label": "US West (Oregon)"},
                {"value": "eu-west-1", "label": "EU (Ireland)"},
                {"value": "eu-west-2", "label": "EU (London)"},
                {"value": "eu-central-1", "label": "EU (Frankfurt)"},
                {"value": "ap-northeast-1", "label": "Asia Pacific (Tokyo)"},
                {"value": "ap-southeast-1", "label": "Asia Pacific (Singapore)"},
            ],
        ),
        ConfigField(
            name="access_key_id",
            label="Access Key ID",
            type="string",
            required=True,
            group="auth",
        ),
        ConfigField(
            name="secret_access_key",
            label="Secret Access Key",
            type="secret",
            required=True,
            group="auth",
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

S3_CAPABILITIES = AdapterCapabilities(
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
    source_type=SourceType.S3,
    display_name="Amazon S3",
    category=SourceCategory.FILESYSTEM,
    icon="aws-s3",
    description="Query parquet, CSV, and JSON files directly from S3 using SQL",
    capabilities=S3_CAPABILITIES,
    config_schema=S3_CONFIG_SCHEMA,
)
class S3Adapter(FileSystemAdapter):
    """S3 file system adapter.

    Uses DuckDB with httpfs extension for querying files directly from S3.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize S3 adapter.

        Args:
            config: Configuration dictionary with:
                - bucket: S3 bucket name
                - prefix: Path prefix (optional)
                - region: AWS region
                - access_key_id: AWS access key
                - secret_access_key: AWS secret key
                - file_format: Default format (optional)
        """
        super().__init__(config)
        self._duckdb_conn: Any = None
        self._s3_client: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.S3

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return S3_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to S3."""
        try:
            import boto3
            import duckdb
        except ImportError as e:
            raise ConnectionFailedError(
                message="boto3 and duckdb are required. Install with: pip install boto3 duckdb",
                details={"error": str(e)},
            ) from e

        try:
            region = self._config.get("region", "us-east-1")
            access_key = self._config.get("access_key_id", "")
            secret_key = self._config.get("secret_access_key", "")

            # Initialize S3 client for listing
            self._s3_client = boto3.client(
                "s3",
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )

            # Initialize DuckDB with S3 credentials
            self._duckdb_conn = duckdb.connect(":memory:")
            self._duckdb_conn.execute("INSTALL httpfs")
            self._duckdb_conn.execute("LOAD httpfs")
            self._duckdb_conn.execute(f"SET s3_region = '{region}'")
            self._duckdb_conn.execute(f"SET s3_access_key_id = '{access_key}'")
            self._duckdb_conn.execute(f"SET s3_secret_access_key = '{secret_key}'")

            # Test connection by listing bucket
            bucket = self._config.get("bucket", "")
            self._s3_client.head_bucket(Bucket=bucket)

            self._connected = True
        except Exception as e:
            error_str = str(e).lower()
            if "accessdenied" in error_str or "403" in error_str:
                raise AccessDeniedError(
                    message="Access denied to S3 bucket",
                ) from e
            elif "invalidaccesskeyid" in error_str or "signaturemismatch" in error_str:
                raise AuthenticationFailedError(
                    message="Invalid AWS credentials",
                    details={"error": str(e)},
                ) from e
            elif "nosuchbucket" in error_str:
                raise ConnectionFailedError(
                    message=f"S3 bucket not found: {self._config.get('bucket')}",
                    details={"error": str(e)},
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to S3: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close S3 connection."""
        if self._duckdb_conn:
            self._duckdb_conn.close()
            self._duckdb_conn = None
        self._s3_client = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test S3 connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            bucket = self._config.get("bucket", "")
            prefix = self._config.get("prefix", "")

            # List objects to verify access
            response = self._s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=1,
            )
            key_count = response.get("KeyCount", 0)

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"S3 ({bucket})",
                message=f"Connection successful, found {key_count}+ objects",
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=False,
                latency_ms=latency_ms,
                message=str(e),
                error_code="CONNECTION_FAILED",
            )

    async def list_files(
        self,
        pattern: str = "*",
        recursive: bool = True,
    ) -> list[FileInfo]:
        """List files in S3 bucket."""
        if not self._connected or not self._s3_client:
            raise ConnectionFailedError(message="Not connected to S3")

        bucket = self._config.get("bucket", "")
        prefix = self._config.get("prefix", "")

        files = []
        paginator = self._s3_client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                name = key.split("/")[-1]

                # Skip directories
                if key.endswith("/"):
                    continue

                # Match pattern
                if pattern != "*":
                    import fnmatch

                    if not fnmatch.fnmatch(name, pattern):
                        continue

                # Detect file format
                file_format = None
                if name.endswith(".parquet"):
                    file_format = "parquet"
                elif name.endswith(".csv"):
                    file_format = "csv"
                elif name.endswith(".json") or name.endswith(".jsonl"):
                    file_format = "json"

                files.append(
                    FileInfo(
                        path=f"s3://{bucket}/{key}",
                        name=name,
                        size_bytes=obj.get("Size", 0),
                        last_modified=obj.get("LastModified", datetime.now()).isoformat(),
                        file_format=file_format,
                    )
                )

        return files

    async def read_file(
        self,
        path: str,
        file_format: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Read a file from S3."""
        if not self._connected or not self._duckdb_conn:
            raise ConnectionFailedError(message="Not connected to S3")

        start_time = time.time()

        # Auto-detect format if not specified
        if not file_format:
            file_format = self._config.get("file_format", "auto")
            if file_format == "auto":
                if path.endswith(".parquet"):
                    file_format = "parquet"
                elif path.endswith(".csv"):
                    file_format = "csv"
                elif path.endswith(".json") or path.endswith(".jsonl"):
                    file_format = "json"
                else:
                    file_format = "parquet"  # Default

        # Build query based on format
        if file_format == "parquet":
            sql = f"SELECT * FROM read_parquet('{path}') LIMIT {limit}"
        elif file_format == "csv":
            sql = f"SELECT * FROM read_csv_auto('{path}') LIMIT {limit}"
        elif file_format == "json":
            sql = f"SELECT * FROM read_json_auto('{path}') LIMIT {limit}"
        else:
            sql = f"SELECT * FROM read_parquet('{path}') LIMIT {limit}"

        result = self._duckdb_conn.execute(sql)
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
            execution_time_ms=execution_time_ms,
        )

    def _map_duckdb_type(self, type_code: Any) -> str:
        """Map DuckDB type to normalized type."""
        if type_code is None:
            return "unknown"
        type_str = str(type_code).lower()
        result: str = normalize_type(type_str, SourceType.DUCKDB).value
        return result

    async def infer_schema(
        self,
        path: str,
        file_format: str | None = None,
    ) -> Table:
        """Infer schema from a file."""
        if not self._connected or not self._duckdb_conn:
            raise ConnectionFailedError(message="Not connected to S3")

        # Auto-detect format
        if not file_format:
            if path.endswith(".parquet"):
                file_format = "parquet"
            elif path.endswith(".csv"):
                file_format = "csv"
            else:
                file_format = "parquet"

        # Get schema using DESCRIBE
        if file_format == "parquet":
            sql = f"DESCRIBE SELECT * FROM read_parquet('{path}')"
        elif file_format == "csv":
            sql = f"DESCRIBE SELECT * FROM read_csv_auto('{path}')"
        else:
            sql = f"DESCRIBE SELECT * FROM read_parquet('{path}')"

        result = self._duckdb_conn.execute(sql)
        rows = result.fetchall()

        columns = []
        for row in rows:
            col_name = row[0]
            col_type = row[1]
            columns.append(
                Column(
                    name=col_name,
                    data_type=normalize_type(col_type, SourceType.DUCKDB),
                    native_type=col_type,
                    nullable=True,
                    is_primary_key=False,
                    is_partition_key=False,
                )
            )

        # Get file name for table name
        name = path.split("/")[-1].split(".")[0]

        return Table(
            name=name,
            table_type="file",
            native_type="PARQUET_FILE" if file_format == "parquet" else "CSV_FILE",
            native_path=path,
            columns=columns,
        )

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get S3 schema (files as tables)."""
        if not self._connected:
            raise ConnectionFailedError(message="Not connected to S3")

        try:
            # List files
            files = await self.list_files()

            # Apply filter if provided
            if filter and filter.table_pattern:
                import fnmatch

                pattern = filter.table_pattern.replace("%", "*")
                files = [f for f in files if fnmatch.fnmatch(f.name, pattern)]

            # Limit files
            max_tables = filter.max_tables if filter else 100
            files = files[:max_tables]

            # Infer schema for each file
            tables = []
            for file_info in files:
                try:
                    table = await self.infer_schema(file_info.path, file_info.file_format)
                    tables.append(
                        {
                            "name": table.name,
                            "table_type": table.table_type,
                            "native_type": table.native_type,
                            "native_path": table.native_path,
                            "columns": [
                                {
                                    "name": col.name,
                                    "data_type": col.data_type,
                                    "native_type": col.native_type,
                                    "nullable": col.nullable,
                                    "is_primary_key": col.is_primary_key,
                                    "is_partition_key": col.is_partition_key,
                                }
                                for col in table.columns
                            ],
                            "size_bytes": file_info.size_bytes,
                            "last_modified": file_info.last_modified,
                        }
                    )
                except Exception:
                    # Skip files we can't read
                    continue

            bucket = self._config.get("bucket", "")
            prefix = self._config.get("prefix", "")

            # Build catalog structure
            catalogs = [
                {
                    "name": bucket,
                    "schemas": [
                        {
                            "name": prefix or "root",
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "s3",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch S3 schema: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Execute a SQL query against S3 files using DuckDB."""
        if not self._connected or not self._duckdb_conn:
            raise ConnectionFailedError(message="Not connected to S3")

        start_time = time.time()

        result = self._duckdb_conn.execute(sql)
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
