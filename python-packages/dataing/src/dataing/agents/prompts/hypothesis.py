"""Hypothesis generation prompts.

Generates hypotheses about what could have caused a data anomaly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataing.core.domain_types import AnomalyAlert, InvestigationContext

SYSTEM_PROMPT = """You are a data quality investigator. Given an anomaly alert and database context,
generate {num_hypotheses} hypotheses about what could have caused the anomaly.

CRITICAL: Pay close attention to the METRIC NAME in the alert:
- "null_count": Investigate what causes NULL values (app bugs, missing required fields, ETL drops)
- "row_count" or "volume": Investigate missing/extra records (filtering bugs, data loss, duplicates)
- "duplicate_count": Investigate what causes duplicate records
- Other metrics: Investigate value changes, data corruption, calculation errors

HYPOTHESIS CATEGORIES:
- upstream_dependency: Source table missing data, late arrival, schema change
- transformation_bug: ETL logic error, incorrect aggregation, wrong join
- data_quality: Nulls, duplicates, invalid values, schema drift
- infrastructure: Job failure, timeout, resource exhaustion
- expected_variance: Seasonality, holiday, known business event

REQUIRED FIELDS FOR EACH HYPOTHESIS:

1. id: Unique identifier like 'h1', 'h2', etc.
2. title: Short, specific title describing the potential cause (10-200 chars)
3. category: One of the categories listed above
4. reasoning: Why this could be the cause (20+ chars)
5. suggested_query: SQL query to investigate (must include LIMIT, SELECT only)
6. expected_if_true: What query results would CONFIRM this hypothesis
   - Be specific about counts, patterns, or values you expect to see
   - Example: "Multiple rows with NULL user_id clustered after 03:00 UTC"
   - Example: "Row count drops >50% compared to previous day"
7. expected_if_false: What query results would REFUTE this hypothesis
   - Example: "Zero NULL user_ids, or NULLs evenly distributed across all times"
   - Example: "Row count consistent with historical average"

TESTABILITY IS CRITICAL:
- A good hypothesis is FALSIFIABLE - the query can definitively prove it wrong
- The expected_if_true and expected_if_false should be mutually exclusive
- Avoid vague expectations like "some issues found" or "data looks wrong"

DIMENSIONAL ANALYSIS IS ESSENTIAL:
- Use GROUP BY on categorical columns to segment the data and find patterns
- Common dimensions: channel, platform, version, region, source, type, category
- If anomalies cluster in ONE segment (e.g., one app version, one channel), that's the root cause
- Example: GROUP BY channel, app_version to see if issues are isolated to specific clients
- Dimensional breakdowns often reveal root causes faster than temporal analysis alone

Generate diverse hypotheses covering multiple categories when plausible."""


def build_system(num_hypotheses: int = 5) -> str:
    """Build hypothesis system prompt.

    Args:
        num_hypotheses: Target number of hypotheses to generate.

    Returns:
        Formatted system prompt.
    """
    return SYSTEM_PROMPT.format(num_hypotheses=num_hypotheses)


def _build_metric_context(alert: AnomalyAlert) -> str:
    """Build context string based on metric_spec type.

    This is the key win from structured MetricSpec - different prompt
    framing based on what kind of metric we're investigating.
    """
    spec = alert.metric_spec

    if spec.metric_type == "column":
        return f"""The anomaly is on column `{spec.expression}` in table `{alert.dataset_id}`.
Investigate why this column's {alert.anomaly_type} changed.
Focus on: NULL introduction, upstream joins, filtering changes, application bugs.
All hypotheses MUST focus on the `{spec.expression}` column specifically."""

    elif spec.metric_type == "sql_expression":
        cols = ", ".join(spec.columns_referenced) if spec.columns_referenced else "unknown"
        return f"""The anomaly is on a computed metric: {spec.expression}
This expression references columns: {cols}
Investigate why this calculation's result changed.
Focus on: input column changes, expression logic errors, upstream data shifts."""

    elif spec.metric_type == "dbt_metric":
        url_info = f"\nDefinition: {spec.source_url}" if spec.source_url else ""
        return f"""The anomaly is on dbt metric `{spec.expression}`.{url_info}
Investigate the metric's upstream models and their data quality.
Focus on: upstream model failures, source data changes, metric definition issues."""

    else:  # description
        return f"""The anomaly is described as: {spec.expression}
This is a free-text description. Infer which columns/tables are involved
from the schema and investigate accordingly.
Focus on: matching the description to actual schema elements."""


def build_user(alert: AnomalyAlert, context: InvestigationContext) -> str:
    """Build hypothesis user prompt.

    Args:
        alert: The anomaly alert to investigate.
        context: Available schema and lineage context.

    Returns:
        Formatted user prompt.
    """
    lineage_section = ""
    if context.lineage:
        lineage_section = f"""
## Data Lineage
{context.lineage.to_prompt_string()}
"""

    metric_context = _build_metric_context(alert)

    return f"""## Anomaly Alert
- Dataset: {alert.dataset_id}
- Metric: {alert.metric_spec.display_name}
- Anomaly Type: {alert.anomaly_type}
- Expected: {alert.expected_value}
- Actual: {alert.actual_value}
- Deviation: {alert.deviation_pct}%
- Anomaly Date: {alert.anomaly_date}
- Severity: {alert.severity}

## What To Investigate
{metric_context}

## Available Schema
{context.schema.to_prompt_string()}
{lineage_section}
Generate hypotheses to investigate why {alert.metric_spec.display_name} deviated
from {alert.expected_value} to {alert.actual_value} ({alert.deviation_pct}% change)."""
