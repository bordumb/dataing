"""Tests for the security module."""

from __future__ import annotations

from typing import Any

import pytest

from investigator.security import SecurityViolation, create_scope, validate_tool_call


class TestValidateToolCall:
    """Test validate_tool_call functionality."""

    def test_all_tools_allowed_by_default(self) -> None:
        """Test all tools are allowed when no allowlist specified."""
        scope = create_scope("user1", "tenant1", ["orders"])
        # All tools should pass when no allowed_tools in scope
        validate_tool_call("get_schema", {}, scope)
        validate_tool_call("generate_hypotheses", {}, scope)
        validate_tool_call("any_custom_tool", {}, scope)

    def test_allowlist_restricts_tools(self) -> None:
        """Test tools are restricted when allowlist is specified."""
        scope = create_scope(
            "user1", "tenant1", ["orders"], allowed_tools=["get_schema"]
        )
        # Allowed tool should pass
        validate_tool_call("get_schema", {}, scope)

        # Non-allowed tool should fail
        with pytest.raises(SecurityViolation) as exc_info:
            validate_tool_call("other_tool", {}, scope)
        assert "not in allowlist" in str(exc_info.value)

    def test_forbidden_table_raises(self) -> None:
        """Test forbidden tables are rejected."""
        scope = create_scope("user1", "tenant1", ["allowed_table"])
        with pytest.raises(SecurityViolation) as exc_info:
            validate_tool_call("query", {"table_name": "forbidden_table"}, scope)
        assert "forbidden_table" in str(exc_info.value)

    def test_allowed_table_passes(self) -> None:
        """Test allowed tables pass validation."""
        scope = create_scope("user1", "tenant1", ["orders", "customers"])
        # Should not raise
        validate_tool_call("query", {"table_name": "orders"}, scope)
        validate_tool_call("query", {"table_name": "customers"}, scope)

    def test_empty_permissions_denies_all_tables(self) -> None:
        """Test empty permissions denies all table access."""
        scope = create_scope("user1", "tenant1", [])
        with pytest.raises(SecurityViolation) as exc_info:
            validate_tool_call("query", {"table_name": "any_table"}, scope)
        assert "No table permissions" in str(exc_info.value)

    def test_no_table_in_args_passes(self) -> None:
        """Test calls without table_name pass table validation."""
        scope = create_scope("user1", "tenant1", [])
        # Should pass - no table_name in args
        validate_tool_call("get_schema", {}, scope)


class TestForbiddenSqlPatterns:
    """Test SQL pattern validation."""

    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE users",
            "drop table users",
            "DROP   TABLE   users",
            "TRUNCATE TABLE orders",
            "truncate table orders",
            "DELETE FROM users",
            "delete from customers",
            "ALTER TABLE users ADD COLUMN",
            "alter table users drop column",
            "CREATE TABLE new_table",
            "create table test",
            "INSERT INTO users VALUES",
            "insert into orders values",
            "UPDATE users SET name = 'x'",
            "update orders set status = 'done'",
            "GRANT SELECT ON users",
            "grant all on orders",
            "REVOKE SELECT ON users",
            "revoke all on orders",
        ],
    )
    def test_forbidden_sql_patterns_raise(self, sql: str) -> None:
        """Test forbidden SQL patterns are rejected."""
        scope = create_scope("user1", "tenant1", ["orders"])
        with pytest.raises(SecurityViolation) as exc_info:
            validate_tool_call("execute", {"query": sql}, scope)
        assert "Forbidden SQL pattern" in str(exc_info.value)

    def test_select_query_allowed(self) -> None:
        """Test SELECT queries are allowed."""
        scope = create_scope("user1", "tenant1", ["users", "orders"])
        # Should not raise
        validate_tool_call("execute", {"query": "SELECT * FROM users"}, scope)
        validate_tool_call("execute", {"query": "select count(*) from orders"}, scope)

    def test_pattern_word_boundary(self) -> None:
        """Test patterns match on word boundaries only."""
        scope = create_scope("user1", "tenant1", ["orders"])
        # DROPBOX should not match DROP
        validate_tool_call("execute", {"query": "SELECT * FROM dropbox_files"}, scope)


class TestCreateScope:
    """Test create_scope helper."""

    def test_create_scope_basic(self) -> None:
        """Test creating a basic scope."""
        scope = create_scope("user1", "tenant1", ["table1", "table2"])
        assert scope["user_id"] == "user1"
        assert scope["tenant_id"] == "tenant1"
        assert scope["permissions"] == ["table1", "table2"]

    def test_create_scope_with_allowed_tools(self) -> None:
        """Test creating a scope with allowed tools."""
        scope = create_scope(
            "user1", "tenant1", ["orders"], allowed_tools=["get_schema", "query"]
        )
        assert scope["allowed_tools"] == ["get_schema", "query"]

    def test_create_scope_empty_permissions(self) -> None:
        """Test scope with empty permissions."""
        scope = create_scope("user1", "tenant1", [])
        assert scope["permissions"] == []

    def test_create_scope_none_permissions(self) -> None:
        """Test scope with None permissions defaults to empty list."""
        scope = create_scope("user1", "tenant1", None)
        assert scope["permissions"] == []


class TestSecurityViolation:
    """Test SecurityViolation exception."""

    def test_security_violation_message(self) -> None:
        """Test SecurityViolation preserves message."""
        try:
            raise SecurityViolation("Test violation")
        except SecurityViolation as e:
            assert str(e) == "Test violation"

    def test_security_violation_is_exception(self) -> None:
        """Test SecurityViolation is an Exception."""
        assert issubclass(SecurityViolation, Exception)
