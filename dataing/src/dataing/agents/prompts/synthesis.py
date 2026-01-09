"""Synthesis prompts for root cause determination.

Synthesizes all evidence into a final root cause finding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataing.core.domain_types import AnomalyAlert, Evidence

# Import for metric context helper
from .hypothesis import _build_metric_context

SYSTEM_PROMPT = """You are synthesizing investigation findings to determine root cause.

CRITICAL: Your root cause MUST directly explain the specific metric anomaly.
- If the anomaly is "null_count", root cause must explain what caused NULL values
- If the anomaly is "row_count", root cause must explain missing/extra records
- Do NOT suggest unrelated issues as root cause

REQUIRED FIELDS:

1. root_cause: The UPSTREAM cause, not the symptom (20+ chars, or null if inconclusive)
   - BAD: "NULL user_ids in orders table" (this is the symptom)
   - GOOD: "users ETL job timed out at 03:14 UTC due to API rate limiting"

2. confidence: Score from 0.0 to 1.0
   - 0.9+: Strong evidence with clear causation
   - 0.7-0.9: Good evidence, likely correct
   - 0.5-0.7: Some evidence, but uncertain
   - <0.5: Weak evidence, inconclusive (set root_cause to null)

3. causal_chain: Step-by-step list from root cause to observed symptom (2-6 steps)
   - Example: ["API rate limit hit", "users ETL job timeout", "users table stale after 03:14",
     "orders JOIN produces NULLs", "null_count metric spikes"]
   - Each step must logically lead to the next

4. estimated_onset: When the issue started (timestamp or relative time)
   - Example: "03:14 UTC" or "approximately 6 hours ago" or "since 2024-01-15 batch"
   - Use evidence timestamps to determine this

5. affected_scope: Blast radius - what else is affected?
   - Example: "orders table, downstream_report_daily, customer_analytics dashboard"
   - Consider downstream tables, reports, and consumers

6. supporting_evidence: Specific evidence with data points (1-10 items)

7. recommendations: Actionable items with specific targets (1-5 items)
   - BAD: "Investigate the issue" or "Fix the data" (too vague)
   - GOOD: "Re-run stg_users job: airflow trigger_dag stg_users --backfill 2024-01-15"
   - GOOD: "Add NULL check constraint to orders.user_id column"
   - GOOD: "Contact data-platform team to increase API rate limits for users sync"""


def build_system() -> str:
    """Build synthesis system prompt.

    Returns:
        The system prompt (static, no dynamic values).
    """
    return SYSTEM_PROMPT


def build_user(alert: AnomalyAlert, evidence: list[Evidence]) -> str:
    """Build synthesis user prompt.

    Args:
        alert: The original anomaly alert.
        evidence: All collected evidence.

    Returns:
        Formatted user prompt.
    """
    evidence_text = "\n\n".join(
        [
            f"""### Hypothesis: {e.hypothesis_id}
- Query: {e.query[:200]}...
- Interpretation: {e.interpretation}
- Confidence: {e.confidence}
- Supports hypothesis: {e.supports_hypothesis}"""
            for e in evidence
        ]
    )

    metric_context = _build_metric_context(alert)

    return f"""## Original Anomaly
- Dataset: {alert.dataset_id}
- Metric: {alert.metric_spec.display_name} deviated by {alert.deviation_pct}%
- Anomaly Type: {alert.anomaly_type}
- Expected: {alert.expected_value}
- Actual: {alert.actual_value}
- Date: {alert.anomaly_date}

## What Was Investigated
{metric_context}

## Investigation Findings
{evidence_text}

Synthesize these findings into a root cause determination."""
