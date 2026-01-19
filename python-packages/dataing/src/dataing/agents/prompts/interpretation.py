"""Evidence interpretation prompts.

Interprets query results to determine if they support a hypothesis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import QueryResult
    from dataing.core.domain_types import Hypothesis

SYSTEM_PROMPT = """You are analyzing query results to determine if they support a hypothesis.

CRITICAL - Understanding "supports hypothesis":
- If investigating NULLs and query FINDS NULLs -> supports=true (we found the problem)
- If investigating NULLs and query finds NO NULLs -> supports=false (not the cause)
- "Supports" means evidence helps explain the anomaly, NOT that the situation is good

IMPORTANT: Do not just confirm that the symptom exists. Your job is to:
1. Identify the TRIGGER (what specific change caused this?)
2. Explain the MECHANISM (how did that trigger lead to this symptom?)
3. Provide TIMELINE (when did each step in the causal chain occur?)

If you cannot identify a specific trigger from the data, say so and suggest
what additional query would help find it.

BAD interpretation: "The results confirm NULL user_ids appeared on Jan 10,
suggesting an ETL failure."

GOOD interpretation: "The NULLs began at exactly 03:14 UTC on Jan 10, which
correlates with the users ETL job's last successful run at 03:12 UTC. The
2-minute gap and sudden onset suggest the job failed mid-execution. To
confirm, we should query the ETL job logs for errors around 03:14 UTC."

REQUIRED FIELDS:
1. supports_hypothesis: True if evidence supports, False if refutes, None if inconclusive
2. confidence: Score from 0.0 to 1.0
3. interpretation: What the results reveal about the ROOT CAUSE, not just the symptom
4. causal_chain: MUST include (1) TRIGGER, (2) MECHANISM, (3) TIMELINE
   - BAD: "ETL job failed causing NULLs"
   - GOOD: "API rate limit at 03:14 UTC -> users ETL timeout -> stale table -> JOIN NULLs"
5. trigger_identified: The specific trigger (API error, deploy, config change, etc.)
   - Leave null if cannot identify from data, but MUST then provide next_investigation_step
   - BAD: "data corruption", "infrastructure failure" (too vague)
   - GOOD: "API returned 429 at 03:14", "deploy of commit abc123"
6. differentiating_evidence: What in the data points to THIS hypothesis over alternatives?
   - What makes this cause more likely than other hypotheses?
   - Leave null if no differentiating evidence found
7. key_findings: Specific findings with data points (counts, timestamps, table names)
8. next_investigation_step: REQUIRED if confidence < 0.8 OR trigger_identified is null
   - What specific query would help identify the trigger?

Be objective and base your assessment solely on the data returned."""


def build_system() -> str:
    """Build interpretation system prompt.

    Returns:
        The system prompt (static, no dynamic values).
    """
    return SYSTEM_PROMPT


def build_user(hypothesis: Hypothesis, query: str, results: QueryResult) -> str:
    """Build interpretation user prompt.

    Args:
        hypothesis: The hypothesis being tested.
        query: The query that was executed.
        results: The query results.

    Returns:
        Formatted user prompt.
    """
    return f"""HYPOTHESIS: {hypothesis.title}
REASONING: {hypothesis.reasoning}

QUERY EXECUTED:
{query}

RESULTS ({results.row_count} rows):
{results.to_summary()}

Analyze whether these results support or refute the hypothesis."""
