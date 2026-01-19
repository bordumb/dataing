"""MySQL adapter implementation.

This module provides a MySQL adapter that implements the unified
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

MYSQL_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
        FieldGroup(id="auth", label="Authentication", collapsed_by_default=False),
        FieldGroup(id="ssl", label="SSL/TLS", collapsed_by_default=True),
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
            description="MySQL server hostname or IP address",
        ),
        ConfigField(
            name="port",
            label="Port",
            type="integer",
            required=True,
            group="connection",
            default_value=3306,
            min_value=1,
            max_value=65535,
        ),
        ConfigField(
            name="database",
            label="Database",
            type="string",
            required=True,
            group="connection",
            placeholder="mydb",
            description="Name of the database to connect to",
        ),
        ConfigField(
            name="username",
            label="Username",
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
            name="ssl",
            label="Use SSL",
            type="boolean",
            required=False,
            group="ssl",
            default_value=False,
        ),
        ConfigField(
            name="connection_timeout",
            label="Connection Timeout (seconds)",
            type="integer",
            required=False,
            group="advanced",
            default_value=30,
            min_value=5,
            max_value=300,
        ),
    ],
)

MYSQL_CAPABILITIES = AdapterCapabilities(
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
    source_type=SourceType.MYSQL,
    display_name="MySQL",
    category=SourceCategory.DATABASE,
    icon="mysql",
    description="Connect to MySQL databases for schema discovery and querying",
    capabilities=MYSQL_CAPABILITIES,
    config_schema=MYSQL_CONFIG_SCHEMA,
)
class MySQLAdapter(SQLAdapter):
    """MySQL database adapter.

    Provides full schema discovery and query execution for MySQL databases.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize MySQL adapter.

        Args:
            config: Configuration dictionary with:
                - host: Server hostname
                - port: Server port
                - database: Database name
                - username: Username
                - password: Password
                - ssl: Whether to use SSL (optional)
                - connection_timeout: Timeout in seconds (optional)
        """
        super().__init__(config)
        self._pool: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.MYSQL

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return MYSQL_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to MySQL."""
        try:
            import aiomysql
        except ImportError as e:
            raise ConnectionFailedError(
                message="aiomysql is not installed. Install with: pip install aiomysql",
                details={"error": str(e)},
            ) from e

        try:
            host = self._config.get("host", "localhost")
            port = self._config.get("port", 3306)
            database = self._config.get("database", "")
            username = self._config.get("username", "")
            password = self._config.get("password", "")
            use_ssl = self._config.get("ssl", False)
            timeout = self._config.get("connection_timeout", 30)

            ssl_context = None
            if use_ssl:
                import ssl

                ssl_context = ssl.create_default_context()

            self._pool = await aiomysql.create_pool(
                host=host,
                port=port,
                user=username,
                password=password,
                db=database,
                ssl=ssl_context,
                connect_timeout=timeout,
                minsize=1,
                maxsize=10,
                autocommit=True,
            )
            self._connected = True
        except Exception as e:
            error_str = str(e).lower()
            if "access denied" in error_str:
                raise AuthenticationFailedError(
                    message="Access denied for MySQL user",
                    details={"error": str(e)},
                ) from e
            elif "unknown database" in error_str:
                raise ConnectionFailedError(
                    message=f"Database does not exist: {self._config.get('database')}",
                    details={"error": str(e)},
                ) from e
            elif "timeout" in error_str or "timed out" in error_str:
                raise ConnectionTimeoutError(
                    message="Connection to MySQL timed out",
                    timeout_seconds=self._config.get("connection_timeout", 30),
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to MySQL: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close MySQL connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test MySQL connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT VERSION()")
                    result = await cur.fetchone()
                    version = result[0] if result else "Unknown"

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"MySQL {version}",
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
        """Execute a SQL query against MySQL."""
        if not self._connected or not self._pool:
            raise ConnectionFailedError(message="Not connected to MySQL")

        start_time = time.time()
        try:
            import aiomysql

            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Set query timeout
                    await cur.execute(f"SET max_execution_time = {timeout_seconds * 1000}")

                    # Execute query
                    await cur.execute(sql)
                    rows = await cur.fetchall()

                    execution_time_ms = int((time.time() - start_time) * 1000)

                    if not rows:
                        # Get columns from cursor description
                        columns = []
                        if cur.description:
                            columns = [
                                {"name": col[0], "data_type": "string"} for col in cur.description
                            ]
                        return QueryResult(
                            columns=columns,
                            rows=[],
                            row_count=0,
                            execution_time_ms=execution_time_ms,
                        )

                    # Get column info
                    columns = [{"name": col[0], "data_type": "string"} for col in cur.description]

                    # Convert rows to dicts (already dicts with DictCursor)
                    row_dicts = list(rows)

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
            if "syntax" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=sql[:200],
                ) from e
            elif "access denied" in error_str:
                raise AccessDeniedError(
                    message=str(e),
                ) from e
            elif "timeout" in error_str or "max_execution_time" in error_str:
                raise QueryTimeoutError(
                    message=str(e),
                    timeout_seconds=timeout_seconds,
                ) from e
            else:
                raise

    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        """Fetch table metadata from MySQL."""
        database = self._config.get("database", "")
        sql = f"""
            SELECT
                TABLE_CATALOG as table_catalog,
                TABLE_SCHEMA as table_schema,
                TABLE_NAME as table_name,
                TABLE_TYPE as table_type
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = '{database}'
            ORDER BY TABLE_NAME
        """
        result = await self.execute_query(sql)
        return list(result.rows)

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get MySQL schema."""
        if not self._connected or not self._pool:
            raise ConnectionFailedError(message="Not connected to MySQL")

        try:
            database = self._config.get("database", "")

            # Build filter conditions
            conditions = [f"TABLE_SCHEMA = '{database}'"]
            if filter:
                if filter.table_pattern:
                    conditions.append(f"TABLE_NAME LIKE '{filter.table_pattern}'")
                if not filter.include_views:
                    conditions.append("TABLE_TYPE = 'BASE TABLE'")

            where_clause = " AND ".join(conditions)
            limit_clause = f"LIMIT {filter.max_tables}" if filter else "LIMIT 1000"

            # Get tables
            tables_sql = f"""
                SELECT
                    TABLE_SCHEMA as table_schema,
                    TABLE_NAME as table_name,
                    TABLE_TYPE as table_type
                FROM information_schema.TABLES
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
                    ORDINAL_POSITION as ordinal_position,
                    COLUMN_KEY as column_key
                FROM information_schema.COLUMNS
                WHERE {where_clause}
                ORDER BY TABLE_NAME, ORDINAL_POSITION
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
                    is_pk = row.get("column_key") == "PRI"
                    col_data = {
                        "name": row["column_name"],
                        "data_type": normalize_type(row["data_type"], SourceType.MYSQL),
                        "native_type": row["data_type"],
                        "nullable": row["is_nullable"] == "YES",
                        "is_primary_key": is_pk,
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
                source_id=self._source_id or "mysql",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch MySQL schema: {str(e)}",
                details={"error": str(e)},
            ) from e

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build MySQL-specific sampling query."""
        # MySQL doesn't have TABLESAMPLE, use ORDER BY RAND()
        return f"SELECT * FROM {table} ORDER BY RAND() LIMIT {n}"
