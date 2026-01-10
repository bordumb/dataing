# SQLite Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SQLite as a data source adapter for local/demo databases and file-based investigations.

**Architecture:** Create a new `SQLiteAdapter` extending `SQLAdapter` base class, using Python's built-in `sqlite3` module. SQLite has no schema hierarchy (flat namespace), so we model it as a single default catalog with a single default schema containing all tables.

**Tech Stack:** Python sqlite3 (built-in), asyncio, pydantic

---

## Task 1: Add SQLITE to SourceType enum

**Files:**
- Modify: `dataing/src/dataing/adapters/datasource/types.py:16-43`

**Step 1: Add SQLITE enum value**

In `types.py`, add `SQLITE` to the `SourceType` enum in the SQL Databases section:

```python
class SourceType(str, Enum):
    """Supported data source types."""

    # SQL Databases
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    TRINO = "trino"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    DUCKDB = "duckdb"
    SQLITE = "sqlite"  # Add this line
```

**Step 2: Verify change**

Run: `cd dataing && uv run python -c "from dataing.adapters.datasource.types import SourceType; print(SourceType.SQLITE)"`
Expected: `SourceType.SQLITE`

**Step 3: Commit**

```bash
git add dataing/src/dataing/adapters/datasource/types.py
git commit -m "feat(adapters): add SQLITE to SourceType enum

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add SQLite type mappings

**Files:**
- Modify: `dataing/src/dataing/adapters/datasource/type_mapping.py`

**Step 1: Add SQLITE_TYPE_MAP dictionary**

After the DuckDB type map (~line 302), add:

```python
# SQLite type mappings
# SQLite has dynamic typing, but these are the common declared types
SQLITE_TYPE_MAP: dict[str, NormalizedType] = {
    # Integer types
    "integer": NormalizedType.INTEGER,
    "int": NormalizedType.INTEGER,
    "tinyint": NormalizedType.INTEGER,
    "smallint": NormalizedType.INTEGER,
    "mediumint": NormalizedType.INTEGER,
    "bigint": NormalizedType.INTEGER,
    "int2": NormalizedType.INTEGER,
    "int8": NormalizedType.INTEGER,
    # Float types
    "real": NormalizedType.FLOAT,
    "double": NormalizedType.FLOAT,
    "double precision": NormalizedType.FLOAT,
    "float": NormalizedType.FLOAT,
    # Decimal/Numeric types
    "numeric": NormalizedType.DECIMAL,
    "decimal": NormalizedType.DECIMAL,
    # String types
    "text": NormalizedType.STRING,
    "varchar": NormalizedType.STRING,
    "character": NormalizedType.STRING,
    "char": NormalizedType.STRING,
    "nchar": NormalizedType.STRING,
    "nvarchar": NormalizedType.STRING,
    "clob": NormalizedType.STRING,
    # Binary types
    "blob": NormalizedType.BINARY,
    # Boolean (SQLite stores as INTEGER 0/1)
    "boolean": NormalizedType.BOOLEAN,
    "bool": NormalizedType.BOOLEAN,
    # Date/Time types
    "date": NormalizedType.DATE,
    "datetime": NormalizedType.DATETIME,
    "timestamp": NormalizedType.TIMESTAMP,
    "time": NormalizedType.TIME,
}
```

**Step 2: Add SQLite to SOURCE_TYPE_MAPS**

In the `SOURCE_TYPE_MAPS` dictionary (~line 424), add:

```python
SourceType.SQLITE: SQLITE_TYPE_MAP,
```

**Step 3: Verify change**

Run: `cd dataing && uv run python -c "from dataing.adapters.datasource.type_mapping import normalize_type; from dataing.adapters.datasource.types import SourceType, NormalizedType; assert normalize_type('INTEGER', SourceType.SQLITE) == NormalizedType.INTEGER; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add dataing/src/dataing/adapters/datasource/type_mapping.py
git commit -m "feat(adapters): add SQLite type mappings

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update base adapter source category

**Files:**
- Modify: `dataing/src/dataing/adapters/datasource/base.py:189-200`

**Step 1: Add SQLITE to sql_types set**

In `_get_source_category()`, add `SourceType.SQLITE` to the `sql_types` set:

```python
sql_types = {
    SourceType.POSTGRESQL,
    SourceType.MYSQL,
    SourceType.TRINO,
    SourceType.SNOWFLAKE,
    SourceType.BIGQUERY,
    SourceType.REDSHIFT,
    SourceType.DUCKDB,
    SourceType.SQLITE,  # Add this line
    SourceType.MONGODB,
    SourceType.DYNAMODB,
    SourceType.CASSANDRA,
}
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/adapters/datasource/base.py
git commit -m "feat(adapters): include SQLITE in database source category

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create SQLite adapter

**Files:**
- Create: `dataing/src/dataing/adapters/datasource/sql/sqlite.py`

**Step 1: Create the SQLite adapter file**

Create `dataing/src/dataing/adapters/datasource/sql/sqlite.py`:

```python
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
    max_concurrent_queries=1,  # SQLite has limited concurrency
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

        # If already a file: URI, use as-is
        if path.startswith("file:"):
            return path

        # Build URI with read-only mode if requested
        uri = f"file:{path}"
        if read_only:
            uri += "?mode=ro"
        return uri

    async def connect(self) -> None:
        """Establish connection to SQLite database."""
        path = self._config.get("path", "")

        # Validate path exists (unless it's a URI with special options)
        if not path.startswith("file:") and not path.startswith(":memory:"):
            if not Path(path).exists():
                raise ConnectionFailedError(
                    message=f"SQLite database file not found: {path}",
                    details={"path": path},
                )

        try:
            uri = self._build_uri()
            # Use uri=True to enable URI mode for file: URIs
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
            # Set timeout (SQLite uses seconds)
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

            # Get column info from cursor description
            columns = [
                {"name": desc[0], "data_type": "string"}
                for desc in (cursor.description or [])
            ]

            # Convert sqlite3.Row to dict
            row_dicts = [dict(row) for row in rows]

            # Apply limit if needed
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
            # Get all tables
            tables_cursor = self._conn.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            table_rows = tables_cursor.fetchall()
            tables_cursor.close()

            # Apply filters
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

            # Build table list with columns
            tables = []
            for table_row in table_rows:
                table_name = table_row["name"]
                table_type = "view" if table_row["type"] == "view" else "table"

                # Get columns using PRAGMA table_info
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
                    "native_path": table_name,  # SQLite has flat namespace
                    "columns": columns,
                })

            # SQLite has no catalog/schema hierarchy - use defaults
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
        # SQLite doesn't have TABLESAMPLE, use ORDER BY RANDOM()
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
```

**Step 2: Verify file created**

Run: `ls -la dataing/src/dataing/adapters/datasource/sql/sqlite.py`
Expected: File exists

**Step 3: Verify import works**

Run: `cd dataing && uv run python -c "from dataing.adapters.datasource.sql.sqlite import SQLiteAdapter; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add dataing/src/dataing/adapters/datasource/sql/sqlite.py
git commit -m "feat(adapters): add SQLite adapter implementation

- Uses built-in sqlite3 module (no extra deps)
- Supports file paths and file: URIs
- Read-only mode by default for safety
- Flat namespace (single catalog/schema)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Update SQL adapters __init__.py

**Files:**
- Modify: `dataing/src/dataing/adapters/datasource/sql/__init__.py`

**Step 1: Add SQLiteAdapter export**

Update the file to:

```python
"""SQL database adapters.

This module provides adapters for SQL-speaking data sources:
- PostgreSQL
- MySQL
- Trino
- Snowflake
- BigQuery
- Redshift
- DuckDB
- SQLite
"""

from dataing.adapters.datasource.sql.base import SQLAdapter
from dataing.adapters.datasource.sql.sqlite import SQLiteAdapter

__all__ = ["SQLAdapter", "SQLiteAdapter"]
```

**Step 2: Verify import**

Run: `cd dataing && uv run python -c "from dataing.adapters.datasource.sql import SQLiteAdapter; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add dataing/src/dataing/adapters/datasource/sql/__init__.py
git commit -m "feat(adapters): export SQLiteAdapter from sql package

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Write unit tests for SQLite adapter

**Files:**
- Create: `dataing/tests/unit/adapters/datasource/sql/test_sqlite.py`

**Step 1: Create test file**

```python
"""Unit tests for SQLite adapter."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from dataing.adapters.datasource.sql.sqlite import SQLiteAdapter
from dataing.adapters.datasource.types import NormalizedType, SourceType


@pytest.fixture
def sample_db():
    """Create a temporary SQLite database with sample data."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            age INTEGER,
            created_at DATETIME
        )
    """)
    conn.execute("""
        INSERT INTO users (name, email, age, created_at)
        VALUES
            ('Alice', 'alice@example.com', 30, '2024-01-01'),
            ('Bob', 'bob@example.com', 25, '2024-01-02'),
            ('Charlie', NULL, 35, '2024-01-03')
    """)
    conn.execute("""
        CREATE VIEW active_users AS
        SELECT * FROM users WHERE age < 35
    """)
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestSQLiteAdapter:
    """Tests for SQLiteAdapter."""

    async def test_source_type(self, sample_db: str) -> None:
        """Test source_type property."""
        adapter = SQLiteAdapter({"path": sample_db})
        assert adapter.source_type == SourceType.SQLITE

    async def test_connect_success(self, sample_db: str) -> None:
        """Test successful connection."""
        adapter = SQLiteAdapter({"path": sample_db})
        await adapter.connect()
        assert adapter.is_connected
        await adapter.disconnect()
        assert not adapter.is_connected

    async def test_connect_file_not_found(self) -> None:
        """Test connection failure when file doesn't exist."""
        from dataing.adapters.datasource.errors import ConnectionFailedError

        adapter = SQLiteAdapter({"path": "/nonexistent/path.sqlite"})
        with pytest.raises(ConnectionFailedError) as exc_info:
            await adapter.connect()
        assert "not found" in str(exc_info.value).lower()

    async def test_test_connection(self, sample_db: str) -> None:
        """Test connection test returns version."""
        adapter = SQLiteAdapter({"path": sample_db})
        result = await adapter.test_connection()
        assert result.success
        assert "SQLite" in (result.server_version or "")

    async def test_execute_query(self, sample_db: str) -> None:
        """Test query execution."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.execute_query("SELECT * FROM users ORDER BY id")
            assert result.row_count == 3
            assert result.rows[0]["name"] == "Alice"

    async def test_execute_query_with_limit(self, sample_db: str) -> None:
        """Test query execution with limit."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.execute_query(
                "SELECT * FROM users ORDER BY id",
                limit=2,
            )
            assert result.row_count == 2

    async def test_execute_query_syntax_error(self, sample_db: str) -> None:
        """Test query syntax error handling."""
        from dataing.adapters.datasource.errors import QuerySyntaxError

        async with SQLiteAdapter({"path": sample_db}) as adapter:
            with pytest.raises(QuerySyntaxError):
                await adapter.execute_query("SELCT * FROM users")

    async def test_get_schema(self, sample_db: str) -> None:
        """Test schema discovery."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema()

            assert schema.source_type == SourceType.SQLITE
            assert len(schema.catalogs) == 1
            assert len(schema.catalogs[0].schemas) == 1

            tables = schema.get_all_tables()
            table_names = [t.name for t in tables]
            assert "users" in table_names
            assert "active_users" in table_names

            # Check users table columns
            users_table = next(t for t in tables if t.name == "users")
            col_names = [c.name for c in users_table.columns]
            assert "id" in col_names
            assert "name" in col_names
            assert "email" in col_names

            # Check id is primary key
            id_col = next(c for c in users_table.columns if c.name == "id")
            assert id_col.is_primary_key

    async def test_get_schema_exclude_views(self, sample_db: str) -> None:
        """Test schema discovery with views excluded."""
        from dataing.adapters.datasource.types import SchemaFilter

        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema(
                filter=SchemaFilter(include_views=False)
            )

            tables = schema.get_all_tables()
            table_names = [t.name for t in tables]
            assert "users" in table_names
            assert "active_users" not in table_names

    async def test_count_rows(self, sample_db: str) -> None:
        """Test row counting."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            count = await adapter.count_rows("users")
            assert count == 3

    async def test_sample(self, sample_db: str) -> None:
        """Test sampling."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.sample("users", n=2)
            assert result.row_count == 2

    async def test_preview(self, sample_db: str) -> None:
        """Test preview."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            result = await adapter.preview("users", n=2)
            assert result.row_count == 2

    async def test_get_column_stats(self, sample_db: str) -> None:
        """Test column statistics."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            stats = await adapter.get_column_stats("users", ["email", "age"])

            assert "email" in stats
            assert stats["email"]["null_count"] == 1
            assert stats["email"]["distinct_count"] == 2

            assert "age" in stats
            assert stats["age"]["null_count"] == 0

    async def test_read_only_mode(self, sample_db: str) -> None:
        """Test read-only mode prevents writes."""
        async with SQLiteAdapter({"path": sample_db, "read_only": True}) as adapter:
            # Read should work
            result = await adapter.execute_query("SELECT * FROM users")
            assert result.row_count == 3

            # Write should fail in read-only mode
            with pytest.raises(Exception):  # sqlite3.OperationalError
                await adapter.execute_query(
                    "INSERT INTO users (name) VALUES ('Test')"
                )

    async def test_uri_mode(self, sample_db: str) -> None:
        """Test file: URI mode."""
        uri = f"file:{sample_db}?mode=ro"
        async with SQLiteAdapter({"path": uri}) as adapter:
            result = await adapter.execute_query("SELECT COUNT(*) as cnt FROM users")
            assert result.rows[0]["cnt"] == 3

    async def test_context_manager(self, sample_db: str) -> None:
        """Test async context manager."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            assert adapter.is_connected
        assert not adapter.is_connected

    async def test_type_normalization(self, sample_db: str) -> None:
        """Test type normalization in schema."""
        async with SQLiteAdapter({"path": sample_db}) as adapter:
            schema = await adapter.get_schema()
            users_table = next(
                t for t in schema.get_all_tables() if t.name == "users"
            )

            id_col = next(c for c in users_table.columns if c.name == "id")
            assert id_col.data_type == NormalizedType.INTEGER

            name_col = next(c for c in users_table.columns if c.name == "name")
            assert name_col.data_type == NormalizedType.STRING

            created_col = next(c for c in users_table.columns if c.name == "created_at")
            assert created_col.data_type == NormalizedType.DATETIME
```

**Step 2: Run tests to verify they fail (TDD - need implementation first)**

Run: `cd dataing && uv run pytest tests/unit/adapters/datasource/sql/test_sqlite.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add dataing/tests/unit/adapters/datasource/sql/test_sqlite.py
git commit -m "test(adapters): add comprehensive SQLite adapter unit tests

Tests cover:
- Connection (success, file not found, read-only)
- Query execution (basic, limit, syntax error)
- Schema discovery (tables, views, columns, filters)
- Sampling and preview
- Column statistics
- Type normalization
- Context manager

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Run linting and type checking

**Files:**
- None (verification only)

**Step 1: Run ruff**

Run: `cd dataing && uv run ruff check src/dataing/adapters/datasource/sql/sqlite.py --fix`
Expected: No errors (or auto-fixed)

**Step 2: Run mypy**

Run: `cd dataing && uv run mypy src/dataing/adapters/datasource/sql/sqlite.py`
Expected: No errors

**Step 3: Run all tests**

Run: `cd dataing && uv run pytest tests/unit/adapters/datasource/sql/test_sqlite.py -v`
Expected: All tests pass

**Step 4: Commit any fixes**

```bash
git add -u
git commit -m "fix(adapters): address linting/type issues in SQLite adapter

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Files | Action |
|------|-------|--------|
| 1 | `types.py` | Add SQLITE to SourceType enum |
| 2 | `type_mapping.py` | Add SQLite type mappings |
| 3 | `base.py` | Add SQLITE to sql_types set |
| 4 | `sql/sqlite.py` | Create SQLite adapter |
| 5 | `sql/__init__.py` | Export SQLiteAdapter |
| 6 | `tests/.../test_sqlite.py` | Add unit tests |
| 7 | N/A | Run linting and verification |

Total: ~250 lines of adapter code + ~200 lines of tests
