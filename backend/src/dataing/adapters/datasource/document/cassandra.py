"""Apache Cassandra adapter implementation.

This module provides a Cassandra adapter that implements the unified
data source interface with schema discovery and CQL query capabilities.
"""

from __future__ import annotations

import time
from typing import Any

from dataing.adapters.datasource.document.base import DocumentAdapter
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
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    ConfigField,
    ConfigSchema,
    ConnectionTestResult,
    FieldGroup,
    NormalizedType,
    QueryLanguage,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
)

CASSANDRA_TYPE_MAP = {
    "ascii": NormalizedType.STRING,
    "bigint": NormalizedType.INTEGER,
    "blob": NormalizedType.BINARY,
    "boolean": NormalizedType.BOOLEAN,
    "counter": NormalizedType.INTEGER,
    "date": NormalizedType.DATE,
    "decimal": NormalizedType.DECIMAL,
    "double": NormalizedType.FLOAT,
    "duration": NormalizedType.STRING,
    "float": NormalizedType.FLOAT,
    "inet": NormalizedType.STRING,
    "int": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "text": NormalizedType.STRING,
    "time": NormalizedType.TIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "timeuuid": NormalizedType.STRING,
    "tinyint": NormalizedType.INTEGER,
    "uuid": NormalizedType.STRING,
    "varchar": NormalizedType.STRING,
    "varint": NormalizedType.INTEGER,
    "list": NormalizedType.ARRAY,
    "set": NormalizedType.ARRAY,
    "map": NormalizedType.MAP,
    "tuple": NormalizedType.STRUCT,
    "frozen": NormalizedType.STRUCT,
}

CASSANDRA_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
        FieldGroup(id="auth", label="Authentication", collapsed_by_default=False),
        FieldGroup(id="advanced", label="Advanced", collapsed_by_default=True),
    ],
    fields=[
        ConfigField(
            name="hosts",
            label="Contact Points",
            type="string",
            required=True,
            group="connection",
            placeholder="host1.example.com,host2.example.com",
            description="Comma-separated list of Cassandra hosts",
        ),
        ConfigField(
            name="port",
            label="Port",
            type="integer",
            required=True,
            group="connection",
            default_value=9042,
            min_value=1,
            max_value=65535,
        ),
        ConfigField(
            name="keyspace",
            label="Keyspace",
            type="string",
            required=True,
            group="connection",
            placeholder="my_keyspace",
            description="Default keyspace to connect to",
        ),
        ConfigField(
            name="username",
            label="Username",
            type="string",
            required=False,
            group="auth",
            description="Username for authentication (optional)",
        ),
        ConfigField(
            name="password",
            label="Password",
            type="secret",
            required=False,
            group="auth",
            description="Password for authentication (optional)",
        ),
        ConfigField(
            name="ssl_enabled",
            label="Enable SSL",
            type="boolean",
            required=False,
            group="advanced",
            default_value=False,
        ),
        ConfigField(
            name="connection_timeout",
            label="Connection Timeout (seconds)",
            type="integer",
            required=False,
            group="advanced",
            default_value=10,
            min_value=1,
            max_value=120,
        ),
        ConfigField(
            name="request_timeout",
            label="Request Timeout (seconds)",
            type="integer",
            required=False,
            group="advanced",
            default_value=10,
            min_value=1,
            max_value=300,
        ),
    ],
)

CASSANDRA_CAPABILITIES = AdapterCapabilities(
    supports_sql=False,
    supports_sampling=True,
    supports_row_count=False,
    supports_column_stats=False,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SCAN_ONLY,
    max_concurrent_queries=5,
)


@register_adapter(
    source_type=SourceType.CASSANDRA,
    display_name="Apache Cassandra",
    category=SourceCategory.DATABASE,
    icon="cassandra",
    description="Connect to Apache Cassandra or ScyllaDB clusters",
    capabilities=CASSANDRA_CAPABILITIES,
    config_schema=CASSANDRA_CONFIG_SCHEMA,
)
class CassandraAdapter(DocumentAdapter):
    """Apache Cassandra adapter.

    Provides schema discovery and CQL query execution for Cassandra clusters.
    Uses cassandra-driver for connection.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Cassandra adapter.

        Args:
            config: Configuration dictionary with:
                - hosts: Comma-separated contact points
                - port: Native protocol port
                - keyspace: Default keyspace
                - username: Username (optional)
                - password: Password (optional)
                - ssl_enabled: Enable SSL (optional)
                - connection_timeout: Connect timeout (optional)
                - request_timeout: Request timeout (optional)
        """
        super().__init__(config)
        self._cluster: Any = None
        self._session: Any = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.CASSANDRA

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return CASSANDRA_CAPABILITIES

    async def connect(self) -> None:
        """Establish connection to Cassandra."""
        try:
            from cassandra.auth import PlainTextAuthProvider
            from cassandra.cluster import Cluster
        except ImportError as e:
            raise ConnectionFailedError(
                message="cassandra-driver not installed. Install: pip install cassandra-driver",
                details={"error": str(e)},
            ) from e

        try:
            hosts_str = self._config.get("hosts", "localhost")
            hosts = [h.strip() for h in hosts_str.split(",")]
            port = self._config.get("port", 9042)
            keyspace = self._config.get("keyspace")
            username = self._config.get("username")
            password = self._config.get("password")
            connect_timeout = self._config.get("connection_timeout", 10)

            auth_provider = None
            if username and password:
                auth_provider = PlainTextAuthProvider(
                    username=username,
                    password=password,
                )

            self._cluster = Cluster(
                contact_points=hosts,
                port=port,
                auth_provider=auth_provider,
                connect_timeout=connect_timeout,
            )

            self._session = self._cluster.connect(keyspace)
            self._connected = True

        except Exception as e:
            error_str = str(e).lower()
            if "authentication" in error_str or "credentials" in error_str:
                raise AuthenticationFailedError(
                    message="Cassandra authentication failed",
                    details={"error": str(e)},
                ) from e
            elif "timeout" in error_str:
                raise ConnectionTimeoutError(
                    message="Connection to Cassandra timed out",
                    timeout_seconds=self._config.get("connection_timeout", 10),
                ) from e
            else:
                raise ConnectionFailedError(
                    message=f"Failed to connect to Cassandra: {str(e)}",
                    details={"error": str(e)},
                ) from e

    async def disconnect(self) -> None:
        """Close Cassandra connection."""
        if self._session:
            self._session.shutdown()
            self._session = None
        if self._cluster:
            self._cluster.shutdown()
            self._cluster = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test Cassandra connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            row = self._session.execute("SELECT release_version FROM system.local").one()
            version = row.release_version if row else "Unknown"

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"Cassandra {version}",
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

    async def scan_collection(
        self,
        name: str,
        filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Scan a Cassandra table."""
        if not self._connected or not self._session:
            raise ConnectionFailedError(message="Not connected to Cassandra")

        start_time = time.time()
        try:
            keyspace = self._config.get("keyspace", "")
            full_table = f"{keyspace}.{name}" if keyspace and "." not in name else name

            cql = f"SELECT * FROM {full_table}"

            if filter:
                where_parts = []
                for key, value in filter.items():
                    if isinstance(value, str):
                        where_parts.append(f"{key} = '{value}'")
                    else:
                        where_parts.append(f"{key} = {value}")
                if where_parts:
                    cql += " WHERE " + " AND ".join(where_parts) + " ALLOW FILTERING"

            cql += f" LIMIT {limit}"

            rows = self._session.execute(cql)
            execution_time_ms = int((time.time() - start_time) * 1000)

            rows_list = list(rows)
            if not rows_list:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            columns = [{"name": col, "data_type": "string"} for col in rows_list[0]._fields]

            row_dicts = [dict(row._asdict()) for row in rows_list]

            return QueryResult(
                columns=columns,
                rows=row_dicts,
                row_count=len(row_dicts),
                truncated=len(row_dicts) >= limit,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            error_str = str(e).lower()
            if "syntax error" in error_str:
                raise QuerySyntaxError(message=str(e), query=cql[:200]) from e
            elif "unauthorized" in error_str or "permission" in error_str:
                raise AccessDeniedError(message=str(e)) from e
            elif "timeout" in error_str:
                raise QueryTimeoutError(message=str(e), timeout_seconds=30) from e
            raise

    async def sample(
        self,
        name: str,
        n: int = 100,
    ) -> QueryResult:
        """Sample rows from a Cassandra table."""
        return await self.scan_collection(name, limit=n)

    def _normalize_type(self, cql_type: str) -> NormalizedType:
        """Normalize a CQL type to our standard types."""
        cql_type_lower = cql_type.lower()

        for type_prefix, normalized in CASSANDRA_TYPE_MAP.items():
            if cql_type_lower.startswith(type_prefix):
                return normalized

        return NormalizedType.UNKNOWN

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get Cassandra schema."""
        if not self._connected or not self._session:
            raise ConnectionFailedError(message="Not connected to Cassandra")

        try:
            keyspace = self._config.get("keyspace")

            if keyspace:
                keyspaces = [keyspace]
            else:
                ks_rows = self._session.execute("SELECT keyspace_name FROM system_schema.keyspaces")
                keyspaces = [
                    row.keyspace_name
                    for row in ks_rows
                    if not row.keyspace_name.startswith("system")
                ]

            schemas = []
            for ks in keyspaces:
                tables_cql = f"""
                    SELECT table_name
                    FROM system_schema.tables
                    WHERE keyspace_name = '{ks}'
                """
                table_rows = self._session.execute(tables_cql)
                table_names = [row.table_name for row in table_rows]

                if filter and filter.table_pattern:
                    table_names = [t for t in table_names if filter.table_pattern in t]

                if filter and filter.max_tables:
                    table_names = table_names[: filter.max_tables]

                tables = []
                for table_name in table_names:
                    columns_cql = f"""
                        SELECT column_name, type, kind
                        FROM system_schema.columns
                        WHERE keyspace_name = '{ks}' AND table_name = '{table_name}'
                    """
                    col_rows = self._session.execute(columns_cql)

                    columns = []
                    for col in col_rows:
                        columns.append(
                            {
                                "name": col.column_name,
                                "data_type": self._normalize_type(col.type),
                                "native_type": col.type,
                                "nullable": col.kind not in ("partition_key", "clustering"),
                                "is_primary_key": col.kind == "partition_key",
                                "is_partition_key": col.kind == "clustering",
                            }
                        )

                    tables.append(
                        {
                            "name": table_name,
                            "table_type": "table",
                            "native_type": "CASSANDRA_TABLE",
                            "native_path": f"{ks}.{table_name}",
                            "columns": columns,
                        }
                    )

                schemas.append(
                    {
                        "name": ks,
                        "tables": tables,
                    }
                )

            catalogs = [
                {
                    "name": "default",
                    "schemas": schemas,
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "cassandra",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch Cassandra schema: {str(e)}",
                details={"error": str(e)},
            ) from e
