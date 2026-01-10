"""SQLite adapter implementation.

This module provides a SQLite adapter for local/demo databases and
file-based data investigations. Uses Python's built-in sqlite3 module.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from dataing.adapters.datasource.errors import (
    ConnectionFailedError,
    QuerySyntaxError,
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

SQLITE_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
    ],
    fields=[
        ConfigField(
            name="path",
            label="Database Path",
            type="string",
            required=True,
            group="connection",
            placeholder="/path/to/database.sqlite",
            description="Path to SQLite file, or file: URI (e.g., file:db.sqlite?mode=ro)",
        ),
        ConfigField(
            name="read_only",
            label="Read Only",
            type="boolean",
            required=False,
            group="connection",
            default_value=True,
            description="Open database in read-only mode (recommended for investigations)",
        ),
    ],
)

SQLITE_CAPABILITIES = AdapterCapabilities(
    supports_sql=True,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=True,
    supports_preview=True,
    supports_write=False,
    query_language=QueryLanguage.SQL,
    max_concurrent_queries=1,
)


@register_adapter(
    source_type=SourceType.SQLITE,
    display_name="SQLite",
    category=SourceCategory.DATABASE,
    icon="sqlite",
    description="Connect to SQLite databases for local/demo data investigations",
    capabilities=SQLITE_CAPABILITIES,
    config_schema=SQLITE_CONFIG_SCHEMA,
)
class SQLiteAdapter(SQLAdapter):
    """SQLite database adapter.

    Provides schema discovery and query execution for SQLite databases.
    SQLite has no schema hierarchy, so we model it as a single catalog
    with a single schema containing all tables.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize SQLite adapter.

        Args:
            config: Configuration dictionary with:
                - path: Path to SQLite file or file: URI
                - read_only: Open in read-only mode (default True)
        """
        super().__init__(config)
        self._conn: sqlite3.Connection | None = None
        self._source_id: str = ""

    @property
    def source_type(self) -> SourceType:
        """Get the source type for this adapter."""
        return SourceType.SQLITE

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Get the capabilities of this adapter."""
        return SQLITE_CAPABILITIES

    def _build_uri(self) -> str:
        """Build SQLite URI from config."""
        path = self._config.get("path", "")
        read_only = self._config.get("read_only", True)

        if path.startswith("file:"):
            return path

        uri = f"file:{path}"
        if read_only:
            uri += "?mode=ro"
        return uri

    async def connect(self) -> None:
        """Establish connection to SQLite database."""
        path = self._config.get("path", "")

        if not path.startswith("file:") and not path.startswith(":memory:"):
            if not Path(path).exists():
                raise ConnectionFailedError(
                    message=f"SQLite database file not found: {path}",
                    details={"path": path},
                )

        try:
            uri = self._build_uri()
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._connected = True
        except sqlite3.OperationalError as e:
            raise ConnectionFailedError(
                message=f"Failed to open SQLite database: {e}",
                details={"path": path, "error": str(e)},
            ) from e

    async def disconnect(self) -> None:
        """Close SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> ConnectionTestResult:
        """Test SQLite connectivity."""
        start_time = time.time()
        try:
            if not self._connected:
                await self.connect()

            if self._conn is None:
                raise ConnectionFailedError(message="Connection not established")

            cursor = self._conn.execute("SELECT sqlite_version()")
            row = cursor.fetchone()
            version = row[0] if row else "Unknown"
            cursor.close()

            latency_ms = int((time.time() - start_time) * 1000)
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version=f"SQLite {version}",
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
        """Execute a SQL query against SQLite."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to SQLite")

        start_time = time.time()
        try:
            self._conn.execute(f"PRAGMA busy_timeout = {timeout_seconds * 1000}")

            cursor = self._conn.execute(sql)
            rows = cursor.fetchall()

            execution_time_ms = int((time.time() - start_time) * 1000)

            if not rows:
                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                )

            columns = [
                {"name": desc[0], "data_type": "string"}
                for desc in (cursor.description or [])
            ]

            row_dicts = [dict(row) for row in rows]

            truncated = False
            if limit and len(row_dicts) > limit:
                row_dicts = row_dicts[:limit]
                truncated = True

            cursor.close()

            return QueryResult(
                columns=columns,
                rows=row_dicts,
                row_count=len(row_dicts),
                truncated=truncated,
                execution_time_ms=execution_time_ms,
            )

        except sqlite3.OperationalError as e:
            error_str = str(e).lower()
            if "syntax error" in error_str or "near" in error_str:
                raise QuerySyntaxError(
                    message=str(e),
                    query=sql[:200],
                ) from e
            raise

    async def _fetch_table_metadata(self) -> list[dict[str, Any]]:
        """Fetch table metadata from SQLite."""
        if not self._conn:
            raise ConnectionFailedError(message="Not connected to SQLite")

        cursor = self._conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
        )
        tables = []
        for row in cursor:
            tables.append({
                "table_catalog": "default",
                "table_schema": "main",
                "table_name": row["name"],
                "table_type": row["type"].upper(),
            })
        cursor.close()
        return tables

    async def get_schema(
        self,
        filter: SchemaFilter | None = None,
    ) -> SchemaResponse:
        """Get database schema from SQLite."""
        if not self._connected or not self._conn:
            raise ConnectionFailedError(message="Not connected to SQLite")

        try:
            tables_cursor = self._conn.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            table_rows = tables_cursor.fetchall()
            tables_cursor.close()

            if filter:
                if filter.table_pattern:
                    pattern = filter.table_pattern.replace("%", ".*").replace("_", ".")
                    import re
                    table_rows = [
                        r for r in table_rows
                        if re.match(pattern, r["name"], re.IGNORECASE)
                    ]
                if not filter.include_views:
                    table_rows = [r for r in table_rows if r["type"] == "table"]
                if filter.max_tables:
                    table_rows = table_rows[:filter.max_tables]

            tables = []
            for table_row in table_rows:
                table_name = table_row["name"]
                table_type = "view" if table_row["type"] == "view" else "table"

                col_cursor = self._conn.execute(f"PRAGMA table_info('{table_name}')")
                col_rows = col_cursor.fetchall()
                col_cursor.close()

                columns = []
                for col in col_rows:
                    columns.append({
                        "name": col["name"],
                        "data_type": normalize_type(col["type"] or "TEXT", SourceType.SQLITE),
                        "native_type": col["type"] or "TEXT",
                        "nullable": not col["notnull"],
                        "is_primary_key": bool(col["pk"]),
                        "is_partition_key": False,
                        "default_value": col["dflt_value"],
                    })

                tables.append({
                    "name": table_name,
                    "table_type": table_type,
                    "native_type": table_row["type"].upper(),
                    "native_path": table_name,
                    "columns": columns,
                })

            catalogs = [
                {
                    "name": "default",
                    "schemas": [
                        {
                            "name": "main",
                            "tables": tables,
                        }
                    ],
                }
            ]

            return self._build_schema_response(
                source_id=self._source_id or "sqlite",
                catalogs=catalogs,
            )

        except Exception as e:
            raise SchemaFetchFailedError(
                message=f"Failed to fetch SQLite schema: {e}",
                details={"error": str(e)},
            ) from e

    def _build_sample_query(self, table: str, n: int) -> str:
        """Build SQLite-specific sampling query."""
        return f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT {n}"

    async def get_column_stats(
        self,
        table: str,
        columns: list[str],
        schema: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Get statistics for specific columns.

        SQLite doesn't support ::text casting, so we override the base method.
        """
        stats = {}

        for col in columns:
            sql = f"""
                SELECT
                    COUNT(*) as total_count,
                    COUNT("{col}") as non_null_count,
                    COUNT(DISTINCT "{col}") as distinct_count,
                    MIN("{col}") as min_value,
                    MAX("{col}") as max_value
                FROM "{table}"
            """
            try:
                result = await self.execute_query(sql, timeout_seconds=60)
                if result.rows:
                    row = result.rows[0]
                    total = row.get("total_count", 0)
                    non_null = row.get("non_null_count", 0)
                    null_count = total - non_null if total else 0
                    stats[col] = {
                        "null_count": null_count,
                        "null_rate": null_count / total if total > 0 else 0.0,
                        "distinct_count": row.get("distinct_count"),
                        "min_value": str(row.get("min_value")) if row.get("min_value") is not None else None,
                        "max_value": str(row.get("max_value")) if row.get("max_value") is not None else None,
                    }
            except Exception:
                stats[col] = {
                    "null_count": 0,
                    "null_rate": 0.0,
                    "distinct_count": None,
                    "min_value": None,
                    "max_value": None,
                }

        return stats
