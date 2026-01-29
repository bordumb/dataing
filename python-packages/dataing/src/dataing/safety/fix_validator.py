"""SQL Fix Validator - Validates LLM-generated SQL fixes for safety.

This module ensures that SQL fixes proposed by the synthesis agent are:
1. Syntactically correct (parsed by sqlglot)
2. Safe to execute (no DROP TABLE, no TRUNCATE, no DELETE without WHERE)
3. Scoped correctly (only touches tables in the investigation context)
4. Reasonable in impact (estimated affected rows below threshold)

SAFETY IS NON-NEGOTIABLE:
- Never allow DROP TABLE without explicit flag
- Never allow DELETE without WHERE clause
- Never allow TRUNCATE
- Always validate syntax before showing to user
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import sqlglot
from sqlglot import exp

if TYPE_CHECKING:
    from dataing.agents.models import FixProposal

# Statements that are NEVER allowed (completely blacklisted)
BLACKLISTED_STATEMENTS: set[type[exp.Expression]] = {
    exp.TruncateTable,
    exp.Grant,
    exp.Revoke,
}

# DDL statements that need special handling
DDL_STATEMENTS: set[type[exp.Expression]] = {
    exp.Drop,
    exp.Create,
    exp.Alter,
}

# DML statements that need WHERE clause validation
DML_WITH_WHERE_REQUIRED: set[type[exp.Expression]] = {
    exp.Delete,
    exp.Update,
}

# Default maximum affected rows threshold
DEFAULT_MAX_AFFECTED_ROWS = 100_000


@dataclass
class FixValidationResult:
    """Result of validating a SQL fix proposal.

    Attributes:
        is_valid: Whether the fix passed all validation checks.
        errors: List of validation error messages.
        warnings: List of validation warning messages.
        estimated_affected_rows: Estimated number of rows affected (if determinable).
        tables_touched: Set of table names the fix will modify.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_affected_rows: int | None = None
    tables_touched: set[str] = field(default_factory=set)


def validate_fix_sql(
    sql: str,
    *,
    dialect: str = "postgres",
    allowed_tables: set[str] | None = None,
    max_affected_rows: int = DEFAULT_MAX_AFFECTED_ROWS,
    allow_drop: bool = False,
    allow_truncate: bool = False,
) -> FixValidationResult:
    """Validate a SQL fix for safety and correctness.

    This function performs multiple layers of validation:
    1. Parse with sqlglot to verify syntax
    2. Check for blacklisted statement types
    3. Validate WHERE clause for DELETE/UPDATE
    4. Check that only allowed tables are touched
    5. Estimate affected rows (basic heuristic)

    Args:
        sql: The SQL fix to validate.
        dialect: SQL dialect for parsing (default: postgres).
        allowed_tables: Set of table names the fix is allowed to modify.
                       If None, all tables are allowed.
        max_affected_rows: Maximum estimated affected rows allowed.
        allow_drop: If True, allows DROP statements (use with caution).
        allow_truncate: If True, allows TRUNCATE statements (use with caution).

    Returns:
        FixValidationResult with validation status and any errors/warnings.

    Examples:
        >>> result = validate_fix_sql("UPDATE orders SET status = 'fixed' WHERE id = 1")
        >>> result.is_valid
        True

        >>> result = validate_fix_sql("DELETE FROM orders")  # No WHERE
        >>> result.is_valid
        False
        >>> "WHERE clause" in result.errors[0]
        True
    """
    errors: list[str] = []
    warnings: list[str] = []
    tables_touched: set[str] = set()

    # Empty SQL check
    if not sql or not sql.strip():
        return FixValidationResult(
            is_valid=False,
            errors=["Empty SQL statement"],
        )

    # 1. Parse with sqlglot
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as e:
        return FixValidationResult(
            is_valid=False,
            errors=[f"Invalid SQL syntax: {e}"],
        )

    # 2. Check for blacklisted statements
    for node in parsed.walk():
        # Always blacklisted
        if isinstance(node, tuple(BLACKLISTED_STATEMENTS)):
            if isinstance(node, exp.TruncateTable) and not allow_truncate:
                errors.append("TRUNCATE is not allowed - use DELETE with WHERE instead")
            elif isinstance(node, exp.Grant | exp.Revoke):
                errors.append(f"{type(node).__name__} statements are not allowed in fixes")

        # DDL requires special handling
        if isinstance(node, exp.Drop) and not allow_drop:
            errors.append("DROP statements are not allowed - set allow_drop=True to override")

    # 3. Validate WHERE clause for DELETE/UPDATE
    if isinstance(parsed, exp.Delete | exp.Update):
        where_clause = parsed.find(exp.Where)
        if where_clause is None:
            errors.append(
                f"{type(parsed).__name__} without WHERE clause is not allowed - "
                "specify conditions to limit scope"
            )
        else:
            # Check for trivially true WHERE clauses
            _check_trivial_where(where_clause, warnings)

    # 4. Extract tables touched
    tables_touched = _extract_tables(parsed)

    # 5. Validate allowed tables
    if allowed_tables is not None:
        disallowed = tables_touched - allowed_tables
        if disallowed:
            errors.append(
                f"Fix touches tables outside investigation scope: {sorted(disallowed)}. "
                f"Allowed tables: {sorted(allowed_tables)}"
            )

    # 6. Estimate affected rows (basic heuristic)
    estimated_rows = _estimate_affected_rows(parsed, warnings)

    if estimated_rows is not None and estimated_rows > max_affected_rows:
        warnings.append(
            f"Estimated {estimated_rows:,} affected rows exceeds threshold of "
            f"{max_affected_rows:,}. Consider adding more specific WHERE conditions."
        )

    return FixValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        estimated_affected_rows=estimated_rows,
        tables_touched=tables_touched,
    )


def validate_fix_proposal(
    proposal: FixProposal,
    *,
    dialect: str = "postgres",
    allowed_tables: set[str] | None = None,
    max_affected_rows: int = DEFAULT_MAX_AFFECTED_ROWS,
) -> FixValidationResult:
    """Validate a FixProposal object.

    Validates the fix based on its type:
    - sql_ddl and sql_dml: Full SQL validation
    - dbt_patch: Basic syntax check if it's SQL
    - python_patch and manual_instruction: Always valid (not SQL)

    Args:
        proposal: The FixProposal to validate.
        dialect: SQL dialect for parsing.
        allowed_tables: Set of allowed table names.
        max_affected_rows: Maximum estimated affected rows.

    Returns:
        FixValidationResult with validation status.
    """
    if proposal.fix_type == "manual_instruction":
        return FixValidationResult(is_valid=True)

    if proposal.fix_type == "python_patch":
        # Python patches are validated at model creation time
        return FixValidationResult(is_valid=True)

    if proposal.fix_type == "dbt_patch":
        # dbt patches with Jinja can't be fully validated
        if "{{" in proposal.code or "{%" in proposal.code:
            return FixValidationResult(
                is_valid=True,
                warnings=["dbt patch contains Jinja - SQL syntax not fully validated"],
            )
        # Try to validate as SQL
        return validate_fix_sql(
            proposal.code,
            dialect=dialect,
            allowed_tables=allowed_tables,
            max_affected_rows=max_affected_rows,
        )

    # sql_ddl or sql_dml
    return validate_fix_sql(
        proposal.code,
        dialect=dialect,
        allowed_tables=allowed_tables,
        max_affected_rows=max_affected_rows,
        allow_drop=(proposal.fix_type == "sql_ddl"),  # DDL can use DROP
    )


def _extract_tables(parsed: exp.Expression) -> set[str]:
    """Extract all table names from a SQL statement.

    Args:
        parsed: The parsed SQL expression.

    Returns:
        Set of table names (including schema.table format if present).
    """
    tables: set[str] = set()

    for table in parsed.find_all(exp.Table):
        if table.name:
            if table.db:
                tables.add(f"{table.db}.{table.name}")
            else:
                tables.add(table.name)

    return tables


def _check_trivial_where(where: exp.Where, warnings: list[str]) -> None:
    """Check for trivially true WHERE clauses.

    Args:
        where: The WHERE clause expression.
        warnings: List to append warnings to.
    """
    condition = where.this

    # Check for 1=1, true, TRUE, etc.
    if isinstance(condition, exp.Boolean) and condition.this:
        warnings.append("WHERE clause is trivially true (1=1 or TRUE)")
        return

    # Check for literal equality that's always true
    if isinstance(condition, exp.EQ):
        left, right = condition.this, condition.expression
        if isinstance(left, exp.Literal) and isinstance(right, exp.Literal):
            if left.this == right.this:
                warnings.append(f"WHERE clause is trivially true ({left.this}={right.this})")


def _estimate_affected_rows(parsed: exp.Expression, warnings: list[str]) -> int | None:
    """Estimate affected rows based on statement structure.

    This is a heuristic - actual row counts require database access.

    Args:
        parsed: The parsed SQL expression.
        warnings: List to append warnings to.

    Returns:
        Estimated affected rows, or None if cannot be determined.
    """
    # For statements without WHERE, assume large impact
    if isinstance(parsed, exp.Delete | exp.Update):
        where = parsed.find(exp.Where)
        if where is None:
            return None  # Can't estimate without WHERE

        # Check if WHERE uses specific identifiers (better than no constraint)
        condition = where.this

        # Very rough heuristic: primary key lookup = 1 row
        if _is_pk_lookup(condition):
            return 1

        # Check for IN clause with limited values
        in_count = _count_in_values(condition)
        if in_count is not None:
            return in_count

        # Check for LIMIT clause
        limit = parsed.find(exp.Limit)
        if limit and limit.expression:
            try:
                return int(limit.expression.this)
            except (ValueError, TypeError):
                pass

    # For DDL statements
    if isinstance(parsed, exp.Create | exp.Alter | exp.Drop):
        return 0  # DDL affects schema, not data rows

    # For INSERT
    if isinstance(parsed, exp.Insert):
        values = parsed.find(exp.Values)
        if values:
            # Count number of value tuples
            return len(list(values.find_all(exp.Tuple)))

    return None


def _is_pk_lookup(condition: exp.Expression) -> bool:
    """Check if condition looks like a primary key lookup.

    Args:
        condition: The WHERE condition.

    Returns:
        True if it looks like a PK lookup (column = literal).
    """
    if isinstance(condition, exp.EQ):
        left, right = condition.this, condition.expression
        # Column = Literal pattern
        if isinstance(left, exp.Column) and isinstance(right, exp.Literal):
            col_name = left.name.lower() if left.name else ""
            if col_name in ("id", "pk", "uuid", "guid"):
                return True
        # Literal = Column pattern
        if isinstance(right, exp.Column) and isinstance(left, exp.Literal):
            col_name = right.name.lower() if right.name else ""
            if col_name in ("id", "pk", "uuid", "guid"):
                return True
    return False


def _count_in_values(condition: exp.Expression) -> int | None:
    """Count values in IN clauses for row estimation.

    Args:
        condition: The WHERE condition.

    Returns:
        Number of values in IN clause, or None if not applicable.
    """
    # Check if condition itself is an IN expression
    if isinstance(condition, exp.In):
        # The values are in the expressions list directly
        expressions = condition.expressions
        if expressions:
            return len(expressions)

    # Search for IN expressions within the condition
    for in_expr in condition.find_all(exp.In):
        expressions = in_expr.expressions
        if expressions:
            return len(expressions)

    return None
