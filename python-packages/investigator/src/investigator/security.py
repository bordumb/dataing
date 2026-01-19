"""Security module with deny-by-default tool call validation.

Provides defense-in-depth validation for tool calls before they
reach any database or external service.
"""

from __future__ import annotations

from typing import Any


class SecurityViolation(Exception):
    """Raised when a tool call violates security policy."""

    pass


# Default forbidden SQL patterns (deny-by-default)
FORBIDDEN_SQL_PATTERNS: frozenset[str] = frozenset({
    "DROP",
    "DELETE",
    "TRUNCATE",
    "ALTER",
    "INSERT",
    "UPDATE",
    "CREATE",
    "GRANT",
    "REVOKE",
})


def validate_tool_call(
    tool_name: str,
    args: dict[str, Any],
    scope: dict[str, Any],
) -> None:
    """Validate a tool call against the security policy.

    Defense-in-depth: this runs BEFORE hitting any database.

    Args:
        tool_name: Name of the tool being called.
        args: Arguments to the tool call.
        scope: Security scope with permissions.

    Raises:
        SecurityViolation: If the call violates security policy.
    """
    # 1. Validate tool is in allowlist (if scope restricts tools)
    _validate_tool_allowlist(tool_name, scope)

    # 2. Validate table access (if table_name in args)
    _validate_table_access(args, scope)

    # 3. Validate query safety (if query in args)
    if "query" in args:
        _validate_query_safety(args["query"])


def _validate_tool_allowlist(tool_name: str, scope: dict[str, Any]) -> None:
    """Validate that the tool is in the allowlist.

    If scope has no allowlist, all tools are allowed (permissive default).
    If scope has an allowlist, the tool must be in it.

    Args:
        tool_name: Name of the tool.
        scope: Security scope.

    Raises:
        SecurityViolation: If tool is not in allowlist.
    """
    allowed_tools = scope.get("allowed_tools")
    if allowed_tools is not None and tool_name not in allowed_tools:
        raise SecurityViolation(f"Tool '{tool_name}' not in allowlist")


def _validate_table_access(args: dict[str, Any], scope: dict[str, Any]) -> None:
    """Validate table access permissions.

    Args:
        args: Tool arguments.
        scope: Security scope with permissions list.

    Raises:
        SecurityViolation: If access denied to table.
    """
    if "table_name" not in args:
        return

    table = args["table_name"]
    allowed_tables = scope.get("permissions", [])

    # Deny-by-default: if no permissions specified, deny all
    if not allowed_tables:
        raise SecurityViolation(f"No table permissions granted, access denied to '{table}'")

    if table not in allowed_tables:
        raise SecurityViolation(f"Access denied to table '{table}'")


def _validate_query_safety(query: str) -> None:
    """Check for obviously dangerous SQL patterns.

    This is a defense-in-depth check, not a complete SQL parser.
    The underlying database adapter should also enforce read-only access.

    Args:
        query: SQL query string.

    Raises:
        SecurityViolation: If forbidden pattern detected.
    """
    query_upper = query.upper()
    for pattern in FORBIDDEN_SQL_PATTERNS:
        # Check for pattern as a word (not substring of another word)
        # e.g., "DROP" should match " DROP " but not "DROPBOX"
        if _word_in_query(pattern, query_upper):
            raise SecurityViolation(f"Forbidden SQL pattern: {pattern}")


def _word_in_query(word: str, query_upper: str) -> bool:
    """Check if a word appears in the query as a keyword.

    Simple check that looks for the word surrounded by non-alphanumeric chars.

    Args:
        word: The keyword to check for (uppercase).
        query_upper: The query string (uppercase).

    Returns:
        True if the word appears as a keyword.
    """
    import re
    # Match word boundaries
    pattern = rf"\b{word}\b"
    return bool(re.search(pattern, query_upper))


def create_scope(
    user_id: str,
    tenant_id: str,
    permissions: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> dict[str, Any]:
    """Create a security scope dictionary.

    Helper function for constructing scope objects.

    Args:
        user_id: User identifier.
        tenant_id: Tenant identifier.
        permissions: List of allowed table names.
        allowed_tools: Optional list of allowed tool names.

    Returns:
        Scope dictionary for use with validate_tool_call.
    """
    scope: dict[str, Any] = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "permissions": permissions or [],
    }
    if allowed_tools is not None:
        scope["allowed_tools"] = allowed_tools
    return scope
