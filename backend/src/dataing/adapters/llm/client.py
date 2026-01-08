"""Anthropic Claude implementation with Pydantic AI structured outputs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.output import PromptedOutput

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
    """Anthropic Claude implementation with structured outputs.

    Uses Pydantic AI for type-safe, validated LLM responses.
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
        # Pydantic AI reads API key from environment variable
        os.environ["ANTHROPIC_API_KEY"] = api_key
        self._model = AnthropicModel(model)

        # Pre-configure agents for each task
        # Using PromptedOutput mode enables chain-of-thought reasoning before structured output,
        # which significantly improves quality for complex analytical tasks compared to tool mode.
        self._hypothesis_agent: Agent[None, HypothesesResponse] = Agent(
            model=self._model,
            output_type=PromptedOutput(HypothesesResponse),
            retries=max_retries,
        )
        self._interpretation_agent: Agent[None, InterpretationResponse] = Agent(
            model=self._model,
            output_type=PromptedOutput(InterpretationResponse),
            retries=max_retries,
        )
        self._synthesis_agent: Agent[None, SynthesisResponse] = Agent(
            model=self._model,
            output_type=PromptedOutput(SynthesisResponse),
            retries=max_retries,
        )
        self._query_agent: Agent[None, QueryResponse] = Agent(
            model=self._model,
            output_type=PromptedOutput(QueryResponse),
            retries=max_retries,
        )

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate.
            context: Available schema and lineage context.
            num_hypotheses: Target number of hypotheses.

        Returns:
            List of validated Hypothesis objects.

        Raises:
            LLMError: If LLM call fails after retries.
        """
        system_prompt = self._build_hypothesis_system_prompt(num_hypotheses)
        user_prompt = self._build_hypothesis_user_prompt(alert, context)

        try:
            result = await self._hypothesis_agent.run(
                user_prompt,
                instructions=system_prompt,
            )

            return [
                Hypothesis(
                    id=h.id,
                    title=h.title,
                    category=h.category,
                    reasoning=h.reasoning,
                    suggested_query=h.suggested_query,
                )
                for h in result.output.hypotheses
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
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous attempt (for reflexion).

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
            result = await self._query_agent.run(
                prompt,
                instructions=system,
            )
            query: str = result.output.query
            return query

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
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested.
            query: The query that was executed.
            results: The query results.

        Returns:
            Evidence with validated interpretation.
        """
        prompt = self._build_interpretation_prompt(hypothesis, query, results)
        system = self._build_interpretation_system_prompt()

        try:
            result = await self._interpretation_agent.run(
                prompt,
                instructions=system,
            )

            return Evidence(
                hypothesis_id=hypothesis.id,
                query=query,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=result.output.supports_hypothesis,
                confidence=result.output.confidence,
                interpretation=result.output.interpretation,
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
    ) -> Finding:
        """Synthesize all evidence into a root cause finding.

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.

        Returns:
            Finding with validated root cause and recommendations.

        Raises:
            LLMError: If synthesis fails.
        """
        prompt = self._build_synthesis_prompt(alert, evidence)
        system = self._build_synthesis_system_prompt()

        try:
            result = await self._synthesis_agent.run(
                prompt,
                instructions=system,
            )

            return Finding(
                investigation_id="",  # Set by orchestrator
                status="completed" if result.output.root_cause else "inconclusive",
                root_cause=result.output.root_cause,
                confidence=result.output.confidence,
                evidence=evidence,
                recommendations=result.output.recommendations,
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

Example: Investigating "null_count spike in user_id"
- Query finds 485 rows with NULL user_id -> supports=true (this IS the problem we're investigating)
- Query finds 0 rows with NULL user_id -> supports=false (not the cause)

REQUIRED FIELDS:
1. supports_hypothesis: True if evidence supports, False if refutes, None if inconclusive
2. confidence: Score from 0.0 to 1.0
3. interpretation: What the results reveal about the ROOT CAUSE, not just the symptom
   - BAD: "Found 485 NULL user_ids" (just describes symptom)
   - GOOD: "485 NULL user_ids appearing after 03:14 UTC suggests upstream users ETL stopped"
4. causal_chain: The cause-and-effect explanation connecting upstream cause to observation
   - REQUIRED: Explain WHAT upstream change led to this observation
   - Example: "users ETL stopped at 03:14 -> stale users table -> orders JOIN produces NULLs"
   - NOT: "NULL values found" (this is just restating the symptom)
5. key_findings: Specific findings with data points (counts, timestamps, table names)
6. next_investigation_step: If inconclusive, what query or check would determine root cause?
   - Example: "Query logs table for users ETL job status between 03:00-04:00 UTC"
   - Only needed when supports_hypothesis is None

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
