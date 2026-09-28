"""Synthesis prompts for root cause determination.

Synthesizes all evidence into a final root cause finding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dataing.agents.prompts.brief import team_brief_section

if TYPE_CHECKING:
    from dataing.core.domain_types import (
        AnomalyAlert,
        Evidence,
        RelevantCodeChange,
        UntestedHypothesis,
    )

# Import for metric context helper
from .hypothesis import _build_metric_context

SYSTEM_PROMPT = """You are synthesizing investigation findings to determine root cause.

CRITICAL: Your root cause MUST directly explain the specific metric anomaly.
- If the anomaly is "null_count", root cause must explain what caused NULL values
- If the anomaly is "row_count", root cause must explain missing/extra records
- Do NOT suggest unrelated issues as root cause

UNTESTED HYPOTHESES:
Hypotheses listed under "Untested Hypotheses" could not be tested because their
evaluation failed (for example, their query or its interpretation failed). A failed
evaluation is not evidence: never treat an untested hypothesis as refuted or ruled out.
Untested hypotheses remain possible explanations, so lower confidence accordingly.
If no hypothesis was tested, the investigation is inconclusive: set root_cause to null,
keep confidence below 0.5, use causal_chain and supporting_evidence to state what could
not be tested and why, set estimated_onset to "unknown", and recommend fixing what made
the evaluations fail.

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
   - GOOD: "Contact data-platform team to increase API rate limits for users sync"

WHEN CODE CHANGES ARE RELEVANT:
If the investigation includes recent code changes (commits), and a code deploy is the root cause:
- Reference the commit hash (first 8 chars) in root_cause
- Include "revert commit" or "fix commit" recommendations with the specific hash
- Example root_cause: "Deploy of commit abc12345 introduced a bug in order validation logic"
- Example recommendation: "Revert commit abc12345 or deploy hotfix to correct order validation"

FIX PROPOSAL (OPTIONAL - only when confidence > 0.7):

8. fix_proposal: If confidence > 0.7, propose a concrete fix the user can apply.
   Only include this field when you have a high-confidence root cause.

   fix_proposal has these required fields:
   - fix_type: One of "sql_ddl", "sql_dml", "dbt_patch", "python_patch", "manual_instruction"
   - description: Human-readable explanation of what the fix does (10+ chars)
   - code: The actual fix code (SQL, dbt, Python, or instruction text)
   - confidence: Your confidence this fix will work (0.0-1.0)
   - risks: List of potential negative effects (can be empty)
   - rollback: SQL/code to undo the fix (null if not applicable)
   - requires_confirmation: Always true for DDL, true by default for others
   - estimated_impact: What rows/tables are affected (e.g., "Updates ~485 rows in orders")
   - target_asset: The table/model being fixed

   CHOOSING fix_type based on root cause category:
   - Schema issues (missing columns, wrong types) → sql_ddl (ALTER TABLE)
   - Data quality issues (NULLs, duplicates) → sql_dml (UPDATE/DELETE)
   - Transformation logic bugs → dbt_patch (model SQL changes)
   - Code bugs → python_patch (code changes)
   - External/manual intervention needed → manual_instruction

   GOOD FIX EXAMPLES:
   - sql_dml: "UPDATE orders SET user_id = (SELECT id FROM users WHERE email = orders.user_email)
              WHERE user_id IS NULL AND user_email IS NOT NULL"
   - sql_ddl: "ALTER TABLE orders ALTER COLUMN user_id SET NOT NULL"
   - dbt_patch: "SELECT COALESCE(user_id, -1) as user_id FROM {{ ref('stg_orders') }}"
   - manual_instruction: "1. Contact data-eng team\\n2. Re-run users_etl job\\n3. Verify data"

   BAD FIX EXAMPLES (DO NOT DO):
   - "DELETE FROM orders" (too broad, no WHERE clause)
   - "DROP TABLE orders" (destructive without clear justification)
   - "Fix the data" (vague instruction, not actionable)

   SAFETY RULES:
   - NEVER propose DROP TABLE without explicit user request
   - ALWAYS include WHERE clause for UPDATE/DELETE
   - PREFER manual_instruction when unsure
   - Include rollback statement when possible
"""


def build_system() -> str:
    """Build synthesis system prompt.

    Returns:
        The system prompt (static, no dynamic values).
    """
    return SYSTEM_PROMPT


def _build_code_changes_section(changes: list[RelevantCodeChange]) -> str:
    """Build a formatted section showing related code changes.

    Args:
        changes: List of relevant code changes.

    Returns:
        Formatted string for inclusion in the prompt.
    """
    if not changes:
        return ""

    lines = ["## Related Code Changes"]
    lines.append("These commits occurred near the anomaly timeframe:")
    lines.append("")

    for change in changes:
        date_str = (
            change.committed_at.strftime("%Y-%m-%d %H:%M") if change.committed_at else "unknown"
        )
        author = change.author_name or "unknown"
        message = (change.message or "No message")[:80]  # Truncate for synthesis
        commit_short = change.commit_hash[:8]

        lines.append(f"- **{commit_short}** ({date_str}) by {author}: {message}")

    lines.append("")
    lines.append(
        "If a code change caused the anomaly, reference the commit hash in root_cause "
        "and recommendations."
    )
    return "\n".join(lines)


def _build_untested_section(untested: list[UntestedHypothesis]) -> str:
    """Build a section listing hypotheses whose evaluation failed.

    Args:
        untested: Hypotheses that could not be tested.

    Returns:
        Formatted string for inclusion in the prompt.
    """
    lines = ["## Untested Hypotheses"]
    lines.append("These could not be tested, so they are neither supported nor refuted:")
    lines.append("")

    for hypothesis in untested:
        error = " ".join(hypothesis.error.split())[:300]  # One bounded line for synthesis
        lines.append(f"- {hypothesis.hypothesis_id} ({hypothesis.title}): {error}")

    return "\n".join(lines)


def build_user(
    alert: AnomalyAlert,
    evidence: list[Evidence],
    code_changes: list[RelevantCodeChange] | None = None,
    untested_hypotheses: list[UntestedHypothesis] | None = None,
) -> str:
    """Build synthesis user prompt.

    Args:
        alert: The original anomaly alert.
        evidence: All collected evidence.
        code_changes: Optional list of recent code changes related to the investigation.
        untested_hypotheses: Optional hypotheses whose evaluation failed.

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
    if not evidence:
        evidence_text = "No evidence was collected."

    metric_context = _build_metric_context(alert)

    untested_section = ""
    if untested_hypotheses:
        untested_section = f"\n{_build_untested_section(untested_hypotheses)}\n"

    code_changes_section = ""
    if code_changes:
        code_changes_section = f"\n{_build_code_changes_section(code_changes)}\n"

    return f"""## Original Anomaly
- Dataset: {alert.dataset_id}
- Metric: {alert.metric_spec.display_name} deviated by {alert.deviation_pct}%
- Anomaly Type: {alert.anomaly_type}
- Expected: {alert.expected_value}
- Actual: {alert.actual_value}
- Date: {alert.anomaly_date}

## What Was Investigated
{metric_context}
{team_brief_section(alert)}
## Investigation Findings
{evidence_text}
{untested_section}{code_changes_section}
Synthesize these findings into a root cause determination."""
