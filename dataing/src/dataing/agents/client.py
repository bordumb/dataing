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
