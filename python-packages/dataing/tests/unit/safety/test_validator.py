"""Unit tests for SQL query validator."""

from __future__ import annotations

import pytest

from dataing.core.exceptions import QueryValidationError
from dataing.safety.validator import (
    add_limit_if_missing,
    sanitize_identifier,
    validate_query,
)


class TestValidateQuery:
    """Tests for validate_query."""

    def test_valid_select_with_limit(self) -> None:
        """Test that valid SELECT with LIMIT passes."""
        validate_query("SELECT * FROM users LIMIT 10", dialect="postgres")  # Should not raise

    def test_valid_select_with_columns(self) -> None:
        """Test valid SELECT with specific columns."""
        validate_query("SELECT id, name, email FROM users LIMIT 100", dialect="postgres")

    def test_valid_select_with_where(self) -> None:
        """Test valid SELECT with WHERE clause."""
        validate_query("SELECT * FROM users WHERE id = 1 LIMIT 10", dialect="postgres")

    def test_valid_select_with_join(self) -> None:
        """Test valid SELECT with JOIN."""
        validate_query(
            "SELECT u.id, o.total FROM users u JOIN orders o ON u.id = o.user_id LIMIT 10",
            dialect="postgres",
        )

    def test_valid_select_with_subquery(self) -> None:
        """Test valid SELECT with subquery."""
        validate_query(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders) LIMIT 10",
            dialect="postgres",
        )

    def test_valid_select_with_cte(self) -> None:
        """Test valid SELECT with CTE."""
        validate_query(
            """
            WITH active_users AS (SELECT id FROM users WHERE active = true)
            SELECT * FROM active_users LIMIT 10
            """,
            dialect="postgres",
        )

    def test_empty_query_raises(self) -> None:
        """Test that empty query raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("", dialect="postgres")

        assert "Empty query" in str(exc_info.value)

    def test_whitespace_only_raises(self) -> None:
        """Test that whitespace-only query raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("   \n\t  ", dialect="postgres")

        assert "Empty query" in str(exc_info.value)

    def test_missing_limit_raises(self) -> None:
        """Test that missing LIMIT raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("SELECT * FROM users", dialect="postgres")

        assert "LIMIT" in str(exc_info.value)

    def test_drop_table_raises(self) -> None:
        """Test that DROP TABLE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("DROP TABLE users", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_delete_raises(self) -> None:
        """Test that DELETE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("DELETE FROM users WHERE id = 1", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_truncate_raises(self) -> None:
        """Test that TRUNCATE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("TRUNCATE TABLE users", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_update_raises(self) -> None:
        """Test that UPDATE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("UPDATE users SET name = 'test' WHERE id = 1", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_insert_raises(self) -> None:
        """Test that INSERT raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("INSERT INTO users (name) VALUES ('test')", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_create_raises(self) -> None:
        """Test that CREATE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("CREATE TABLE test (id INT)", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_alter_raises(self) -> None:
        """Test that ALTER raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("ALTER TABLE users ADD COLUMN email VARCHAR", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_grant_raises(self) -> None:
        """Test that GRANT raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("GRANT SELECT ON users TO public", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_revoke_raises(self) -> None:
        """Test that REVOKE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("REVOKE SELECT ON users FROM public", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_exec_in_query_raises(self) -> None:
        """Test that EXEC keyword raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("EXEC sp_executesql @sql", dialect="postgres")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_column_named_update_ok(self) -> None:
        """Test that column named 'updated_at' is allowed."""
        # Should not raise
        validate_query("SELECT updated_at FROM users LIMIT 10", dialect="postgres")

    def test_invalid_sql_raises(self) -> None:
        """Test that invalid SQL raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("SELECTT * FORM users LIMIT 10", dialect="postgres")

        assert "parse" in str(exc_info.value).lower()

    def test_multi_statement_raises(self) -> None:
        """Test that multi-statement queries are rejected."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("SELECT * FROM users LIMIT 10; DROP TABLE users", dialect="postgres")

        assert "Multi-statement" in str(exc_info.value)

    def test_multi_statement_injection_raises(self) -> None:
        """Test that hidden multi-statement injection is rejected."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("SELECT 1 LIMIT 1; DELETE FROM users WHERE 1=1", dialect="postgres")

        assert "Multi-statement" in str(exc_info.value)

    def test_single_statement_with_trailing_semicolon_ok(self) -> None:
        """Test that single statement with trailing semicolon passes."""
        validate_query("SELECT * FROM users LIMIT 10;", dialect="postgres")  # Should not raise

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * INTO pwned FROM users LIMIT 10",
            "SELECT * FROM (SELECT * INTO pwned FROM users) AS s LIMIT 10",
        ],
    )
    def test_select_into_raises(self, sql: str) -> None:
        """Test that SELECT ... INTO is rejected: it creates a table."""
        with pytest.raises(QueryValidationError):
            validate_query(sql, dialect="postgres")

    @pytest.mark.parametrize("operator", ["UNION", "UNION ALL", "INTERSECT", "EXCEPT"])
    def test_set_operations_allowed(self, operator: str) -> None:
        """Test that set operations over SELECTs count as read-only queries."""
        validate_query(f"SELECT id FROM a {operator} SELECT id FROM b LIMIT 10", dialect="postgres")

    def test_dialect_is_required(self) -> None:
        """Test that callers must name a dialect rather than silently get postgres."""
        with pytest.raises(TypeError):
            validate_query("SELECT 1 LIMIT 1")  # type: ignore[call-arg]

    def test_unknown_dialect_raises(self) -> None:
        """Test that an unknown dialect fails closed."""
        with pytest.raises(QueryValidationError):
            validate_query("SELECT 1 LIMIT 1", dialect="not-a-dialect")


class TestValidateQueryDialect:
    """Tests that validate_query parses in the caller's dialect."""

    def test_mysql_identifiers_accepted_in_mysql(self) -> None:
        """Test that MySQL backtick identifiers pass in the MySQL dialect."""
        validate_query("SELECT `id` FROM `users` LIMIT 10", dialect="mysql")

    def test_mysql_identifiers_rejected_in_postgres(self) -> None:
        """Test that the same query does not parse as postgres."""
        with pytest.raises(QueryValidationError):
            validate_query("SELECT `id` FROM `users` LIMIT 10", dialect="postgres")

    def test_nested_comment_smuggling_rejected_in_mysql(self) -> None:
        """Test that a second statement hidden in a nested comment is caught.

        Postgres nests block comments, so a postgres parser sees one SELECT.
        MySQL ends the comment at the first */ and runs the RENAME.
        """
        sql = "SELECT 1 LIMIT 1 /* /* */ ; RENAME TABLE a TO b; /* */ */"
        validate_query(sql, dialect="postgres")

        with pytest.raises(QueryValidationError):
            validate_query(sql, dialect="mysql")


class TestValidateQueryWithoutLimit:
    """Tests for validate_query(require_limit=False), used for ad-hoc queries."""

    def test_missing_limit_allowed(self) -> None:
        """Test that a SELECT without LIMIT passes when LIMIT is not required."""
        validate_query("SELECT * FROM users", dialect="postgres", require_limit=False)

    @pytest.mark.parametrize(
        "sql",
        [
            "DELETE FROM users",
            "SELECT * INTO pwned FROM users",
            "SELECT 1; DROP TABLE users",
        ],
    )
    def test_other_checks_still_apply(self, sql: str) -> None:
        """Test that dropping the LIMIT requirement keeps every other check."""
        with pytest.raises(QueryValidationError):
            validate_query(sql, dialect="postgres", require_limit=False)


class TestAddLimitIfMissing:
    """Tests for add_limit_if_missing."""

    def test_adds_limit_when_missing(self) -> None:
        """Test adding LIMIT when missing."""
        result = add_limit_if_missing("SELECT * FROM users")

        assert "LIMIT" in result.upper()
        assert "10000" in result

    def test_preserves_existing_limit(self) -> None:
        """Test that existing LIMIT is preserved."""
        result = add_limit_if_missing("SELECT * FROM users LIMIT 5")

        assert "LIMIT 5" in result
        # Should not have LIMIT 10000
        assert "10000" not in result

    def test_custom_limit_value(self) -> None:
        """Test custom limit value."""
        result = add_limit_if_missing("SELECT * FROM users", limit=500)

        assert "500" in result

    def test_handles_trailing_semicolon(self) -> None:
        """Test handling trailing semicolon."""
        result = add_limit_if_missing("SELECT * FROM users;")

        assert "LIMIT" in result.upper()


class TestSanitizeIdentifier:
    """Tests for sanitize_identifier."""

    def test_valid_simple_identifier(self) -> None:
        """Test valid simple identifier."""
        result = sanitize_identifier("users")

        assert result == "users"

    def test_valid_schema_qualified(self) -> None:
        """Test valid schema-qualified identifier."""
        result = sanitize_identifier("public.users")

        assert result == "public.users"

    def test_valid_with_underscore(self) -> None:
        """Test valid identifier with underscore."""
        result = sanitize_identifier("user_accounts")

        assert result == "user_accounts"

    def test_valid_with_numbers(self) -> None:
        """Test valid identifier with numbers."""
        result = sanitize_identifier("users2024")

        assert result == "users2024"

    def test_empty_raises(self) -> None:
        """Test that empty identifier raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            sanitize_identifier("")

        assert "Empty identifier" in str(exc_info.value)

    def test_starts_with_number_raises(self) -> None:
        """Test that identifier starting with number raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            sanitize_identifier("123users")

        assert "Invalid identifier" in str(exc_info.value)

    def test_special_chars_raise(self) -> None:
        """Test that special characters raise error."""
        with pytest.raises(QueryValidationError) as exc_info:
            sanitize_identifier("users; DROP TABLE")

        assert "Invalid identifier" in str(exc_info.value)

    def test_single_quotes_raise(self) -> None:
        """Test that single quotes raise error."""
        with pytest.raises(QueryValidationError) as exc_info:
            sanitize_identifier("users'")

        assert "Invalid identifier" in str(exc_info.value)

    def test_double_quotes_raise(self) -> None:
        """Test that double quotes raise error."""
        with pytest.raises(QueryValidationError) as exc_info:
            sanitize_identifier('users"')

        assert "Invalid identifier" in str(exc_info.value)

    def test_hyphen_raises(self) -> None:
        """Test that hyphen raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            sanitize_identifier("user-accounts")

        assert "Invalid identifier" in str(exc_info.value)


COPY_QUERY_TO_FILE = "COPY (SELECT * FROM orders LIMIT 10) TO '/data/src/orders.csv'"


class TestCopyStatements:
    """Tests that COPY is rejected: it writes files, runs programs and loads tables."""

    @pytest.mark.parametrize("dialect", ["duckdb", "postgres"])
    def test_copy_to_file_forbidden_without_require_select(self, dialect: str) -> None:
        """Test COPY ... TO a file is rejected even though its inner SELECT has a LIMIT."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query(COPY_QUERY_TO_FILE, dialect=dialect, require_select=False)

        assert "Forbidden statement type: Copy" in str(exc_info.value)

    @pytest.mark.parametrize("dialect", ["duckdb", "postgres"])
    def test_copy_to_file_rejected_with_require_select(self, dialect: str) -> None:
        """Test COPY ... TO a file fails the SELECT-only check."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query(COPY_QUERY_TO_FILE, dialect=dialect, require_select=True)

        assert "Only SELECT statements allowed, got: Copy" in str(exc_info.value)

    def test_copy_to_program_forbidden(self) -> None:
        """Test Postgres COPY ... TO PROGRAM, which runs a shell command, is rejected."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query(
                "COPY (SELECT * FROM orders LIMIT 10) TO PROGRAM 'rm -rf /data/src'",
                dialect="postgres",
                require_select=False,
            )

        assert "Forbidden statement type: Copy" in str(exc_info.value)

    @pytest.mark.parametrize("dialect", ["duckdb", "postgres"])
    @pytest.mark.parametrize(
        "sql",
        [
            "COPY orders TO '/data/src/orders.csv'",
            "COPY orders FROM '/data/src/orders.csv'",
        ],
        ids=["to_file", "from_file"],
    )
    def test_copy_table_forbidden(self, sql: str, dialect: str) -> None:
        """Test COPY of a whole table is forbidden, not just rejected for lacking a LIMIT."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query(sql, dialect=dialect, require_select=False)

        assert "Forbidden statement type: Copy" in str(exc_info.value)


class TestWriteCapableStatements:
    """Tests that statements which write data or files, or change session state, are rejected.

    The assertions check for the forbidden-statement error, not just any
    rejection: the LIMIT rule guards result size, not writes, and an embedded
    SELECT can satisfy it.
    """

    @pytest.mark.parametrize(
        ("sql", "dialect", "statement_type"),
        [
            pytest.param(
                "COPY INTO @unload_stage FROM (SELECT * FROM orders LIMIT 10)",
                "snowflake",
                "Copy",
                id="snowflake_copy_into_stage",
            ),
            pytest.param(
                "EXPORT DATA OPTIONS (uri = 'gs://bucket/orders-*.csv', format = 'CSV') "
                "AS SELECT * FROM orders LIMIT 10",
                "bigquery",
                "Export",
                id="bigquery_export_data",
            ),
            pytest.param(
                "CACHE TABLE orders_cache AS SELECT * FROM orders LIMIT 10",
                "postgres",
                "Cache",
                id="cache_table_as_select",
            ),
            pytest.param(
                "SET VARIABLE last_id = (SELECT id FROM orders LIMIT 1)",
                "duckdb",
                "Set",
                id="duckdb_set_variable",
            ),
            pytest.param(
                "SET @last_id = (SELECT id FROM orders LIMIT 1)",
                "mysql",
                "Set",
                id="mysql_set_user_variable",
            ),
            pytest.param("ATTACH '/data/src/new.db' AS new_db", "duckdb", "Attach", id="attach"),
            pytest.param("DETACH new_db", "duckdb", "Detach", id="detach"),
            pytest.param("INSTALL httpfs", "duckdb", "Install", id="install"),
            pytest.param("LOAD httpfs", "duckdb", "Command", id="load_extension"),
            pytest.param("PRAGMA user_version = 5", "sqlite", "Pragma", id="pragma"),
            pytest.param("USE ROLE accountadmin", "snowflake", "Use", id="use_role"),
            pytest.param("PUT 'file:///tmp/orders.csv' @my_stage", "snowflake", "Put", id="put"),
            pytest.param("GET @my_stage 'file:///tmp/'", "snowflake", "Get", id="get"),
            pytest.param(
                "LOAD DATA INPATH '/data/src/orders.csv' INTO TABLE orders",
                "postgres",
                "LoadData",
                id="load_data",
            ),
            pytest.param(
                "COMMENT ON TABLE orders IS 'overwritten'", "postgres", "Comment", id="comment_on"
            ),
            pytest.param("KILL 123", "mysql", "Kill", id="kill"),
            pytest.param(
                "VACUUM INTO '/data/src/copy.db'", "sqlite", "Command", id="sqlite_vacuum_into"
            ),
            pytest.param(
                "DO $$ BEGIN PERFORM 1; END $$", "postgres", "Command", id="postgres_do_block"
            ),
        ],
    )
    def test_statement_forbidden(self, sql: str, dialect: str, statement_type: str) -> None:
        """Test the statement is rejected as forbidden when SELECT is not required."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query(sql, dialect=dialect, require_select=False)

        assert f"Forbidden statement type: {statement_type}" in str(exc_info.value)

    @pytest.mark.parametrize(
        "sql",
        ["EXPORT DATABASE '/data/src/'", "IMPORT DATABASE '/data/src/'"],
        ids=["export_database", "import_database"],
    )
    def test_duckdb_database_export_import_rejected(self, sql: str) -> None:
        """Test DuckDB EXPORT/IMPORT DATABASE are rejected (sqlglot cannot parse them)."""
        with pytest.raises(QueryValidationError):
            validate_query(sql, dialect="duckdb", require_select=False)

    @pytest.mark.parametrize(
        ("sql", "dialect"),
        [
            pytest.param(
                "SELECT id FROM orders UNION ALL SELECT id FROM refunds LIMIT 10",
                "postgres",
                id="union_is_not_set",
            ),
            pytest.param(
                "SELECT * FROM orders USE INDEX (idx_created_at) LIMIT 10",
                "mysql",
                id="index_hint_is_not_use",
            ),
            pytest.param(
                "SELECT GET(line_items, 0) FROM orders LIMIT 10",
                "snowflake",
                id="get_function_is_not_get",
            ),
            pytest.param(
                "SELECT * FROM events WHERE action = 'copy' LIMIT 10",
                "duckdb",
                id="copy_in_string_literal",
            ),
            pytest.param("SUMMARIZE SELECT * FROM orders LIMIT 10", "duckdb", id="summarize"),
        ],
    )
    def test_read_only_statement_allowed(self, sql: str, dialect: str) -> None:
        """Test read-only statements that resemble forbidden ones still pass."""
        validate_query(sql, dialect=dialect, require_select=False)  # Should not raise
