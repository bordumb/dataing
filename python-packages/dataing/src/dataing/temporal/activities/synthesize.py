"""Synthesize findings activity for investigation workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from temporalio import activity

if TYPE_CHECKING:
    from dataing.temporal.adapters import TemporalAgentAdapter


@dataclass
class SynthesizeInput:
    """Input for synthesize activity."""

    investigation_id: str
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    alert_summary: str
    confidence_threshold: float = 0.85
    code_changes: list[dict[str, Any]] | None = None
    # Hypotheses whose evaluation failed: {"hypothesis_id", "title", "error"}
    untested_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    # The alert, whose metadata carries the team brief and steering notes
    alert: dict[str, Any] | None = None
    # Hypotheses a person ruled out: {"hypothesis_id", "title", "reason"}
    ruled_out_hypotheses: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SynthesizeResult:
    """Result from synthesize activity."""

    root_cause: str | None  # None when the LLM finds the investigation inconclusive
    confidence: float
    recommendations: list[str]
    supporting_evidence: list[str]
    needs_counter_analysis: bool
    error: str | None = None


def make_synthesize_activity(
    adapter: TemporalAgentAdapter,
    confidence_threshold: float = 0.85,
) -> Any:
    """Factory that creates synthesize activity with injected adapter.

    Args:
        adapter: TemporalAgentAdapter for LLM operations.
        confidence_threshold: Minimum confidence to skip counter-analysis.

    Returns:
        The synthesize activity function.
    """

    @activity.defn
    async def synthesize(input: SynthesizeInput) -> SynthesizeResult:
        """Synthesize evidence into root cause finding."""
        try:
            synthesis = await adapter.synthesize_findings_for_temporal(
                evidence=input.evidence,
                hypotheses=input.hypotheses,
                alert_summary=input.alert_summary,
                untested_hypotheses=input.untested_hypotheses,
                code_changes=input.code_changes,
                alert=input.alert,
                ruled_out_hypotheses=input.ruled_out_hypotheses,
            )
        except Exception as e:
            return SynthesizeResult(
                root_cause="",
                confidence=0.0,
                recommendations=[],
                supporting_evidence=[],
                needs_counter_analysis=False,
                error=f"Synthesis failed: {e}",
            )

        confidence = synthesis.get("confidence", 0.0)
        threshold = input.confidence_threshold or confidence_threshold
        needs_counter_analysis = confidence < threshold

        return SynthesizeResult(
            root_cause=synthesis.get("root_cause", ""),
            confidence=confidence,
            recommendations=synthesis.get("recommendations", []),
            supporting_evidence=synthesis.get("supporting_evidence", []),
            needs_counter_analysis=needs_counter_analysis,
        )

    return synthesize
