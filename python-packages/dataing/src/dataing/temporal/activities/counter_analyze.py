"""Counter analyze activity for investigation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from temporalio import activity

from dataing.agents.errors import classify_llm_error
from dataing.temporal.errors import llm_activity_error

if TYPE_CHECKING:
    from dataing.temporal.adapters import TemporalAgentAdapter


@dataclass
class CounterAnalyzeInput:
    """Input for counter_analyze activity."""

    investigation_id: str
    synthesis: dict[str, Any]
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]


@dataclass
class CounterAnalyzeResult:
    """Result from counter_analyze activity."""

    alternative_explanations: list[str]
    weaknesses: list[str]
    confidence_adjustment: float
    recommendation: str
    error: str | None = None


def make_counter_analyze_activity(adapter: TemporalAgentAdapter) -> Any:
    """Factory that creates counter_analyze activity with injected adapter.

    Args:
        adapter: TemporalAgentAdapter for LLM operations.

    Returns:
        The counter_analyze activity function.
    """

    @activity.defn
    async def counter_analyze(input: CounterAnalyzeInput) -> CounterAnalyzeResult:
        """Perform counter-analysis on current synthesis."""
        try:
            result = await adapter.counter_analyze(
                synthesis=input.synthesis,
                evidence=input.evidence,
                hypotheses=input.hypotheses,
            )
        except Exception as e:
            failure = classify_llm_error(e)
            if failure is not None:
                raise llm_activity_error(failure) from e
            return CounterAnalyzeResult(
                alternative_explanations=[],
                weaknesses=[],
                confidence_adjustment=0.0,
                recommendation="accept",
                error=f"Counter-analysis failed: {e}",
            )

        return CounterAnalyzeResult(
            alternative_explanations=result.get("alternative_explanations", []),
            weaknesses=result.get("weaknesses", []),
            confidence_adjustment=result.get("confidence_adjustment", 0.0),
            recommendation=result.get("recommendation", "accept"),
        )

    return counter_analyze
