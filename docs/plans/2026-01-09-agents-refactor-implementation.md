# Agents Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract LLM prompts into a dedicated module and promote agents to first-class domain concept.

**Architecture:** Create `dataing/src/dataing/agents/` with `AgentClient` facade, `models.py` for response schemas, and `prompts/` folder with protocol interface + separate files per prompt type.

**Tech Stack:** Python, Pydantic, BondAgent, PydanticAI

---

## Task 1: Create Directory Structure

**Files:**
- Create: `dataing/src/dataing/agents/__init__.py`
- Create: `dataing/src/dataing/agents/prompts/__init__.py`

**Step 1: Create agents package**

```bash
mkdir -p dataing/src/dataing/agents/prompts
```

**Step 2: Create agents/__init__.py**

```python
"""Investigation agents package.

This package contains the LLM agents used in the investigation workflow.
Agents are first-class domain concepts, not infrastructure adapters.
"""

from bond import StreamHandlers

from .client import AgentClient
from .models import (
    HypothesesResponse,
    HypothesisResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)

__all__ = [
    "AgentClient",
    "StreamHandlers",
    "HypothesesResponse",
    "HypothesisResponse",
    "InterpretationResponse",
    "QueryResponse",
    "SynthesisResponse",
]
```

**Step 3: Create agents/prompts/__init__.py**

```python
"""Prompt builders for investigation agents.

Each prompt module exposes:
- SYSTEM_PROMPT: Static system prompt template
- build_system(**kwargs) -> str: Build system prompt with dynamic values
- build_user(**kwargs) -> str: Build user prompt from context
"""

from . import hypothesis, interpretation, query, reflexion, synthesis

__all__ = [
    "hypothesis",
    "interpretation",
    "query",
    "reflexion",
    "synthesis",
]
```

**Step 4: Commit**

```bash
git add dataing/src/dataing/agents/
git commit -m "feat(agents): create agents package structure"
```

---

## Task 2: Create Prompt Protocol

**Files:**
- Create: `dataing/src/dataing/agents/prompts/protocol.py`

**Step 1: Create the protocol file**

```python
"""Protocol interface for prompt builders.

All prompt modules should follow this interface pattern,
though they don't need to formally implement it.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class PromptBuilder(Protocol):
    """Interface for agent prompt builders.

    Each prompt module should expose:
    - SYSTEM_PROMPT: str - Static system prompt template
    - build_system(**kwargs) -> str - Build system prompt with dynamic values
    - build_user(**kwargs) -> str - Build user prompt from context
    """

    SYSTEM_PROMPT: str

    @staticmethod
    def build_system(**kwargs: object) -> str:
        """Build system prompt, optionally with dynamic values."""
        ...

    @staticmethod
    def build_user(**kwargs: object) -> str:
        """Build user prompt from context."""
        ...
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/agents/prompts/protocol.py
git commit -m "feat(agents): add PromptBuilder protocol"
```

---

## Task 3: Extract Hypothesis Prompts

**Files:**
- Create: `dataing/src/dataing/agents/prompts/hypothesis.py`

**Step 1: Create hypothesis prompt module**

```python
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
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/agents/prompts/hypothesis.py
git commit -m "feat(agents): extract hypothesis prompts"
```

---

## Task 4: Extract Query Prompts

**Files:**
- Create: `dataing/src/dataing/agents/prompts/query.py`

**Step 1: Create query prompt module**

```python
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
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/agents/prompts/query.py
git commit -m "feat(agents): extract query prompts"
```

---

## Task 5: Extract Reflexion Prompts

**Files:**
- Create: `dataing/src/dataing/agents/prompts/reflexion.py`

**Step 1: Create reflexion prompt module**

```python
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
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/agents/prompts/reflexion.py
git commit -m "feat(agents): extract reflexion prompts"
```

---

## Task 6: Extract Interpretation Prompts

**Files:**
- Create: `dataing/src/dataing/agents/prompts/interpretation.py`

**Step 1: Create interpretation prompt module**

```python
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
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/agents/prompts/interpretation.py
git commit -m "feat(agents): extract interpretation prompts"
```

---

## Task 7: Extract Synthesis Prompts

**Files:**
- Create: `dataing/src/dataing/agents/prompts/synthesis.py`

**Step 1: Create synthesis prompt module**

```python
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
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/agents/prompts/synthesis.py
git commit -m "feat(agents): extract synthesis prompts"
```

---

## Task 8: Move Response Models

**Files:**
- Create: `dataing/src/dataing/agents/models.py`
- Reference: `dataing/src/dataing/adapters/llm/response_models.py`

**Step 1: Copy response_models.py to agents/models.py**

```bash
cp dataing/src/dataing/adapters/llm/response_models.py dataing/src/dataing/agents/models.py
```

**Step 2: Update module docstring**

Change the first line of `dataing/src/dataing/agents/models.py` to:

```python
"""Response models for investigation agents.

These models define the exact schema expected from the LLM.
Pydantic AI uses these for:
1. Generating schema hints in the prompt
2. Validating LLM responses
3. Automatic retry on validation failure
"""
```

**Step 3: Commit**

```bash
git add dataing/src/dataing/agents/models.py
git commit -m "feat(agents): move response models to agents package"
```

---

## Task 9: Create AgentClient

**Files:**
- Create: `dataing/src/dataing/agents/client.py`

**Step 1: Create the AgentClient facade**

```python
"""AgentClient - LLM client facade for investigation agents.

Uses BondAgent for type-safe, validated LLM responses with optional streaming.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.output import PromptedOutput
from pydantic_ai.providers.anthropic import AnthropicProvider

from bond import BondAgent, StreamHandlers
from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    InvestigationContext,
)
from dataing.core.exceptions import LLMError

from .models import (
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)
from .prompts import hypothesis, interpretation, query, reflexion, synthesis

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import QueryResult, SchemaResponse


class AgentClient:
    """LLM client facade for investigation agents.

    Uses BondAgent for type-safe, validated LLM responses with optional streaming.
    Prompts are modular and live in the prompts/ package.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
    ) -> None:
        """Initialize the agent client.

        Args:
            api_key: Anthropic API key.
            model: Model to use.
            max_retries: Max retries on validation failure.
        """
        provider = AnthropicProvider(api_key=api_key)
        self._model = AnthropicModel(model, provider=provider)

        # Empty base instructions: all prompting via dynamic_instructions at runtime.
        # This ensures PromptedOutput gets the full detailed prompt without conflicts.
        self._hypothesis_agent: BondAgent[HypothesesResponse, None] = BondAgent(
            name="hypothesis-generator",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(HypothesesResponse),
            max_retries=max_retries,
        )
        self._interpretation_agent: BondAgent[InterpretationResponse, None] = BondAgent(
            name="evidence-interpreter",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(InterpretationResponse),
            max_retries=max_retries,
        )
        self._synthesis_agent: BondAgent[SynthesisResponse, None] = BondAgent(
            name="finding-synthesizer",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(SynthesisResponse),
            max_retries=max_retries,
        )
        self._query_agent: BondAgent[QueryResponse, None] = BondAgent(
            name="sql-generator",
            instructions="",
            model=self._model,
            output_type=PromptedOutput(QueryResponse),
            max_retries=max_retries,
        )

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
        handlers: StreamHandlers | None = None,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate.
            context: Available schema and lineage context.
            num_hypotheses: Target number of hypotheses.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            List of validated Hypothesis objects.

        Raises:
            LLMError: If LLM call fails after retries.
        """
        system_prompt = hypothesis.build_system(num_hypotheses=num_hypotheses)
        user_prompt = hypothesis.build_user(alert=alert, context=context)

        try:
            result = await self._hypothesis_agent.ask(
                user_prompt,
                dynamic_instructions=system_prompt,
                handlers=handlers,
            )

            return [
                Hypothesis(
                    id=h.id,
                    title=h.title,
                    category=h.category,
                    reasoning=h.reasoning,
                    suggested_query=h.suggested_query,
                )
                for h in result.hypotheses
            ]

        except Exception as e:
            raise LLMError(
                f"Hypothesis generation failed: {e}",
                retryable=False,
            ) from e

    async def generate_query(
        self,
        hyp: Hypothesis,
        schema: SchemaResponse,
        previous_error: str | None = None,
        handlers: StreamHandlers | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hyp: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous attempt (for reflexion).
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Validated SQL query string.

        Raises:
            LLMError: If query generation fails.
        """
        if previous_error:
            prompt = reflexion.build_user(hypothesis=hyp, previous_error=previous_error)
            system = reflexion.build_system(schema=schema)
        else:
            prompt = query.build_user(hypothesis=hyp)
            system = query.build_system(schema=schema)

        try:
            result = await self._query_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )
            return result.query

        except Exception as e:
            raise LLMError(
                f"Query generation failed: {e}",
                retryable=True,
            ) from e

    async def interpret_evidence(
        self,
        hyp: Hypothesis,
        sql: str,
        results: QueryResult,
        handlers: StreamHandlers | None = None,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hyp: The hypothesis being tested.
            sql: The query that was executed.
            results: The query results.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Evidence with validated interpretation.
        """
        prompt = interpretation.build_user(hypothesis=hyp, query=sql, results=results)
        system = interpretation.build_system()

        try:
            result = await self._interpretation_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )

            return Evidence(
                hypothesis_id=hyp.id,
                query=sql,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=result.supports_hypothesis,
                confidence=result.confidence,
                interpretation=result.interpretation,
            )

        except Exception as e:
            # Return low-confidence evidence on failure rather than crashing
            return Evidence(
                hypothesis_id=hyp.id,
                query=sql,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=None,
                confidence=0.3,
                interpretation=f"Interpretation failed: {e}",
            )

    async def synthesize_findings(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
        handlers: StreamHandlers | None = None,
    ) -> Finding:
        """Synthesize all evidence into a root cause finding.

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Finding with validated root cause and recommendations.

        Raises:
            LLMError: If synthesis fails.
        """
        prompt = synthesis.build_user(alert=alert, evidence=evidence)
        system = synthesis.build_system()

        try:
            result = await self._synthesis_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )

            return Finding(
                investigation_id="",  # Set by orchestrator
                status="completed" if result.root_cause else "inconclusive",
                root_cause=result.root_cause,
                confidence=result.confidence,
                evidence=evidence,
                recommendations=result.recommendations,
                duration_seconds=0.0,  # Set by orchestrator
            )

        except Exception as e:
            raise LLMError(
                f"Synthesis failed: {e}",
                retryable=False,
            ) from e
```

**Step 2: Commit**

```bash
git add dataing/src/dataing/agents/client.py
git commit -m "feat(agents): create AgentClient facade"
```

---

## Task 10: Update Imports Across Codebase

**Files:**
- Modify: `dataing/src/dataing/core/orchestrator.py`
- Modify: `dataing/src/dataing/core/quality/judge.py`
- Modify: `dataing/src/dataing/core/quality/protocol.py`
- Modify: `dataing/src/dataing/entrypoints/api/deps.py`
- Modify: `dataing/src/dataing/entrypoints/mcp/server.py`
- Modify: `dataing/src/dataing/adapters/__init__.py`
- Modify: `dataing-ee/src/dataing_ee/entrypoints/api/app.py`

**Step 1: Update orchestrator.py**

Change line 25:
```python
# Before
from dataing.adapters.llm.response_models import InterpretationResponse, SynthesisResponse

# After
from dataing.agents.models import InterpretationResponse, SynthesisResponse
```

**Step 2: Update quality/judge.py**

Change lines 14-17:
```python
# Before
if TYPE_CHECKING:
    from dataing.adapters.llm.response_models import (
        InterpretationResponse,
        SynthesisResponse,
    )

# After
if TYPE_CHECKING:
    from dataing.agents.models import (
        InterpretationResponse,
        SynthesisResponse,
    )
```

**Step 3: Update quality/protocol.py**

Find and update any imports from `dataing.adapters.llm.response_models` to `dataing.agents.models`.

**Step 4: Update entrypoints/api/deps.py**

Change line 26:
```python
# Before
from dataing.adapters.llm.client import AnthropicClient

# After
from dataing.agents import AgentClient
```

Also update the usage of `AnthropicClient` to `AgentClient` throughout the file.

**Step 5: Update entrypoints/mcp/server.py**

Change line 24:
```python
# Before
from dataing.adapters.llm.client import AnthropicClient

# After
from dataing.agents import AgentClient
```

Also update the type hint on line 34:
```python
# Before
def create_server(db: SQLAdapter, llm: AnthropicClient) -> Server:

# After
def create_server(db: SQLAdapter, llm: AgentClient) -> Server:
```

**Step 6: Update adapters/__init__.py**

Remove the AnthropicClient import and export:
```python
# Remove line 21
from .llm.client import AnthropicClient

# Remove from __all__
"AnthropicClient",
```

**Step 7: Update dataing-ee/entrypoints/api/app.py**

Find and update any imports from `dataing.adapters.llm` to `dataing.agents`.

**Step 8: Commit**

```bash
git add dataing/src/dataing/core/orchestrator.py \
        dataing/src/dataing/core/quality/judge.py \
        dataing/src/dataing/core/quality/protocol.py \
        dataing/src/dataing/entrypoints/api/deps.py \
        dataing/src/dataing/entrypoints/mcp/server.py \
        dataing/src/dataing/adapters/__init__.py \
        dataing-ee/src/dataing_ee/entrypoints/api/app.py
git commit -m "refactor: update imports to use agents package"
```

---

## Task 11: Move and Update Tests

**Files:**
- Create: `dataing/tests/unit/agents/__init__.py`
- Move: `dataing/tests/unit/adapters/llm/test_response_models.py` → `dataing/tests/unit/agents/test_models.py`
- Delete: `tests/unit/adapters/llm/` (outdated tests)

**Step 1: Create test directory**

```bash
mkdir -p dataing/tests/unit/agents
touch dataing/tests/unit/agents/__init__.py
```

**Step 2: Move and rename test file**

```bash
mv dataing/tests/unit/adapters/llm/test_response_models.py dataing/tests/unit/agents/test_models.py
```

**Step 3: Update imports in test_models.py**

Change line 4-8:
```python
# Before
from dataing.adapters.llm.response_models import (
    HypothesisResponse,
    InterpretationResponse,
    SynthesisResponse,
)

# After
from dataing.agents.models import (
    HypothesisResponse,
    InterpretationResponse,
    SynthesisResponse,
)
```

**Step 4: Remove outdated test directory**

The tests in `tests/unit/adapters/llm/` are testing an old implementation with methods like `_parse_hypotheses` that no longer exist. Delete them:

```bash
rm -rf tests/unit/adapters/llm/
```

**Step 5: Clean up empty directories**

```bash
rmdir dataing/tests/unit/adapters/llm 2>/dev/null || true
```

**Step 6: Commit**

```bash
git add dataing/tests/unit/agents/
git rm -rf tests/unit/adapters/llm/
git rm -rf dataing/tests/unit/adapters/llm/
git commit -m "test: move response model tests to agents package"
```

---

## Task 12: Remove Old LLM Adapter

**Files:**
- Delete: `dataing/src/dataing/adapters/llm/client.py`
- Delete: `dataing/src/dataing/adapters/llm/response_models.py`
- Delete: `dataing/src/dataing/adapters/llm/__init__.py`
- Delete: `dataing/src/dataing/adapters/llm/` directory

**Step 1: Remove the old adapter files**

```bash
rm -rf dataing/src/dataing/adapters/llm/
```

**Step 2: Commit**

```bash
git rm -rf dataing/src/dataing/adapters/llm/
git commit -m "refactor: remove old llm adapter (moved to agents)"
```

---

## Task 13: Run Tests and Verify

**Step 1: Run linting**

```bash
cd dataing && uv run ruff check src/dataing/agents/
cd dataing && uv run ruff format src/dataing/agents/
```

**Step 2: Run type checking**

```bash
cd dataing && uv run mypy src/dataing/agents/
```

**Step 3: Run unit tests**

```bash
cd dataing && uv run pytest tests/unit/agents/ -v
```

**Step 4: Run full test suite**

```bash
just test-backend
```

**Step 5: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: resolve linting and type errors"
```

---

## Task 14: Final Commit and Summary

**Step 1: Verify no broken imports**

```bash
cd dataing && uv run python -c "from dataing.agents import AgentClient; print('OK')"
```

**Step 2: Squash or leave as feature branch**

If all tests pass, the refactor is complete. The agents package is now:

```
dataing/src/dataing/agents/
├── __init__.py           # Exports AgentClient, models
├── client.py             # AgentClient facade
├── models.py             # Response models
└── prompts/
    ├── __init__.py       # Exports all prompt modules
    ├── protocol.py       # PromptBuilder protocol
    ├── hypothesis.py     # Hypothesis generation prompts
    ├── query.py          # Query generation prompts
    ├── reflexion.py      # Query correction prompts
    ├── interpretation.py # Evidence interpretation prompts
    └── synthesis.py      # Finding synthesis prompts
```
