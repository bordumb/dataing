"""Unit tests for the validator's forbidden-function check.

DuckDB-backed adapters confine their connection to the source's own location; this
check is defense in depth on top of that.
"""

from __future__ import annotations

import pytest

from dataing.core.exceptions import QueryValidationError
from dataing.safety.validator import validate_query


class TestForbiddenFunctions:
    """Functions that reach outside the queried tables are rejected."""

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM read_text('/etc/passwd') LIMIT 10",
            "SELECT * FROM read_blob('/home/app/.ssh/id_rsa') LIMIT 10",
            "SELECT * FROM glob('/etc/*') LIMIT 10",
            "SELECT * FROM query('SELECT * FROM read_text(''/etc/passwd'')') LIMIT 10",
            "SELECT current_setting('s3_secret_access_key') AS k LIMIT 1",
            "SELECT * FROM duckdb_settings() LIMIT 100",
            "SELECT * FROM duckdb_secrets() LIMIT 10",
        ],
    )
    def test_rejected_in_duckdb_dialect(self, sql: str) -> None:
        """File, directory, SQL-string and settings functions are rejected."""
        with pytest.raises(QueryValidationError, match="Forbidden function"):
            validate_query(sql, dialect="duckdb")

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM READ_TEXT('/etc/passwd') LIMIT 10",
            "SELECT * FROM \"read_text\"('/etc/passwd') LIMIT 10",
            "SELECT * FROM main.read_text('/etc/passwd') LIMIT 10",
            "SELECT o.id FROM orders o, LATERAL read_blob(o.path) LIMIT 10",
            "SELECT (SELECT count(*) FROM read_text('/etc/passwd')) AS n LIMIT 1",
        ],
    )
    def test_rejected_however_written(self, sql: str) -> None:
        """Case, quoting, schema qualification and nesting do not hide the call."""
        with pytest.raises(QueryValidationError, match="Forbidden function"):
            validate_query(sql, dialect="duckdb")

    def test_rejected_when_validated_in_another_dialect(self) -> None:
        """The check does not depend on the dialect the caller validates with."""
        with pytest.raises(QueryValidationError, match="Forbidden function"):
            validate_query("SELECT * FROM read_text('/etc/passwd') LIMIT 10", dialect="postgres")

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM read_csv('/data/orders.csv') LIMIT 10",
            "SELECT * FROM read_parquet('s3://acme-data/warehouse/orders.parquet') LIMIT 10",
            "SELECT * FROM '/data/orders.csv' LIMIT 10",
            "SELECT name FROM users WHERE name GLOB 'a*' LIMIT 10",
            "SELECT query, duration_ms FROM query_log LIMIT 10",
        ],
    )
    def test_file_source_queries_still_pass(self, sql: str) -> None:
        """File sources are queried through read_csv/read_parquet and path literals."""
        validate_query(sql, dialect="duckdb")
