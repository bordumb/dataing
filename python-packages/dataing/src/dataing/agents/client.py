"""AgentClient - LLM client facade for investigation agents.

Uses BondAgent for type-safe, validated LLM responses with optional streaming.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from bond import BondAgent, StreamHandlers
from pydantic import BaseModel
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.output import PromptedOutput
from pydantic_ai.providers.anthropic import AnthropicProvider

from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    InvestigationContext,
    RelevantCodeChange,
)
from dataing.core.exceptions import LLMError

from .models import (
    CounterAnalysisResponse,
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)

# Re-export for type hints in adapters
__all__ = ["AgentClient", "SynthesisResponse"]
from .prompts import counter_analysis, hypothesis, interpretation, query, reflexion, synthesis

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import QueryResult, SchemaResponse

OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentClient:
    """LLM client facade for investigation agents.

    Uses BondAgent for type-safe, validated LLM responses with optional streaming.
    Prompts are modular and live in the prompts/ package.

    One instance serves every investigation in a process, across tenants, so every
    LLM call runs on a fresh BondAgent and starts from an empty message history.
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
        self._max_retries = max_retries

    async def _ask(
        self,
        name: str,
        output_type: type[OutputT],
        prompt: str,
        *,
        instructions: str,
        handlers: StreamHandlers | None = None,
    ) -> OutputT:
        """Run one LLM call on a fresh BondAgent.

        BondAgent keeps every message it has seen and replays them on each ask().
        Never hold a BondAgent across calls: its history would carry one
        investigation's schemas, alerts and query rows into the next prompt.

        Args:
            name: Agent name.
            output_type: Response model the LLM output is validated against.
            prompt: User prompt.
            instructions: System prompt for this call.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            The validated response.
        """
        # Empty base instructions: all prompting via dynamic_instructions at runtime.
        # This ensures PromptedOutput gets the full detailed prompt without conflicts.
        agent: BondAgent[OutputT, None] = BondAgent(
            name=name,
            instructions="",
            model=self._model,
            output_type=PromptedOutput(output_type),
            max_retries=self._max_retries,
        )
        result: OutputT = await agent.ask(
            prompt,
            dynamic_instructions=instructions,
            handlers=handlers,
        )
        return result

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
        handlers: StreamHandlers | None = None,
        code_changes: list[RelevantCodeChange] | None = None,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate.
            context: Available schema and lineage context.
            num_hypotheses: Target number of hypotheses.
            handlers: Optional streaming handlers for real-time updates.
            code_changes: Optional list of recent code changes affecting the asset.

        Returns:
            List of validated Hypothesis objects.

        Raises:
            LLMError: If LLM call fails after retries.
        """
        system_prompt = hypothesis.build_system(num_hypotheses=num_hypotheses)
        user_prompt = hypothesis.build_user(alert=alert, context=context, code_changes=code_changes)

        try:
            result = await self._ask(
                "hypothesis-generator",
                HypothesesResponse,
                user_prompt,
                instructions=system_prompt,
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
        alert: AnomalyAlert | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous attempt (for reflexion).
            handlers: Optional streaming handlers for real-time updates.
            alert: The anomaly alert being investigated (for date/context).

        Returns:
            Validated SQL query string.

        Raises:
            LLMError: If query generation fails.
        """
        if previous_error:
            prompt = reflexion.build_user(hypothesis=hypothesis, previous_error=previous_error)
            system = reflexion.build_system(schema=schema)
        else:
            prompt = query.build_user(hypothesis=hypothesis, alert=alert)
            system = query.build_system(schema=schema, alert=alert)

        try:
            result = await self._ask(
                "sql-generator",
                QueryResponse,
                prompt,
                instructions=system,
                handlers=handlers,
            )
            sql_query: str = result.query
            return sql_query

        except Exception as e:
            raise LLMError(
                f"Query generation failed: {e}",
                retryable=True,
            ) from e

    async def interpret_evidence(
        self,
        hypothesis: Hypothesis,
        sql: str,
        results: QueryResult,
        handlers: StreamHandlers | None = None,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested.
            sql: The query that was executed.
            results: The query results.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            Evidence with validated interpretation.
        """
        prompt = interpretation.build_user(hypothesis=hypothesis, query=sql, results=results)
        system = interpretation.build_system()

        try:
            result = await self._ask(
                "evidence-interpreter",
                InterpretationResponse,
                prompt,
                instructions=system,
                handlers=handlers,
            )

            return Evidence(
                hypothesis_id=hypothesis.id,
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
                hypothesis_id=hypothesis.id,
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
        result = await self.synthesize_findings_raw(alert, evidence, handlers)

        return Finding(
            investigation_id="",  # Set by orchestrator
            status="completed" if result.root_cause else "inconclusive",
            root_cause=result.root_cause,
            confidence=result.confidence,
            evidence=evidence,
            recommendations=result.recommendations,
            duration_seconds=0.0,  # Set by orchestrator
        )

    async def synthesize_findings_raw(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
        handlers: StreamHandlers | None = None,
        code_changes: list[RelevantCodeChange] | None = None,
    ) -> SynthesisResponse:
        """Synthesize all evidence into a root cause finding (raw response).

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.
            handlers: Optional streaming handlers for real-time updates.
            code_changes: Optional list of code changes related to the investigation.

        Returns:
            Raw SynthesisResponse with all fields from LLM.

        Raises:
            LLMError: If synthesis fails.
        """
        prompt = synthesis.build_user(alert=alert, evidence=evidence, code_changes=code_changes)
        system = synthesis.build_system()

        try:
            return await self._ask(
                "finding-synthesizer",
                SynthesisResponse,
                prompt,
                instructions=system,
                handlers=handlers,
            )

        except Exception as e:
            raise LLMError(
                f"Synthesis failed: {e}",
                retryable=False,
            ) from e

    async def counter_analyze(
        self,
        *,
        synthesis: dict[str, Any],
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Perform counter-analysis on synthesis conclusion.

        Args:
            synthesis: The current synthesis/conclusion.
            evidence: All collected evidence.
            hypotheses: The hypotheses that were tested.

        Returns:
            Counter-analysis result as dict.
        """
        prompt = counter_analysis.build_user(
            synthesis=synthesis,
            evidence=evidence,
            hypotheses=hypotheses,
        )
        system = counter_analysis.build_system()

        try:
            result = await self._ask(
                "counter-analyst",
                CounterAnalysisResponse,
                prompt,
                instructions=system,
            )
            return {
                "alternative_explanations": result.alternative_explanations,
                "weaknesses": result.weaknesses,
                "confidence_adjustment": result.confidence_adjustment,
                "recommendation": result.recommendation,
            }

        except Exception as e:
            raise LLMError(
                f"Counter-analysis failed: {e}",
                retryable=False,
            ) from e
