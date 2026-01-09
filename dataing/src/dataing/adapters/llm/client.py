"""Anthropic Claude implementation with BondAgent structured outputs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.output import PromptedOutput

from bond import BondAgent, StreamHandlers
from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    InvestigationContext,
)
from dataing.core.exceptions import LLMError

from .response_models import (
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import QueryResult, SchemaResponse


class AnthropicClient:
    """Anthropic Claude implementation with streaming support.

    Uses BondAgent for type-safe, validated LLM responses with optional streaming.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
    ) -> None:
        """Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model to use.
            max_retries: Max retries on validation failure.
        """
        os.environ["ANTHROPIC_API_KEY"] = api_key
        self._model = AnthropicModel(model)

        self._hypothesis_agent: BondAgent[HypothesesResponse, None] = BondAgent(
            name="hypothesis-generator",
            instructions="You are a data quality investigator.",
            model=self._model,
            output_type=PromptedOutput(HypothesesResponse),
            max_retries=max_retries,
        )
        self._interpretation_agent: BondAgent[InterpretationResponse, None] = BondAgent(
            name="evidence-interpreter",
            instructions="You analyze query results for evidence.",
            model=self._model,
            output_type=PromptedOutput(InterpretationResponse),
            max_retries=max_retries,
        )
        self._synthesis_agent: BondAgent[SynthesisResponse, None] = BondAgent(
            name="finding-synthesizer",
            instructions="You synthesize investigation findings.",
            model=self._model,
            output_type=PromptedOutput(SynthesisResponse),
            max_retries=max_retries,
        )
        self._query_agent: BondAgent[QueryResponse, None] = BondAgent(
            name="sql-generator",
            instructions="You are a SQL expert.",
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
        system_prompt = self._build_hypothesis_system_prompt(num_hypotheses)
        user_prompt = self._build_hypothesis_user_prompt(alert, context)

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
        hypothesis: Hypothesis,
        schema: SchemaResponse,
        previous_error: str | None = None,
        handlers: StreamHandlers | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous attempt (for reflexion).
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Validated SQL query string.

        Raises:
            LLMError: If query generation fails.
        """
        if previous_error:
            prompt = self._build_reflexion_prompt(hypothesis, previous_error)
            system = self._build_reflexion_system_prompt(schema)
        else:
            prompt = self._build_query_prompt(hypothesis)
            system = self._build_query_system_prompt(schema)

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
        hypothesis: Hypothesis,
        query: str,
        results: QueryResult,
        handlers: StreamHandlers | None = None,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested.
            query: The query that was executed.
            results: The query results.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Evidence with validated interpretation.
        """
        prompt = self._build_interpretation_prompt(hypothesis, query, results)
        system = self._build_interpretation_system_prompt()

        try:
            result = await self._interpretation_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )

            return Evidence(
                hypothesis_id=hypothesis.id,
                query=query,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=result.supports_hypothesis,
                confidence=result.confidence,
                interpretation=result.interpretation,
            )

        except Exception as e:
            # Return low-confidence evidence on failure rather than crashing
            return Evidence(
                hypothesis_id=hypothesis.id,
                query=query,
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
        prompt = self._build_synthesis_prompt(alert, evidence)
        system = self._build_synthesis_system_prompt()

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

    # -------------------------------------------------------------------------
    # Prompt Building Methods
    # -------------------------------------------------------------------------

    def _build_metric_context(self, alert: AnomalyAlert) -> str:
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

    def _build_hypothesis_system_prompt(self, num_hypotheses: int) -> str:
        """Build system prompt for hypothesis generation."""
        return f"""You are a data quality investigator. Given an anomaly alert and database context,
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

Generate diverse hypotheses covering multiple categories when plausible."""

    def _build_hypothesis_user_prompt(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
    ) -> str:
        """Build user prompt for hypothesis generation."""
        lineage_section = ""
        if context.lineage:
            lineage_section = f"""
## Data Lineage
{context.lineage.to_prompt_string()}
"""

        # Build structured context based on metric type
        metric_context = self._build_metric_context(alert)

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

    def _build_query_system_prompt(self, schema: SchemaResponse) -> str:
        """Build system prompt for query generation."""
        return f"""You are a SQL expert generating investigative queries.

CRITICAL RULES:
1. Use ONLY tables from the schema: {schema.get_table_names()}
2. Use ONLY columns that exist in those tables
3. SELECT queries ONLY - no mutations
4. Always include LIMIT clause (max 10000)
5. Use fully qualified table names (schema.table)

SCHEMA:
{schema.to_prompt_string()}"""

    def _build_query_prompt(self, hypothesis: Hypothesis) -> str:
        """Build user prompt for query generation."""
        return f"""Generate a SQL query to test this hypothesis:

Hypothesis: {hypothesis.title}
Category: {hypothesis.category.value}
Reasoning: {hypothesis.reasoning}

Generate a query that would confirm or refute this hypothesis."""

    def _build_reflexion_system_prompt(self, schema: SchemaResponse) -> str:
        """Build system prompt for reflexion (query correction)."""
        return f"""You are debugging a failed SQL query. Analyze the error and fix the query.

AVAILABLE SCHEMA:
{schema.to_prompt_string()}

COMMON FIXES:
- "column does not exist": Check column name spelling, use correct table
- "relation does not exist": Use fully qualified name (schema.table)
- "type mismatch": Cast values appropriately
- "syntax error": Check SQL syntax for the target database

CRITICAL: Only use tables and columns from the schema above."""

    def _build_reflexion_prompt(
        self,
        hypothesis: Hypothesis,
        previous_error: str,
    ) -> str:
        """Build user prompt for reflexion."""
        return f"""The previous query failed. Generate a corrected version.

ORIGINAL QUERY:
{hypothesis.suggested_query}

ERROR MESSAGE:
{previous_error}

HYPOTHESIS BEING TESTED:
{hypothesis.title}

Generate a corrected SQL query that avoids this error."""

    def _build_interpretation_system_prompt(self) -> str:
        """Build system prompt for evidence interpretation."""
        return """You are analyzing query results to determine if they support a hypothesis.

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

    def _build_interpretation_prompt(
        self,
        hypothesis: Hypothesis,
        query: str,
        results: QueryResult,
    ) -> str:
        """Build user prompt for interpretation."""
        return f"""HYPOTHESIS: {hypothesis.title}
REASONING: {hypothesis.reasoning}

QUERY EXECUTED:
{query}

RESULTS ({results.row_count} rows):
{results.to_summary()}

Analyze whether these results support or refute the hypothesis."""

    def _build_synthesis_system_prompt(self) -> str:
        """Build system prompt for synthesis."""
        return """You are synthesizing investigation findings to determine root cause.

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

    def _build_synthesis_prompt(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
    ) -> str:
        """Build user prompt for synthesis."""
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

        # Include metric context for synthesis
        metric_context = self._build_metric_context(alert)

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
