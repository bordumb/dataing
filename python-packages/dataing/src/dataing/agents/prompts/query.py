"""Query generation prompts.

Generates SQL queries to test hypotheses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dataing.agents.prompts.brief import team_brief_section

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import SchemaResponse
    from dataing.core.domain_types import AnomalyAlert, Hypothesis

SYSTEM_PROMPT = """You are a SQL expert generating investigative queries.

CRITICAL RULES:
1. Use ONLY tables from the schema: {table_names}
2. Use ONLY columns that exist in those tables
3. SELECT queries ONLY - no mutations
4. Always include LIMIT clause (max 10000)
5. Use fully qualified table names (schema.table)
6. ALWAYS filter by the anomaly date when investigating temporal data

INVESTIGATION TECHNIQUES:
- Use GROUP BY on categorical columns to find patterns (channel, platform, version, region, etc.)
- Segment analysis often reveals root causes faster than aggregate counts
- If issues cluster in ONE segment (e.g., one app version, one channel), that IS the root cause
- Compare affected vs unaffected segments to isolate the problem

{alert_context}

SCHEMA:
{schema}"""


def build_system(
    schema: SchemaResponse,
    alert: AnomalyAlert | None = None,
) -> str:
    """Build query system prompt.

    Args:
        schema: Available database schema.
        alert: The anomaly alert being investigated (for date/context).

    Returns:
        Formatted system prompt.
    """
    alert_context = ""
    if alert:
        alert_context = f"""ALERT CONTEXT (use these values in your queries):
- Anomaly Date: {alert.anomaly_date}
- Table: {alert.dataset_id}
- Column: {alert.metric_spec.expression or ", ".join(alert.metric_spec.columns_referenced)}
- Anomaly Type: {alert.anomaly_type}
- Expected Value: {alert.expected_value}
- Actual Value: {alert.actual_value}
- Deviation: {alert.deviation_pct}%

IMPORTANT: Filter your query to focus on the anomaly date ({alert.anomaly_date})."""

    return SYSTEM_PROMPT.format(
        table_names=schema.get_table_names(),
        schema=schema.to_prompt_string(),
        alert_context=alert_context,
    )


def build_user(hypothesis: Hypothesis, alert: AnomalyAlert | None = None) -> str:
    """Build query user prompt.

    Args:
        hypothesis: The hypothesis to test.
        alert: The anomaly alert being investigated (for date/context).

    Returns:
        Formatted user prompt.
    """
    date_hint = ""
    if alert:
        date_hint = f"\n\nIMPORTANT: Focus your query on the anomaly date: {alert.anomaly_date}"
        date_hint += team_brief_section(alert)

    # Use the suggested query if available - it was crafted during hypothesis generation
    suggested_query_section = ""
    if hypothesis.suggested_query:
        # Explicitly tell LLM to update dates if alert has a specific date
        date_override = ""
        if alert:
            date_override = f"""
CRITICAL: If the suggested query contains ANY date that is NOT {alert.anomaly_date}, \
you MUST replace it with {alert.anomaly_date}. The anomaly date is {alert.anomaly_date}."""

        suggested_query_section = f"""

SUGGESTED QUERY (use this as your starting point, refine if needed):
```sql
{hypothesis.suggested_query}
```
{date_override}
Use this query directly if it looks correct for the schema. Only modify it if:
- Table/column names need adjustment for the actual schema
- The date filter needs updating to use {alert.anomaly_date if alert else "the correct date"}
- There's a syntax issue"""

    return f"""Generate a SQL query to test this hypothesis:

Hypothesis: {hypothesis.title}
Category: {hypothesis.category.value}
Reasoning: {hypothesis.reasoning}{suggested_query_section}

Generate a query that would confirm or refute this hypothesis.{date_hint}"""
