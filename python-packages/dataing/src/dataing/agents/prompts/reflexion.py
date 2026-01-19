"""Reflexion prompts for query correction.

Fixes failed SQL queries based on error messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import SchemaResponse
    from dataing.core.domain_types import Hypothesis

SYSTEM_PROMPT = """You are debugging a failed SQL query. Analyze the error and fix the query.

AVAILABLE SCHEMA:
{schema}

COMMON FIXES:
- "column does not exist": Check column name spelling, use correct table
- "relation does not exist": Use fully qualified name (schema.table)
- "type mismatch": Cast values appropriately
- "syntax error": Check SQL syntax for the target database

CRITICAL: Only use tables and columns from the schema above."""


def build_system(schema: SchemaResponse) -> str:
    """Build reflexion system prompt.

    Args:
        schema: Available database schema.

    Returns:
        Formatted system prompt.
    """
    return SYSTEM_PROMPT.format(schema=schema.to_prompt_string())


def build_user(hypothesis: Hypothesis, previous_error: str) -> str:
    """Build reflexion user prompt.

    Args:
        hypothesis: The hypothesis being tested.
        previous_error: Error from the previous query attempt.

    Returns:
        Formatted user prompt.
    """
    return f"""The previous query failed. Generate a corrected version.

ORIGINAL QUERY:
{hypothesis.suggested_query}

ERROR MESSAGE:
{previous_error}

HYPOTHESIS BEING TESTED:
{hypothesis.title}

Generate a corrected SQL query that avoids this error."""
