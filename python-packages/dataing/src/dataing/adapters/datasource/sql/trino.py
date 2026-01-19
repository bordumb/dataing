"""Trino adapter implementation.

This module provides a Trino adapter that implements the unified
data source interface with full schema discovery and query capabilities.
"""

from __future__ import annotations

import time
from typing import Any

from dataing.adapters.datasource.errors import (
    AccessDeniedError,
    AuthenticationFailedError,
    ConnectionFailedError,
    ConnectionTimeoutError,
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

TRINO_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
        FieldGroup(id="auth", label="Authentication", collapsed_by_default=False),
        FieldGroup(id="advanced", label="Advanced", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="host",
            label="Host",
            type="string",
            required=True,
            group="connection",
            placeholder="localhost",
            description="Trino coordinator hostname or IP address",
        ),
        ConfigField(
            name="port",
            label="Port",
            type="integer",
            required=True,
            group="connection",
            default_value=8080,
            min_value=1,
            max_value=65535,
        ),
        ConfigField(
            name="catalog",
            label="Catalog",
            type="string",
            required=True,
            group="connection",
            placeholder="hive",
            description="Default catalog to use",
        ),
        ConfigField(
            name="schema",
            label="Schema",
            type="string",
            required=False,
            group="connection",
            placeholder="default",
            description="Default schema to use",
        ),
        ConfigField(
            name="user",
            label="User",
            type="string",
            required=True,
            group="auth",
            placeholder="trino",
        ),
        ConfigField(
            name="password",
            label="Password",
            type="secret",
            required=False,
            group="auth",
            description="Password (if authentication is enabled)",
        ),
        ConfigField(
            name="http_scheme",
            label="HTTP Scheme",
            type="enum",
            required=False,
            group="advanced",
            default_value="http",
            options=[
                {"value": "http", "label": "HTTP"},
                {"value": "https", "label": "HTTPS"},
            ],
        ),
        ConfigField(
            name="verify",
            label="Verify SSL",
            type="boolean",
            required=False,
            group="advanced",
            default_value=True,
        ),
    ],
)

TRINO_CAPABILITIES = AdapterCapabilities(
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
    source_type=SourceType.TRINO,
    display_name="Trino",
    category=SourceCategory.DATABASE,
    icon="trino",
    description="Connect to Trino clusters for distributed SQL querying",
    capabilities=TRINO_CAPABILITIES,
    config_schema=TRINO_CONFIG_SCHEMA,
)
class TrinoAdapter(SQLAdapter):
    """Trino database adapter.

    Provides full schema discovery and query execution for Trino clusters.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Trino adapter.

        Args:
            config: Configuration dictionary with:
                - host: Coordinator hostname
                - port: Coordinator port
                - catalog: Default catalog
                - schema: Default schema (optional)
                - user: Username
                - password: Password (optional)
                - http_scheme: http or https (optional)
                - verify: Verify SSL certificates (optional)
        """
        super().__init__(config)
        self._conn: Any = None
        self._cursor: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.TRINO

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return TRINO_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to Trino."""
        try:
            from trino.auth import BasicAuthentication
            from trino.dbapi import connect
        except ImportError as e:
            raise ConnectionFailedError(
                message="trino is not installed. Install with: pip install trino",
                details={"error": str(e)},
            ) from e

        try:
            host = self._config.get("host", "localhost")
            port = self._config.get("port", 8080)
            catalog = self._config.get("catalog", "hive")
            schema = self._config.get("schema", "default")
            user = self._config.get("user", "trino")
            password = self._config.get("password")
            http_scheme = self._config.get("http_scheme", "http")
            verify = self._config.get("verify", True)

            auth = None
            if password:
                auth = BasicAuthentication(user, password)

            self._conn = connect(
                host=host,
                port=port,
                user=user,
                catalog=catalog,
                schema=schema,
                http_scheme=http_scheme,
                auth=auth,
                verify=verify,
            )
            self._connected = True
        except Exception as e:
            error_str = str(e).lower()
            if "authentication" in error_str or "401" in error_str:
                raise AuthenticationFailedError(
                    message="Authentication failed for Trino",
                    details={"error": str(e)},
                ) from e
            elif "connection refused" in error_str or "timeout" in error_str:
                raise ConnectionTimeoutError(
                    message="Connection to Trino timed out",
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to Trino: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close Trino connection."""
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test Trino connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            cursor = self._conn.cursor()
            cursor.execute("SELECT 'test'")
            cursor.fetchall()
            cursor.close()

            # Get server info
            catalog = self._config.get("catalog", "")
            version = f"Trino (catalog: {catalog})"

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=version,
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
        """Execute a SQL query against Trino."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to Trino")

        start_time = time.time()
        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)

            # Get column info
            columns_info = cursor.description
            rows = cursor.fetchall()

            execution_time_ms = int((time.time() - start_time) * 1000)

            if not columns_info:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            columns = [{"name": col[0], "data_type": "string"} for col in columns_info]
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
            if "syntax error" in error_str or "mismatched input" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=sql[:200],
                ) from e
            elif "permission denied" in error_str or "access denied" in error_str:
                raise AccessDeniedError(
                    message=str(e),
                ) from e
            elif "timeout" in error_str or "exceeded" in error_str:
                raise QueryTimeoutError(
                    message=str(e),
                    timeout_seconds=timeout_seconds,
                ) from e
            else:
                raise
        finally:
            if cursor:
                cursor.close()

    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        """Fetch table metadata from Trino."""
        catalog = self._config.get("catalog", "hive")
        schema = self._config.get("schema", "default")

        sql = f"""
            SELECT
                table_catalog,
                table_schema,
                table_name,
                table_type
            FROM {catalog}.information_schema.tables
            WHERE table_schema = '{schema}'
            ORDER BY table_name
        """
        result = await self.execute_query(sql)
        return list(result.rows)

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get Trino schema."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to Trino")

        try:
            catalog = self._config.get("catalog", "hive")
            schema = self._config.get("schema", "default")

            # Build filter conditions
            conditions = [f"table_schema = '{schema}'"]
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
                FROM {catalog}.information_schema.tables
                WHERE {where_clause}
                ORDER BY table_name
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
                    ordinal_position
                FROM {catalog}.information_schema.columns
                WHERE {where_clause}
                ORDER BY table_name, ordinal_position
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
                    "native_path": f"{catalog}.{schema_name}.{table_name}",
                    "columns": [],
                }

            # Add columns
            for row in columns_result.rows:
                schema_name = row["table_schema"]
                table_name = row["table_name"]
                if schema_name in schema_map and table_name in schema_map[schema_name]:
                    col_data = {
                        "name": row["column_name"],
                        "data_type": normalize_type(row["data_type"], SourceType.TRINO),
                        "native_type": row["data_type"],
                        "nullable": row["is_nullable"] == "YES",
                        "is_primary_key": False,
                        "is_partition_key": False,
                    }
                    schema_map[schema_name][table_name]["columns"].append(col_data)

            # Build catalog structure
            catalogs = [
                {
                    "name": catalog,
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
                source_id=self._source_id or "trino",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch Trino schema: {str(e)}",
                details={"error": str(e)},
            ) from e

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build Trino-specific sampling query using TABLESAMPLE."""
        return f"SELECT * FROM {table} TABLESAMPLE BERNOULLI(10) LIMIT {n}"
