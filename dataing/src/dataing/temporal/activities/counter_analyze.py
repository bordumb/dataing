"""Counter analyze activity for investigation workflow.

Extracts business logic from CounterAnalyzeStep into a Temporal activity factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from temporalio import activity


class LLMProtocol(Protocol):
    """Protocol for LLM client used by counter_analyze activity."""

    async def counter_analyze(
        self,
        *,
        synthesis: dict[str, Any],
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Perform counter-analysis on current synthesis.

        Returns:
            Counter-analysis dict with:
            - alternative_explanations: list[str]
            - weaknesses: list[str]
            - confidence_adjustment: float (-0.5 to 0.5)
            - recommendation: str - "accept", "investigate_more", or "reject"
        """
        ...


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


def make_counter_analyze_activity(llm: LLMProtocol) -> Any:
    """Factory that creates counter_analyze activity with injected dependencies.

    Args:
        llm: LLM client for counter-analysis.

    Returns:
        The counter_analyze activity function.
    """

    @activity.defn
    async def counter_analyze(input: CounterAnalyzeInput) -> CounterAnalyzeResult:
        """Perform counter-analysis on current synthesis.

        This activity:
        1. Receives synthesis, evidence, and hypotheses
        2. Calls LLM to find alternative explanations and weaknesses
        3. Returns recommendation for next steps
        """
        try:
            result = await llm.counter_analyze(
                synthesis=input.synthesis,
                evidence=input.evidence,
                hypotheses=input.hypotheses,
            )
        except Exception as e:
            return CounterAnalyzeResult(
                alternative_explanations=[],
                weaknesses=[],
                confidence_adjustment=0.0,
                recommendation="accept",  # Default to accept on error
                error=f"Counter-analysis failed: {e}",
            )

        return CounterAnalyzeResult(
            alternative_explanations=result.get("alternative_explanations", []),
            weaknesses=result.get("weaknesses", []),
            confidence_adjustment=result.get("confidence_adjustment", 0.0),
            recommendation=result.get("recommendation", "accept"),
        )

    return counter_analyze


# Standalone activity for POC/testing (returns mock result)
@activity.defn
async def counter_analyze(
    investigation_id: str,
    synthesis: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """POC counter_analyze activity with mock result.

    Used for testing without real dependencies. Production code should use
    make_counter_analyze_activity() factory instead.
    """
    return {
        "alternative_explanations": ["Could be a data pipeline issue"],
        "weaknesses": ["Limited sample size"],
        "confidence_adjustment": -0.1,
        "recommendation": "accept",
    }
