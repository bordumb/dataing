"""SchemaFilter values reach the database as bound parameters, never as SQL text.

get_schema used to splice table_pattern and schema_pattern into its queries, so a
pattern such as "x' OR '1'='1" rewrote the query that runs with the datasource's
stored credentials. These tests pin the fix: the SQL text never depends on the
filter values, the values travel as parameters, and every driver binds them.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from typing import Any, NamedTuple
from unittest.mock import AsyncMock

import duckdb
import pytest

from dataing.adapters.datasource.sql.base import SQLAdapter
from dataing.adapters.datasource.sql.bigquery import BigQueryAdapter
from dataing.adapters.datasource.sql.duckdb import DuckDBAdapter
from dataing.adapters.datasource.sql.mysql import MySQLAdapter
from dataing.adapters.datasource.sql.postgres import PostgresAdapter
from dataing.adapters.datasource.sql.redshift import RedshiftAdapter
from dataing.adapters.datasource.sql.snowflake import SnowflakeAdapter
from dataing.adapters.datasource.sql.sqlite import SQLiteAdapter
from dataing.adapters.datasource.sql.trino import TrinoAdapter
from dataing.adapters.datasource.types import QueryResult, SchemaFilter, SchemaResponse

HOSTILE_PATTERNS = [
    "x' OR '1'='1",
    "%'; --",
    "x\\' OR 1=1 --",
    "' UNION SELECT 'a', 'b', 'BASE TABLE' --",
]

ADAPTERS = [
    pytest.param(PostgresAdapter, {"database": "shop"}, id="postgres"),
    pytest.param(RedshiftAdapter, {"database": "dev"}, id="redshift"),
    pytest.param(MySQLAdapter, {"database": "shop"}, id="mysql"),
    pytest.param(SnowflakeAdapter, {"database": "SHOP", "schema": "PUBLIC"}, id="snowflake"),
    pytest.param(TrinoAdapter, {"catalog": "hive", "schema": "default"}, id="trino"),
    pytest.param(BigQueryAdapter, {"project_id": "proj", "dataset": "shop"}, id="bigquery"),
    pytest.param(DuckDBAdapter, {"source_type": "database"}, id="duckdb"),
]


def _recording_adapter(adapter_cls: type[SQLAdapter], config: dict[str, Any]) -> Any:
    """Build a connected-looking adapter whose execute_query records its calls."""
    adapter = adapter_cls(config)
    adapter._connected = True
    for handle in ("_pool", "_conn", "_client"):
        if hasattr(adapter, handle):
            setattr(adapter, handle, object())
    adapter.execute_query = AsyncMock(  # type: ignore[method-assign]
        return_value=QueryResult(columns=[], rows=[], row_count=0)
    )
    return adapter


async def _schema_queries(adapter: Any, schema_filter: SchemaFilter) -> list[tuple[str, list[Any]]]:
    """Run get_schema and return the (sql, params) of every query it issued."""
    await adapter.get_schema(schema_filter)
    queries = []
    for call in adapter.execute_query.await_args_list:
        params = call.args[1] if len(call.args) > 1 else call.kwargs.get("params")
        queries.append((call.args[0], list(params or [])))
    return queries


@pytest.mark.parametrize("adapter_cls, config", ADAPTERS)
@pytest.mark.parametrize("pattern", HOSTILE_PATTERNS)
async def test_filter_values_are_bound_not_spliced(
    adapter_cls: type[SQLAdapter], config: dict[str, Any], pattern: str
) -> None:
    """A hostile pattern leaves the SQL text unchanged and travels as a parameter."""
    benign = await _schema_queries(
        _recording_adapter(adapter_cls, config),
        SchemaFilter(table_pattern="orders", schema_pattern="public"),
    )
    hostile = await _schema_queries(
        _recording_adapter(adapter_cls, config),
        SchemaFilter(table_pattern=pattern, schema_pattern=pattern),
    )

    assert [sql for sql, _ in hostile] == [sql for sql, _ in benign]
    assert not any(pattern in sql for sql, _ in hostile)
    tables_params = hostile[0][1]
    assert pattern in tables_params


@pytest.mark.parametrize("adapter_cls, config", ADAPTERS)
async def test_include_views_false_filters_tables_not_columns(
    adapter_cls: type[SQLAdapter], config: dict[str, Any]
) -> None:
    """Only the tables query filters on table_type; information_schema.columns has none."""
    queries = await _schema_queries(
        _recording_adapter(adapter_cls, config), SchemaFilter(include_views=False)
    )
    tables_sql = [sql.lower() for sql, _ in queries if "information_schema.tables" in sql.lower()]
    columns_sql = [sql.lower() for sql, _ in queries if "information_schema.columns" in sql.lower()]

    assert tables_sql
    assert all("table_type = 'base table'" in sql for sql in tables_sql)
    assert columns_sql
    assert not any("table_type" in sql for sql in columns_sql)


# Each driver must receive the params, not just the SQL.

INJECTION = "x' OR '1'='1"


class _Pool:
    """Stand-in for an asyncpg or aiomysql pool that hands out one connection."""

    def __init__(self, conn: Any) -> None:
        """Initialize the pool."""
        self.conn = conn

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """Yield the connection."""
        yield self.conn


class _AsyncpgConnection:
    """Records what asyncpg's Connection.fetch receives."""

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.fetched: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, sql: str) -> None:
        """Accept the statement_timeout SET."""

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        """Record the query and its bound arguments."""
        self.fetched.append((sql, args))
        return []


class _AiomysqlCursor:
    """Records what aiomysql's Cursor.execute receives."""

    description = None

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.executed: list[tuple[str, Any]] = []

    async def execute(self, sql: str, args: Any = None) -> None:
        """Record the query and its arguments."""
        self.executed.append((sql, args))

    async def fetchall(self) -> list[Any]:
        """Return no rows."""
        return []


class _AiomysqlConnection:
    """Hands out one aiomysql cursor."""

    def __init__(self, cursor: _AiomysqlCursor) -> None:
        """Initialize the connection."""
        self._cursor = cursor

    @asynccontextmanager
    async def cursor(self, cursor_cls: Any) -> AsyncIterator[_AiomysqlCursor]:
        """Yield the cursor."""
        yield self._cursor


class _DbapiCursor:
    """Records what a DB-API cursor (Snowflake, Trino) receives."""

    description = None

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.executed: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        """Record the query and its parameters."""
        self.executed.append((sql, params))

    def fetchall(self) -> list[Any]:
        """Return no rows."""
        return []

    def close(self) -> None:
        """Nothing to release."""


class _BigQueryParam(NamedTuple):
    """Mirror of google.cloud.bigquery.ScalarQueryParameter's arguments."""

    name: str | None
    type_: str
    value: Any


class _BigQueryClient:
    """Records the SQL and job config that BigQuery's Client.query receives."""

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.queries: list[tuple[str, Any]] = []

    def query(self, sql: str, job_config: Any) -> Any:
        """Record the query and return a job with an empty result."""
        self.queries.append((sql, job_config))
        return SimpleNamespace(result=lambda timeout: SimpleNamespace(schema=[]))


@pytest.mark.parametrize("adapter_cls", [PostgresAdapter, RedshiftAdapter])
async def test_asyncpg_adapters_bind_params(adapter_cls: type[SQLAdapter]) -> None:
    """Postgres and Redshift pass params to asyncpg as $n arguments."""
    conn = _AsyncpgConnection()
    adapter: Any = adapter_cls({})
    adapter._pool, adapter._connected = _Pool(conn), True

    await adapter.execute_query("SELECT $1", [INJECTION])

    assert conn.fetched == [("SELECT $1", (INJECTION,))]


async def test_mysql_binds_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """MySQL passes params to aiomysql, which escapes them for %s placeholders."""
    monkeypatch.setitem(sys.modules, "aiomysql", SimpleNamespace(DictCursor=object))
    cursor = _AiomysqlCursor()
    adapter: Any = MySQLAdapter({})
    adapter._pool, adapter._connected = _Pool(_AiomysqlConnection(cursor)), True

    await adapter.execute_query("SELECT %s", [INJECTION])

    sql, args = cursor.executed[-1]
    assert sql == "SELECT %s"
    assert list(args or ()) == [INJECTION]


@pytest.mark.parametrize("adapter_cls", [SnowflakeAdapter, TrinoAdapter])
async def test_dbapi_adapters_bind_params(adapter_cls: type[SQLAdapter]) -> None:
    """Snowflake (%s) and Trino (?) pass params to their DB-API cursors."""
    cursor = _DbapiCursor()
    adapter: Any = adapter_cls({})
    adapter._conn, adapter._connected = SimpleNamespace(cursor=lambda: cursor), True

    await adapter.execute_query("SELECT ?", [INJECTION])

    sql, params = cursor.executed[-1]
    assert sql == "SELECT ?"
    assert list(params or ()) == [INJECTION]


async def test_bigquery_binds_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """BigQuery sends params as typed positional query parameters."""
    bigquery = ModuleType("google.cloud.bigquery")
    bigquery.QueryJobConfig = SimpleNamespace  # type: ignore[attr-defined]
    bigquery.ScalarQueryParameter = _BigQueryParam  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)
    client = _BigQueryClient()
    adapter: Any = BigQueryAdapter({"project_id": "proj"})
    adapter._client, adapter._connected = client, True

    await adapter.execute_query("SELECT ?, ?", [INJECTION, 7])

    sql, job_config = client.queries[-1]
    assert sql == "SELECT ?, ?"
    assert getattr(job_config, "query_parameters", None) == [
        _BigQueryParam(None, "STRING", INJECTION),
        _BigQueryParam(None, "INT64", 7),
    ]


async def test_duckdb_binds_params() -> None:
    """DuckDB returns a bound value verbatim instead of executing it."""
    adapter: Any = DuckDBAdapter({"source_type": "database"})
    adapter._conn, adapter._connected = duckdb.connect(), True

    result = await adapter.execute_query("SELECT ? AS v", [INJECTION])

    assert result.rows == [{"v": INJECTION}]


async def test_sqlite_binds_params() -> None:
    """SQLite returns a bound value verbatim instead of executing it."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    adapter: Any = SQLiteAdapter({"path": ":memory:"})
    adapter._conn, adapter._connected = conn, True

    result = await adapter.execute_query("SELECT ? AS v", [INJECTION])

    assert result.rows == [{"v": INJECTION}]


# End to end against a real DuckDB database.


@pytest.fixture
def shop_duckdb() -> Iterator[Any]:
    """DuckDB adapter over two tables and a view."""
    conn = duckdb.connect()
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount DOUBLE)")
    conn.execute("CREATE TABLE secrets (token VARCHAR)")
    conn.execute("CREATE VIEW order_totals AS SELECT sum(amount) AS total FROM orders")
    adapter: Any = DuckDBAdapter({"source_type": "database"})
    adapter._conn, adapter._connected = conn, True
    yield adapter
    conn.close()


def _tables(schema: SchemaResponse) -> dict[str, list[str]]:
    """Map each discovered table to its column names."""
    return {
        table.name: [column.name for column in table.columns]
        for catalog in schema.catalogs
        for db_schema in catalog.schemas
        for table in db_schema.tables
    }


@pytest.mark.parametrize("pattern", HOSTILE_PATTERNS)
async def test_duckdb_hostile_pattern_matches_no_tables(shop_duckdb: Any, pattern: str) -> None:
    """A hostile table_pattern is matched literally, so it finds nothing."""
    schema = await shop_duckdb.get_schema(SchemaFilter(table_pattern=pattern))

    assert _tables(schema) == {}


async def test_duckdb_table_pattern_keeps_like_wildcards(shop_duckdb: Any) -> None:
    """Bound patterns still use LIKE semantics."""
    schema = await shop_duckdb.get_schema(SchemaFilter(table_pattern="order%"))

    assert sorted(_tables(schema)) == ["order_totals", "orders"]


async def test_duckdb_include_views_false_lists_tables_with_columns(shop_duckdb: Any) -> None:
    """include_views=False drops the view and keeps each table's columns."""
    schema = await shop_duckdb.get_schema(SchemaFilter(include_views=False))

    assert _tables(schema) == {"orders": ["id", "amount"], "secrets": ["token"]}
