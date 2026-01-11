"""Query generation prompts.

Generates SQL queries to test hypotheses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
- Column: {alert.metric_spec.expression or ', '.join(alert.metric_spec.columns_referenced)}
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

    return f"""Generate a SQL query to test this hypothesis:

Hypothesis: {hypothesis.title}
Category: {hypothesis.category.value}
Reasoning: {hypothesis.reasoning}

Generate a query that would confirm or refute this hypothesis.{date_hint}"""
