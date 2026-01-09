"""Query generation prompts.

Generates SQL queries to test hypotheses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import SchemaResponse
    from dataing.core.domain_types import Hypothesis

SYSTEM_PROMPT = """You are a SQL expert generating investigative queries.

CRITICAL RULES:
1. Use ONLY tables from the schema: {table_names}
2. Use ONLY columns that exist in those tables
3. SELECT queries ONLY - no mutations
4. Always include LIMIT clause (max 10000)
5. Use fully qualified table names (schema.table)

INVESTIGATION TECHNIQUES:
- Use GROUP BY on categorical columns to find patterns (channel, platform, version, region, etc.)
- Segment analysis often reveals root causes faster than aggregate counts
- If issues cluster in one segment, that segment IS the root cause
- Compare affected vs unaffected segments to isolate the problem

SCHEMA:
{schema}"""


def build_system(schema: SchemaResponse) -> str:
    """Build query system prompt.

    Args:
        schema: Available database schema.

    Returns:
        Formatted system prompt.
    """
    return SYSTEM_PROMPT.format(
        table_names=schema.get_table_names(),
        schema=schema.to_prompt_string(),
    )


def build_user(hypothesis: Hypothesis) -> str:
    """Build query user prompt.

    Args:
        hypothesis: The hypothesis to test.

    Returns:
        Formatted user prompt.
    """
    return f"""Generate a SQL query to test this hypothesis:

Hypothesis: {hypothesis.title}
Category: {hypothesis.category.value}
Reasoning: {hypothesis.reasoning}

Generate a query that would confirm or refute this hypothesis."""
