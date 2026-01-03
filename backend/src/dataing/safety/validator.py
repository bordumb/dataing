"""SQL Query Validator - Uses sqlglot for robust SQL parsing.

This module ensures that only safe, read-only queries are executed.
It uses sqlglot for proper SQL parsing rather than regex-based
detection which can be bypassed.

SAFETY IS NON-NEGOTIABLE:
- Only SELECT statements are allowed
- No mutation statements (DROP, DELETE, UPDATE, INSERT, etc.)
- All queries must have a LIMIT clause
- Forbidden keywords are checked even in subqueries
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from dataing.core.exceptions import QueryValidationError

# Forbidden statement types - these are never allowed
FORBIDDEN_STATEMENTS: set[type[exp.Expression]] = {
    exp.Delete,
    exp.Drop,
    exp.TruncateTable,
    exp.Update,
    exp.Insert,
    exp.Create,
    exp.Alter,
    exp.Grant,
    exp.Revoke,
}

# Forbidden keywords even in comments or subqueries
# These are checked as a secondary safety layer
FORBIDDEN_KEYWORDS: set[str] = {
    "DROP",
    "DELETE",
    "TRUNCATE",
    "UPDATE",
    "INSERT",
    "CREATE",
    "ALTER",
    "GRANT",
    "REVOKE",
    "EXECUTE",
    "EXEC",
}


def validate_query(sql: str, dialect: str = "postgres") -> None:
    """Validate that a SQL query is safe to execute.

    This function performs multiple layers of validation:
    1. Parse with sqlglot to get AST
    2. Check that it's a SELECT statement
    3. Check for forbidden statement types in the AST
    4. Check for forbidden keywords as whole words
    5. Ensure LIMIT clause is present

    Args:
        sql: The SQL query to validate.
        dialect: SQL dialect for parsing (default: postgres).

    Raises:
        QueryValidationError: If query is not safe.

    Examples:
        >>> validate_query("SELECT * FROM users LIMIT 10")  # OK
        >>> validate_query("DROP TABLE users")  # Raises QueryValidationError
        >>> validate_query("SELECT * FROM users")  # Raises (no LIMIT)
    """
    if not sql or not sql.strip():
        raise QueryValidationError("Empty query")

    # 1. Parse with sqlglot
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as e:
        raise QueryValidationError(f"Failed to parse SQL: {e}") from e

    # 2. Check statement type - must be SELECT
    if not isinstance(parsed, exp.Select):
        raise QueryValidationError(
            f"Only SELECT statements allowed, got: {type(parsed).__name__}"
        )

    # 3. Walk the AST and check for forbidden statement types
    for node in parsed.walk():
        for forbidden in FORBIDDEN_STATEMENTS:
            if isinstance(node, forbidden):
                raise QueryValidationError(f"Forbidden statement type: {type(node).__name__}")

    # 4. Check for forbidden keywords as whole words
    # This catches edge cases that might slip through AST parsing
    sql_upper = sql.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        # Use word boundary regex to avoid false positives
        # e.g., "UPDATED_AT" should not trigger "UPDATE"
        if re.search(rf"\b{keyword}\b", sql_upper):
            raise QueryValidationError(f"Forbidden keyword: {keyword}")

    # 5. Must have LIMIT (safety against large result sets)
    if not parsed.find(exp.Limit):
        raise QueryValidationError("Query must include LIMIT clause")


def add_limit_if_missing(sql: str, limit: int = 10000, dialect: str = "postgres") -> str:
    """Add LIMIT clause if not present.

    This is a convenience function for automatically adding LIMIT
    to queries that don't have one. Used as a fallback safety measure.

    Args:
        sql: The SQL query.
        limit: Maximum rows to return (default: 10000).
        dialect: SQL dialect for parsing.

    Returns:
        SQL query with LIMIT clause added if it was missing.

    Examples:
        >>> add_limit_if_missing("SELECT * FROM users")
        'SELECT * FROM users LIMIT 10000'
        >>> add_limit_if_missing("SELECT * FROM users LIMIT 5")
        'SELECT * FROM users LIMIT 5'
    """
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
        if not parsed.find(exp.Limit):
            parsed = parsed.limit(limit)
        return parsed.sql(dialect=dialect)
    except Exception:
        # If parsing fails, append LIMIT manually
        # This is a fallback and may not always produce valid SQL
        clean_sql = sql.rstrip().rstrip(";")
        return f"{clean_sql} LIMIT {limit}"


def sanitize_identifier(identifier: str) -> str:
    """Sanitize a SQL identifier (table/column name).

    Removes or escapes characters that could be used for injection.

    Args:
        identifier: The identifier to sanitize.

    Returns:
        Sanitized identifier safe for use in queries.

    Raises:
        QueryValidationError: If identifier is invalid.
    """
    if not identifier:
        raise QueryValidationError("Empty identifier")

    # Only allow alphanumeric, underscores, and dots (for schema.table)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$", identifier):
        raise QueryValidationError(f"Invalid identifier: {identifier}")

    return identifier
