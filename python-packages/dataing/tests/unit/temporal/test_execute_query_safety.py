"""Tests that execute_query validates SQL in the dialect of the data source that runs it.

LLM-generated SQL reaches the activity as a plain string. The activity is the last
step before the query runs, so it validates there, using the SQL dialect declared by
the adapter that will execute the query. There is no default dialect.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.document.mongodb import MongoDBAdapter
from dataing.adapters.datasource.filesystem.s3 import S3Adapter
from dataing.adapters.datasource.sql.bigquery import BigQueryAdapter
from dataing.adapters.datasource.sql.mysql import MySQLAdapter
from dataing.adapters.datasource.sql.postgres import PostgresAdapter
from dataing.adapters.datasource.types import AdapterCapabilities, QueryLanguage, QueryResult
from dataing.temporal.activities.execute_query import (
    AdapterGetter,
    ExecuteQueryInput,
    ExecuteQueryResult,
    make_execute_query_activity,
)

# One SELECT to a Postgres parser, which nests block comments. MySQL ends the
# comment at the first */ and runs the RENAME as a second statement.
NESTED_COMMENT_SMUGGLE = "SELECT 1 LIMIT 1 /* /* */ ; RENAME TABLE a TO b; /* */ */"


class _UndeclaredDialectAdapter(PostgresAdapter):
    """A SQL adapter that runs SQL but does not declare which dialect."""

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Capabilities without a sql_dialect."""
        return AdapterCapabilities(supports_sql=True, query_language=QueryLanguage.SQL)


class _UnknownDialectAdapter(PostgresAdapter):
    """A SQL adapter that declares a dialect sqlglot does not know."""

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Capabilities with an unparseable sql_dialect."""
        return AdapterCapabilities(
            supports_sql=True,
            query_language=QueryLanguage.SQL,
            sql_dialect="not-a-dialect",
        )


ONE_ROW = QueryResult(columns=[{"name": "n", "data_type": "integer"}], rows=[{"n": 1}], row_count=1)


def _recording(adapter_cls: type[BaseAdapter], result: QueryResult = ONE_ROW) -> Any:
    """Build an unconnected adapter whose execute_query records SQL instead of running it."""
    adapter = adapter_cls({})
    adapter.execute_query = AsyncMock(return_value=result)  # type: ignore[attr-defined]
    return adapter


def _serving(adapter: Any) -> AdapterGetter:
    """Build a get_adapter function that always resolves to the given adapter."""

    async def get_adapter(*, tenant_id: str, datasource_id: str) -> Any:
        return adapter

    return get_adapter


async def _run(get_adapter: AdapterGetter, sql: str) -> ExecuteQueryResult:
    """Run the execute_query activity outside a Temporal worker."""
    execute_query = make_execute_query_activity(get_adapter=get_adapter)
    result: ExecuteQueryResult = await execute_query(
        ExecuteQueryInput(
            investigation_id="inv-1",
            query=sql,
            hypothesis_id="h1",
            tenant_id="tenant-1",
            datasource_id="ds-1",
        )
    )
    return result


def _assert_refused(result: ExecuteQueryResult, adapter: Any) -> None:
    """Assert the query was rejected as unsafe and never reached the data source."""
    assert result.error is not None
    assert result.error.startswith("Unsafe SQL: ")
    assert result.rows == []
    adapter.execute_query.assert_not_awaited()


class TestValidatesInDataSourceDialect:
    """The dialect comes from the adapter that runs the query, never from a default."""

    async def test_nested_comment_smuggle_rejected_on_mysql(self) -> None:
        """Test that a statement hidden from a Postgres parser never reaches MySQL."""
        adapter = _recording(MySQLAdapter)

        result = await _run(_serving(adapter), NESTED_COMMENT_SMUGGLE)

        _assert_refused(result, adapter)

    @pytest.mark.parametrize(
        ("adapter_cls", "sql"),
        [
            (MySQLAdapter, "SELECT `id` FROM `users` LIMIT 10"),
            (BigQueryAdapter, "SELECT * FROM `my-proj.analytics.orders` LIMIT 10"),
        ],
        ids=["mysql", "bigquery"],
    )
    async def test_dialect_specific_sql_runs_on_its_source(
        self, adapter_cls: type[BaseAdapter], sql: str
    ) -> None:
        """Test that SQL a Postgres parser rejects runs on the engine that speaks it."""
        adapter = _recording(adapter_cls)

        result = await _run(_serving(adapter), sql)

        assert result.error is None
        adapter.execute_query.assert_awaited_once_with(sql)


class TestFailsClosed:
    """A query whose dialect cannot be established is refused."""

    async def test_sql_source_without_dialect_refused(self) -> None:
        """Test that an adapter declaring no dialect is refused, not validated as Postgres."""
        adapter = _recording(_UndeclaredDialectAdapter)

        result = await _run(_serving(adapter), "SELECT id FROM users LIMIT 10")

        _assert_refused(result, adapter)
        assert result.error is not None
        assert "dialect" in result.error

    async def test_unknown_dialect_refused(self) -> None:
        """Test that a dialect sqlglot does not know is refused."""
        adapter = _recording(_UnknownDialectAdapter)

        result = await _run(_serving(adapter), "SELECT id FROM users LIMIT 10")

        _assert_refused(result, adapter)

    async def test_non_sql_source_refused(self) -> None:
        """Test that a source with no SQL dialect (MongoDB) is refused."""
        adapter = MongoDBAdapter({})

        result = await _run(_serving(adapter), "SELECT id FROM users LIMIT 10")

        assert result.error is not None
        assert result.error.startswith("Unsafe SQL: ")
        assert "dialect" in result.error

    async def test_unavailable_data_source_is_an_error(self) -> None:
        """Test that a data source that cannot be resolved yields an error result."""

        async def get_adapter(*, tenant_id: str, datasource_id: str) -> Any:
            raise ValueError(f"Datasource {datasource_id} not found or inactive")

        result = await _run(get_adapter, "SELECT id FROM users LIMIT 10")

        assert result.error == "Query execution failed: Datasource ds-1 not found or inactive"
        assert result.rows == []


class TestReadOnlyPolicy:
    """Only a single read-only SELECT with a LIMIT runs."""

    @pytest.mark.parametrize(
        ("adapter_cls", "sql"),
        [
            (PostgresAdapter, "DELETE FROM users WHERE id = 1"),
            (PostgresAdapter, "SELECT * FROM users LIMIT 10; DROP TABLE users"),
            (PostgresAdapter, "SELECT * INTO pwned FROM users LIMIT 10"),
            (PostgresAdapter, "SELECT * FROM users"),
            # COPY and CALL passed when SELECT was optional: COPY wraps a SELECT with
            # a LIMIT, and neither keyword is on the forbidden list.
            (PostgresAdapter, "COPY (SELECT * FROM users LIMIT 10) TO '/tmp/out.csv'"),
            (S3Adapter, "COPY (SELECT * FROM users LIMIT 10) TO 's3://bucket/out.parquet'"),
            (MySQLAdapter, "CALL refresh_all((SELECT 1 LIMIT 1))"),
        ],
        ids=[
            "delete",
            "multi-statement",
            "select-into",
            "no-limit",
            "copy-to-file",
            "copy-to-bucket",
            "call",
        ],
    )
    async def test_rejected_before_execution(
        self, adapter_cls: type[BaseAdapter], sql: str
    ) -> None:
        """Test that unsafe SQL never reaches the data source."""
        adapter = _recording(adapter_cls)

        result = await _run(_serving(adapter), sql)

        _assert_refused(result, adapter)

    @pytest.mark.parametrize(
        "sql",
        [
            "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent LIMIT 10",
            "SELECT id FROM a UNION ALL SELECT id FROM b LIMIT 10",
            "SELECT id FROM a INTERSECT SELECT id FROM b LIMIT 10",
            "SELECT id FROM a EXCEPT SELECT id FROM b LIMIT 10",
        ],
        ids=["cte", "union-all", "intersect", "except"],
    )
    async def test_read_only_queries_run(self, sql: str) -> None:
        """Test that CTEs and set operations over SELECTs are accepted."""
        adapter = _recording(PostgresAdapter)

        result = await _run(_serving(adapter), sql)

        assert result.error is None
        adapter.execute_query.assert_awaited_once_with(sql)
