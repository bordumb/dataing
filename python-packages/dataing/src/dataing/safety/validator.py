"""SQL Query Validator - Uses sqlglot for robust SQL parsing.

This module ensures that only safe, read-only queries are executed.
It uses sqlglot for proper SQL parsing rather than regex-based
detection which can be bypassed.

SAFETY IS NON-NEGOTIABLE:
- Only SELECT statements are allowed
- No mutation statements (DROP, DELETE, UPDATE, INSERT, SELECT INTO, etc.)
- Queries are parsed in the caller's SQL dialect; there is no default
- Queries must have a LIMIT clause unless the caller opts out
- Forbidden keywords are checked even in subqueries
- No statements that move data to files or programs, or change session
  state (COPY, EXPORT DATA, ATTACH, SET, etc.)
- Functions that read raw files, directory listings or engine settings are rejected
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from dataing.core.exceptions import QueryValidationError

# Forbidden statement types - these are never allowed
FORBIDDEN_STATEMENTS: set[type[exp.Expression]] = {
    # Moving data to or from files, programs, stages and buckets
    exp.Copy,  # COPY ... TO/FROM a file or PROGRAM, Snowflake COPY INTO
    exp.Export,  # BigQuery EXPORT DATA
    exp.LoadData,
    exp.Put,  # Snowflake PUT uploads to a stage
    exp.Get,  # Snowflake GET downloads from a stage
    # Database files, extensions, catalog and session state
    exp.Attach,  # ATTACH creates or opens database files
    exp.Detach,
    exp.Install,  # DuckDB INSTALL downloads extensions
    exp.Cache,  # CACHE TABLE ... AS SELECT materializes a table
    exp.Comment,  # COMMENT ON writes catalog metadata
    exp.Set,
    exp.Pragma,
    exp.Use,  # includes Snowflake USE ROLE
    exp.Kill,
    # sqlglot's fallback for statements it cannot parse (e.g. LOAD, CALL,
    # VACUUM INTO, DO): the validator cannot see what they do
    exp.Command,
    # Data modification, DDL and privileges
    exp.Delete,
    exp.Drop,
    exp.TruncateTable,
    exp.Update,
    exp.Insert,
    exp.Create,
    exp.Alter,
    exp.Grant,
    exp.Revoke,
    exp.Merge,
    exp.Into,  # SELECT ... INTO creates a table
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
    "MERGE",
}

# Functions that reach past the tables a query names: raw file contents and
# directory listings, SQL passed as a string (which would hide calls from this
# check), and engine settings and secrets. DuckDB-backed adapters also confine
# their connection to the source's own location; this check is defense in depth.
# read_csv/read_parquet/read_json stay allowed: file sources are queried with them.
FORBIDDEN_FUNCTIONS: set[str] = {
    "read_text",
    "read_blob",
    "glob",
    "query",
    "current_setting",
    "duckdb_settings",
    "duckdb_secrets",
}


def validate_query(
    sql: str,
    *,
    dialect: str,
    require_limit: bool = True,
) -> None:
    """Validate that a SQL query is safe to execute.

    This function performs multiple layers of validation:
    0. Check for multi-statement queries (rejected)
    1. Parse with sqlglot to get AST
    2. Check that it's a SELECT statement, or UNION/INTERSECT/EXCEPT of SELECTs
    3. Check for forbidden statement types and functions in the AST
    4. Check for forbidden keywords as whole words
    5. Ensure LIMIT clause is present (if require_limit=True)

    Step 2 has no opt-out: without it, validation is a denylist, and statements
    missing from the lists (COPY, CALL, ...) get through.

    Args:
        sql: The SQL query to validate.
        dialect: sqlglot dialect of the database that will run the query
            (e.g. "postgres", "mysql", "snowflake"). Statement boundaries,
            comments and quoting differ between dialects, so validating in
            the wrong one can let a second statement through.
        require_limit: If True (default), query must include a LIMIT clause.

    Raises:
        QueryValidationError: If query is not safe.

    Examples:
        >>> validate_query("SELECT * FROM users LIMIT 10", dialect="postgres")  # OK
        >>> validate_query("DROP TABLE users", dialect="postgres")  # Raises
        >>> validate_query("SELECT * FROM users", dialect="postgres")  # Raises (no LIMIT)
    """
    if not sql or not sql.strip():
        raise QueryValidationError("Empty query")

    # 0. Check for multi-statement queries (security risk)
    try:
        statements = sqlglot.parse(sql, dialect=dialect)
        non_empty = [s for s in statements if s is not None]
        if len(non_empty) > 1:
            raise QueryValidationError("Multi-statement queries not allowed")
    except QueryValidationError:
        raise
    except Exception as e:
        raise QueryValidationError(f"Failed to parse SQL: {e}") from e

    # 1. Parse with sqlglot (now safe - single statement)
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as e:
        raise QueryValidationError(f"Failed to parse SQL: {e}") from e

    # 2. Check statement type - must be SELECT or a set operation over SELECTs
    if not isinstance(parsed, exp.Select | exp.Union | exp.Intersect | exp.Except):
        raise QueryValidationError(f"Only SELECT statements allowed, got: {type(parsed).__name__}")

    # 3. Walk the AST and check for forbidden statement types and functions
    for node in parsed.walk():
        for forbidden in FORBIDDEN_STATEMENTS:
            if isinstance(node, forbidden):
                raise QueryValidationError(f"Forbidden statement type: {type(node).__name__}")
        if isinstance(node, exp.Anonymous) and node.name.lower() in FORBIDDEN_FUNCTIONS:
            raise QueryValidationError(f"Forbidden function: {node.name}")

    # 4. Check for forbidden keywords as whole words
    # This catches edge cases that might slip through AST parsing
    sql_upper = sql.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        # Use word boundary regex to avoid false positives
        # e.g., "UPDATED_AT" should not trigger "UPDATE"
        if re.search(rf"\b{keyword}\b", sql_upper):
            raise QueryValidationError(f"Forbidden keyword: {keyword}")

    # 5. Must have LIMIT (safety against large result sets), if required
    if require_limit and not parsed.find(exp.Limit):
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
        if isinstance(parsed, exp.Select) and not parsed.find(exp.Limit):
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
