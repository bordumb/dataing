"""Snowflake adapter implementation.

This module provides a Snowflake adapter that implements the unified
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

SNOWFLAKE_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
        FieldGroup(id="auth", label="Authentication", collapsed_by_default=False),
        FieldGroup(id="advanced", label="Advanced", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="account",
            label="Account",
            type="string",
            required=True,
            group="connection",
            placeholder="xy12345.us-east-1",
            description="Snowflake account identifier (e.g., xy12345.us-east-1)",
        ),
        ConfigField(
            name="warehouse",
            label="Warehouse",
            type="string",
            required=True,
            group="connection",
            placeholder="COMPUTE_WH",
            description="Virtual warehouse to use",
        ),
        ConfigField(
            name="database",
            label="Database",
            type="string",
            required=True,
            group="connection",
            placeholder="MY_DATABASE",
        ),
        ConfigField(
            name="schema",
            label="Schema",
            type="string",
            required=False,
            group="connection",
            placeholder="PUBLIC",
            default_value="PUBLIC",
        ),
        ConfigField(
            name="user",
            label="User",
            type="string",
            required=True,
            group="auth",
        ),
        ConfigField(
            name="password",
            label="Password",
            type="secret",
            required=True,
            group="auth",
        ),
        ConfigField(
            name="role",
            label="Role",
            type="string",
            required=False,
            group="advanced",
            placeholder="ACCOUNTADMIN",
            description="Role to use for the session",
        ),
        ConfigField(
            name="login_timeout",
            label="Login Timeout (seconds)",
            type="integer",
            required=False,
            group="advanced",
            default_value=60,
            min_value=10,
            max_value=300,
        ),
    ],
)

SNOWFLAKE_CAPABILITIES = AdapterCapabilities(
    supports_sql=True,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=True,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SQL,
    max_concurrent_queries=10,
)


@register_adapter(
    source_type=SourceType.SNOWFLAKE,
    display_name="Snowflake",
    category=SourceCategory.DATABASE,
    icon="snowflake",
    description="Connect to Snowflake data warehouse for analytics and querying",
    capabilities=SNOWFLAKE_CAPABILITIES,
    config_schema=SNOWFLAKE_CONFIG_SCHEMA,
)
class SnowflakeAdapter(SQLAdapter):
    """Snowflake database adapter.

    Provides full schema discovery and query execution for Snowflake.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Snowflake adapter.

        Args:
            config: Configuration dictionary with:
                - account: Snowflake account identifier
                - warehouse: Virtual warehouse
                - database: Database name
                - schema: Schema name (optional)
                - user: Username
                - password: Password
                - role: Role (optional)
                - login_timeout: Timeout in seconds (optional)
        """
        super().__init__(config)
        self._conn: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.SNOWFLAKE

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return SNOWFLAKE_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to Snowflake."""
        try:
            import snowflake.connector
        except ImportError as e:
            raise ConnectionFailedError(
                message="snowflake-connector-python not installed. pip install it",
                details={"error": str(e)},
            ) from e

        try:
            account = self._config.get("account", "")
            user = self._config.get("user", "")
            password = self._config.get("password", "")
            warehouse = self._config.get("warehouse", "")
            database = self._config.get("database", "")
            schema = self._config.get("schema", "PUBLIC")
            role = self._config.get("role")
            login_timeout = self._config.get("login_timeout", 60)

            connect_params = {
                "account": account,
                "user": user,
                "password": password,
                "warehouse": warehouse,
                "database": database,
                "schema": schema,
                "login_timeout": login_timeout,
            }

            if role:
                connect_params["role"] = role

            self._conn = snowflake.connector.connect(**connect_params)
            self._connected = True
        except Exception as e:
            error_str = str(e).lower()
            if "incorrect username or password" in error_str or "authentication" in error_str:
                raise AuthenticationFailedError(
                    message="Authentication failed for Snowflake",
                    details={"error": str(e)},
                ) from e
            elif "timeout" in error_str:
                raise ConnectionTimeoutError(
                    message="Connection to Snowflake timed out",
                    timeout_seconds=self._config.get("login_timeout", 60),
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to Snowflake: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close Snowflake connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test Snowflake connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            cursor = self._conn.cursor()
            cursor.execute("SELECT CURRENT_VERSION()")
            result = cursor.fetchone()
            version = result[0] if result else "Unknown"
            cursor.close()

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"Snowflake {version}",
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
        """Execute a SQL query against Snowflake."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to Snowflake")

        start_time = time.time()
        cursor = None
        try:
            cursor = self._conn.cursor()

            # Set query timeout
            cursor.execute(f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {timeout_seconds}")

            # Execute query
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
            if "syntax error" in error_str or "sql compilation error" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=sql[:200],
                ) from e
            elif "insufficient privileges" in error_str or "access denied" in error_str:
                raise AccessDeniedError(
                    message=str(e),
                ) from e
            elif "timeout" in error_str or "statement timeout" in error_str:
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
        """Fetch table metadata from Snowflake."""
        database = self._config.get("database", "")
        schema = self._config.get("schema", "PUBLIC")

        sql = f"""
            SELECT
                TABLE_CATALOG as table_catalog,
                TABLE_SCHEMA as table_schema,
                TABLE_NAME as table_name,
                TABLE_TYPE as table_type
            FROM {database}.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = '{schema}'
            ORDER BY TABLE_NAME
        """
        result = await self.execute_query(sql)
        return list(result.rows)

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get Snowflake schema."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to Snowflake")

        try:
            database = self._config.get("database", "")
            schema = self._config.get("schema", "PUBLIC")

            # Build filter conditions
            conditions = [f"TABLE_SCHEMA = '{schema}'"]
            if filter:
                if filter.table_pattern:
                    conditions.append(f"TABLE_NAME LIKE '{filter.table_pattern}'")
                if filter.schema_pattern:
                    conditions.append(f"TABLE_SCHEMA LIKE '{filter.schema_pattern}'")
                if not filter.include_views:
                    conditions.append("TABLE_TYPE = 'BASE TABLE'")

            where_clause = " AND ".join(conditions)
            limit_clause = f"LIMIT {filter.max_tables}" if filter else "LIMIT 1000"

            # Get tables
            tables_sql = f"""
                SELECT
                    TABLE_SCHEMA as table_schema,
                    TABLE_NAME as table_name,
                    TABLE_TYPE as table_type,
                    ROW_COUNT as row_count,
                    BYTES as size_bytes
                FROM {database}.INFORMATION_SCHEMA.TABLES
                WHERE {where_clause}
                ORDER BY TABLE_NAME
                {limit_clause}
            """
            tables_result = await self.execute_query(tables_sql)

            # Get columns
            columns_sql = f"""
                SELECT
                    TABLE_SCHEMA as table_schema,
                    TABLE_NAME as table_name,
                    COLUMN_NAME as column_name,
                    DATA_TYPE as data_type,
                    IS_NULLABLE as is_nullable,
                    COLUMN_DEFAULT as column_default,
                    ORDINAL_POSITION as ordinal_position
                FROM {database}.INFORMATION_SCHEMA.COLUMNS
                WHERE {where_clause}
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            columns_result = await self.execute_query(columns_sql)

            # Organize into schema response
            schema_map: dict[str, dict[str, dict[str, Any]]] = {}
            for row in tables_result.rows:
                schema_name = row["TABLE_SCHEMA"] or row.get("table_schema", "")
                table_name = row["TABLE_NAME"] or row.get("table_name", "")
                table_type_raw = row["TABLE_TYPE"] or row.get("table_type", "")

                table_type = "view" if "view" in table_type_raw.lower() else "table"

                if schema_name not in schema_map:
                    schema_map[schema_name] = {}
                schema_map[schema_name][table_name] = {
                    "name": table_name,
                    "table_type": table_type,
                    "native_type": table_type_raw,
                    "native_path": f"{database}.{schema_name}.{table_name}",
                    "columns": [],
                    "row_count": row.get("ROW_COUNT") or row.get("row_count"),
                    "size_bytes": row.get("BYTES") or row.get("size_bytes"),
                }

            # Add columns
            for row in columns_result.rows:
                schema_name = row["TABLE_SCHEMA"] or row.get("table_schema", "")
                table_name = row["TABLE_NAME"] or row.get("table_name", "")
                if schema_name in schema_map and table_name in schema_map[schema_name]:
                    col_data = {
                        "name": row["COLUMN_NAME"] or row.get("column_name", ""),
                        "data_type": normalize_type(
                            row["DATA_TYPE"] or row.get("data_type", ""), SourceType.SNOWFLAKE
                        ),
                        "native_type": row["DATA_TYPE"] or row.get("data_type", ""),
                        "nullable": (row["IS_NULLABLE"] or row.get("is_nullable", "YES")) == "YES",
                        "is_primary_key": False,
                        "is_partition_key": False,
                        "default_value": row["COLUMN_DEFAULT"] or row.get("column_default"),
                    }
                    schema_map[schema_name][table_name]["columns"].append(col_data)

            # Build catalog structure
            catalogs = [
                {
                    "name": database,
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
                source_id=self._source_id or "snowflake",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch Snowflake schema: {str(e)}",
                details={"error": str(e)},
            ) from e

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build Snowflake-specific sampling query using TABLESAMPLE."""
        return f"SELECT * FROM {table} SAMPLE ({n} ROWS)"
