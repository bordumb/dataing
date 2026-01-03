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
        validate_query("SELECT * FROM users LIMIT 10")  # Should not raise

    def test_valid_select_with_columns(self) -> None:
        """Test valid SELECT with specific columns."""
        validate_query("SELECT id, name, email FROM users LIMIT 100")

    def test_valid_select_with_where(self) -> None:
        """Test valid SELECT with WHERE clause."""
        validate_query("SELECT * FROM users WHERE id = 1 LIMIT 10")

    def test_valid_select_with_join(self) -> None:
        """Test valid SELECT with JOIN."""
        validate_query(
            "SELECT u.id, o.total FROM users u JOIN orders o ON u.id = o.user_id LIMIT 10"
        )

    def test_valid_select_with_subquery(self) -> None:
        """Test valid SELECT with subquery."""
        validate_query(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders) LIMIT 10"
        )

    def test_valid_select_with_cte(self) -> None:
        """Test valid SELECT with CTE."""
        validate_query(
            """
            WITH active_users AS (SELECT id FROM users WHERE active = true)
            SELECT * FROM active_users LIMIT 10
            """
        )

    def test_empty_query_raises(self) -> None:
        """Test that empty query raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("")

        assert "Empty query" in str(exc_info.value)

    def test_whitespace_only_raises(self) -> None:
        """Test that whitespace-only query raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("   \n\t  ")

        assert "Empty query" in str(exc_info.value)

    def test_missing_limit_raises(self) -> None:
        """Test that missing LIMIT raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("SELECT * FROM users")

        assert "LIMIT" in str(exc_info.value)

    def test_drop_table_raises(self) -> None:
        """Test that DROP TABLE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("DROP TABLE users")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_delete_raises(self) -> None:
        """Test that DELETE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("DELETE FROM users WHERE id = 1")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_truncate_raises(self) -> None:
        """Test that TRUNCATE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("TRUNCATE TABLE users")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_update_raises(self) -> None:
        """Test that UPDATE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("UPDATE users SET name = 'test' WHERE id = 1")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_insert_raises(self) -> None:
        """Test that INSERT raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("INSERT INTO users (name) VALUES ('test')")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_create_raises(self) -> None:
        """Test that CREATE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("CREATE TABLE test (id INT)")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_alter_raises(self) -> None:
        """Test that ALTER raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("ALTER TABLE users ADD COLUMN email VARCHAR")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_grant_raises(self) -> None:
        """Test that GRANT raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("GRANT SELECT ON users TO public")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_revoke_raises(self) -> None:
        """Test that REVOKE raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("REVOKE SELECT ON users FROM public")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_exec_in_query_raises(self) -> None:
        """Test that EXEC keyword raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("EXEC sp_executesql @sql")

        assert "Only SELECT statements allowed" in str(exc_info.value)

    def test_column_named_update_ok(self) -> None:
        """Test that column named 'updated_at' is allowed."""
        validate_query("SELECT updated_at FROM users LIMIT 10")  # Should not raise

    def test_invalid_sql_raises(self) -> None:
        """Test that invalid SQL raises error."""
        with pytest.raises(QueryValidationError) as exc_info:
            validate_query("SELECTT * FORM users LIMIT 10")

        assert "parse" in str(exc_info.value).lower()


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
