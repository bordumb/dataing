"""Git diff asset extraction for code change analysis.

Pure functions for parsing git diffs to extract affected data assets.
No database access — callers pass diffs and receive structured asset lists.
"""

from __future__ import annotations

import re


def extract_dbt_refs(file_path: str, diff_content: str) -> list[str]:
    """Extract dbt ref() and source() calls from a diff.

    Parses patterns like:
    - {{ ref('model_name') }}
    - {{ source('source_name', 'table_name') }}
    - config(materialized='table', alias='custom_name')

    Only analyzes added lines (+ prefix) to detect new references.

    Args:
        file_path: Path of the file being analyzed (for context).
        diff_content: Unified diff content.

    Returns:
        List of asset identifiers found.
    """
    refs: list[str] = []

    # Extract only added lines from diff
    added_lines = _extract_added_lines(diff_content)
    text = "\n".join(added_lines)

    # ref('name') or ref("name")
    ref_pattern = r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"
    for match in re.finditer(ref_pattern, text, re.IGNORECASE):
        refs.append(match.group(1).lower())

    # source('src', 'table') or source("src", "table")
    source_pattern = (
        r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"
    )
    for match in re.finditer(source_pattern, text, re.IGNORECASE):
        source_name = match.group(1).lower()
        table_name = match.group(2).lower()
        refs.append(f"{source_name}.{table_name}")

    # config(... alias='name' ...)
    alias_pattern = r"config\s*\([^)]*alias\s*=\s*['\"]([^'\"]+)['\"]"
    for match in re.finditer(alias_pattern, text, re.IGNORECASE):
        refs.append(match.group(1).lower())

    return list(dict.fromkeys(refs))  # Deduplicate while preserving order


def extract_sql_tables(diff_content: str) -> list[str]:
    """Extract table names from SQL statements in diffs.

    Detects patterns like:
    - FROM schema.table
    - JOIN schema.table
    - INSERT INTO schema.table
    - CREATE TABLE schema.table
    - DROP TABLE schema.table

    Only analyzes added lines (+ prefix) to detect new references.

    Args:
        diff_content: Unified diff content.

    Returns:
        List of table identifiers (schema.table format when available).
    """
    tables: list[str] = []

    # Extract only added lines from diff
    added_lines = _extract_added_lines(diff_content)
    text = "\n".join(added_lines)

    # Table name pattern: optional_schema.table_name
    # Supports: table, schema.table, catalog.schema.table
    table_pattern = r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*"

    # FROM clause (including subqueries are tricky, so keep it simple)
    from_pattern = rf"\bFROM\s+({table_pattern})"
    for match in re.finditer(from_pattern, text, re.IGNORECASE):
        tables.append(match.group(1).lower())

    # JOIN clauses (INNER, LEFT, RIGHT, OUTER, CROSS, FULL)
    join_pattern = rf"\bJOIN\s+({table_pattern})"
    for match in re.finditer(join_pattern, text, re.IGNORECASE):
        tables.append(match.group(1).lower())

    # INSERT INTO
    insert_pattern = rf"\bINSERT\s+INTO\s+({table_pattern})"
    for match in re.finditer(insert_pattern, text, re.IGNORECASE):
        tables.append(match.group(1).lower())

    # UPDATE
    update_pattern = rf"\bUPDATE\s+({table_pattern})"
    for match in re.finditer(update_pattern, text, re.IGNORECASE):
        tables.append(match.group(1).lower())

    # CREATE TABLE / CREATE OR REPLACE TABLE
    create_pattern = (
        rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+"
        rf"(?:IF\s+NOT\s+EXISTS\s+)?({table_pattern})"
    )
    for match in re.finditer(create_pattern, text, re.IGNORECASE):
        tables.append(match.group(1).lower())

    # DROP TABLE
    drop_pattern = rf"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?({table_pattern})"
    for match in re.finditer(drop_pattern, text, re.IGNORECASE):
        tables.append(match.group(1).lower())

    # CREATE VIEW / CREATE OR REPLACE VIEW
    create_view_pattern = (
        rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+"
        rf"(?:IF\s+NOT\s+EXISTS\s+)?({table_pattern})"
    )
    for match in re.finditer(create_view_pattern, text, re.IGNORECASE):
        tables.append(match.group(1).lower())

    # Deduplicate and filter common SQL keywords that might match
    keywords = {
        "select",
        "from",
        "where",
        "and",
        "or",
        "not",
        "in",
        "is",
        "null",
        "as",
        "on",
        "using",
        "group",
        "by",
        "order",
        "having",
        "limit",
        "offset",
        "union",
        "intersect",
        "except",
        "all",
        "distinct",
        "case",
        "when",
        "then",
        "else",
        "end",
        "true",
        "false",
        "values",
    }

    return list(dict.fromkeys(t for t in tables if t not in keywords))


def parse_affected_assets(file_path: str, diff_content: str | None) -> list[dict[str, str]]:
    """Determine affected assets based on file type and diff content.

    Routes to the appropriate parser based on file extension/path:
    - .sql files in models/ or dbt paths -> extract_dbt_refs + extract_sql_tables
    - .sql files elsewhere -> extract_sql_tables only
    - .py files -> extract_sql_tables from string literals (basic)
    - Other files -> empty list

    Args:
        file_path: Path of the changed file.
        diff_content: Unified diff content (None if unavailable).

    Returns:
        List of affected assets with structure:
        [{"name": "schema.table", "type": "table", "source": "dbt_ref"}]
    """
    if diff_content is None:
        return []

    assets: list[dict[str, str]] = []
    file_lower = file_path.lower()

    # dbt model file detection
    is_dbt_file = (
        file_lower.endswith(".sql")
        and any(path in file_lower for path in ["models/", "dbt/", "/dbt_project/", "/transform/"])
    ) or file_lower.endswith((".sql.jinja", ".sql.jinja2"))

    is_sql_file = file_lower.endswith((".sql", ".sql.jinja", ".sql.jinja2"))

    if is_sql_file:
        # SQL files: extract both dbt refs (if applicable) and SQL tables
        if is_dbt_file:
            dbt_refs = extract_dbt_refs(file_path, diff_content)
            for ref in dbt_refs:
                assets.append({"name": ref, "type": "model", "source": "dbt_ref"})

        sql_tables = extract_sql_tables(diff_content)
        for table in sql_tables:
            # Avoid duplicates from dbt refs
            if not any(a["name"] == table for a in assets):
                assets.append({"name": table, "type": "table", "source": "sql_parse"})

    elif file_lower.endswith(".py"):
        # Python files: extract SQL from string literals (basic extraction)
        sql_tables = extract_sql_tables(diff_content)
        for table in sql_tables:
            assets.append({"name": table, "type": "table", "source": "python_sql"})

    # Can add more file types here (e.g., .yaml for dbt sources, .dag for Airflow)

    return assets


def _extract_added_lines(diff_content: str) -> list[str]:
    """Extract only added lines from a unified diff.

    Added lines start with '+' but not '+++' (file header).

    Args:
        diff_content: Unified diff content.

    Returns:
        List of added lines (without the + prefix).
    """
    lines = []
    for line in diff_content.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            # Remove the + prefix
            lines.append(line[1:])
    return lines
