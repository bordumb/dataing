"""PostgreSQL adapter implementation.

This module provides a PostgreSQL adapter that implements the unified
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

# PostgreSQL configuration schema for frontend forms
POSTGRES_CONFIG_SCHEMA = ConfigSchema(
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
            description="PostgreSQL server hostname or IP address",
        ),
        ConfigField(
            name="port",
            label="Port",
            type="integer",
            required=True,
            group="connection",
            default_value=5432,
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
            name="ssl_mode",
            label="SSL Mode",
            type="enum",
            required=False,
            group="ssl",
            default_value="prefer",
            options=[
                {"value": "disable", "label": "Disable"},
                {"value": "prefer", "label": "Prefer"},
                {"value": "require", "label": "Require"},
                {"value": "verify-ca", "label": "Verify CA"},
                {"value": "verify-full", "label": "Verify Full"},
            ],
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
        ConfigField(
            name="schemas",
            label="Schemas to Include",
            type="string",
            required=False,
            group="advanced",
            placeholder="public,analytics",
            description="Comma-separated list of schemas to include (default: all)",
        ),
    ],
)

POSTGRES_CAPABILITIES = AdapterCapabilities(
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
    source_type=SourceType.POSTGRESQL,
    display_name="PostgreSQL",
    category=SourceCategory.DATABASE,
    icon="postgresql",
    description="Connect to PostgreSQL databases for schema discovery and querying",
    capabilities=POSTGRES_CAPABILITIES,
    config_schema=POSTGRES_CONFIG_SCHEMA,
)
class PostgresAdapter(SQLAdapter):
    """PostgreSQL database adapter.

    Provides full schema discovery and query execution for PostgreSQL databases.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize PostgreSQL adapter.

        Args:
            config: Configuration dictionary with:
                - host: Server hostname
                - port: Server port
                - database: Database name
                - username: Username
                - password: Password
                - ssl_mode: SSL mode (optional)
                - connection_timeout: Timeout in seconds (optional)
                - schemas: Comma-separated schemas to include (optional)
        """
        super().__init__(config)
        self._pool: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.POSTGRESQL

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return POSTGRES_CAPABILITIES

    def _build_dsn(self) -> str:
        """Build PostgreSQL DSN from config."""
        host = self._config.get("host", "localhost")
        port = self._config.get("port", 5432)
        database = self._config.get("database", "postgres")
        username = self._config.get("username", "")
        password = self._config.get("password", "")
        ssl_mode = self._config.get("ssl_mode", "prefer")

        return f"postgresql://{username}:{password}@{host}:{port}/{database}?sslmode={ssl_mode}"

    async def connect(self) -> None:
        """Establish connection to PostgreSQL."""
        try:
            import asyncpg
        except ImportError as e:
            raise ConnectionFailedError(
                message="asyncpg is not installed. Install with: pip install asyncpg",
                details={"error": str(e)},
            ) from e

        try:
            timeout = self._config.get("connection_timeout", 30)
            self._pool = await asyncpg.create_pool(
                self._build_dsn(),
                min_size=1,
                max_size=10,
                command_timeout=timeout,
            )
            self._connected = True
        except asyncpg.InvalidPasswordError as e:
            raise AuthenticationFailedError(
                message="Password authentication failed for PostgreSQL",
                details={"error": str(e)},
            ) from e
        except asyncpg.InvalidCatalogNameError as e:
            raise ConnectionFailedError(
                message=f"Database does not exist: {self._config.get('database')}",
                details={"error": str(e)},
            ) from e
        except asyncpg.CannotConnectNowError as e:
            raise ConnectionFailedError(
                message="Cannot connect to PostgreSQL server",
                details={"error": str(e)},
            ) from e
        except TimeoutError as e:
            raise ConnectionTimeoutError(
                message="Connection to PostgreSQL timed out",
                timeout_seconds=self._config.get("connection_timeout", 30),
            ) from e
        except Exception as e:
            raise ConnectionFailedError(
                message=f"Failed to connect to PostgreSQL: {str(e)}",
                details={"error": str(e)},
            ) from e

    async def disconnect(self) -> None:
        """Close PostgreSQL connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test PostgreSQL connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            async with self._pool.acquire() as conn:
                result = await conn.fetchrow("SELECT version()")
                version = result[0] if result else "Unknown"

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
        """Execute a SQL query."""
        if not self._connected or not self._pool:
            raise ConnectionFailedError(message="Not connected to PostgreSQL")

        start_time = time.time()
        try:
            async with self._pool.acquire() as conn:
                # Set statement timeout
                await conn.execute(f"SET statement_timeout = {timeout_seconds * 1000}")

                # Execute query
                rows = await conn.fetch(sql)

                execution_time_ms = int((time.time() - start_time) * 1000)

                if not rows:
                    return QueryResult(
                        columns=[],
                        rows=[],
                        row_count=0,
                        execution_time_ms=execution_time_ms,
                    )

                # Get column info
                columns = [{"name": key, "data_type": "string"} for key in rows[0].keys()]

                # Convert rows to dicts
                row_dicts = [dict(row) for row in rows]

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
            if "syntax error" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=sql[:200],
                ) from e
            elif "permission denied" in error_str:
                raise AccessDeniedError(
                    message=str(e),
                ) from e
            elif "canceling statement" in error_str or "timeout" in error_str:
                raise QueryTimeoutError(
                    message=str(e),
                    timeout_seconds=timeout_seconds,
                ) from e
            else:
                raise

    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        """Fetch table metadata from PostgreSQL."""
        schemas_filter = self._config.get("schemas", "")
        if schemas_filter:
            schema_list = [s.strip() for s in schemas_filter.split(",")]
            schema_condition = f"AND table_schema IN ({','.join(repr(s) for s in schema_list)})"
        else:
            schema_condition = "AND table_schema NOT IN ('pg_catalog', 'information_schema')"

        sql = f"""
            SELECT
                table_catalog,
                table_schema,
                table_name,
                table_type
            FROM information_schema.tables
            WHERE 1=1
            {schema_condition}
            ORDER BY table_schema, table_name
        """

        result = await self.execute_query(sql)
        return list(result.rows)

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get database schema."""
        if not self._connected or not self._pool:
            raise ConnectionFailedError(message="Not connected to PostgreSQL")

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

            # Get columns for all tables
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

            # Get primary keys
            pk_sql = f"""
                SELECT
                    kcu.table_schema,
                    kcu.table_name,
                    kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND {where_clause.replace('table_schema', 'tc.table_schema')
                        .replace('table_name', 'tc.table_name')
                        .replace('table_type', "'BASE TABLE'")}
            """
            try:
                pk_result = await self.execute_query(pk_sql)
                pk_set = {
                    (row["table_schema"], row["table_name"], row["column_name"])
                    for row in pk_result.rows
                }
            except Exception:
                pk_set = set()

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
                    is_pk = (schema_name, table_name, row["column_name"]) in pk_set
                    col_data = {
                        "name": row["column_name"],
                        "data_type": normalize_type(row["data_type"], SourceType.POSTGRESQL),
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
                    "name": self._config.get("database", "default"),
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
                source_id=self._source_id or "postgres",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch PostgreSQL schema: {str(e)}",
                details={"error": str(e)},
            ) from e

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build PostgreSQL-specific sampling query using TABLESAMPLE."""
        # Use TABLESAMPLE SYSTEM for larger tables, random for smaller
        return f"""
            SELECT * FROM {table}
            TABLESAMPLE SYSTEM (10)
            LIMIT {n}
        """
