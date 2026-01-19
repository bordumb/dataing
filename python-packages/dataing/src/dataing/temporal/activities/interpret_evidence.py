"""Interpret evidence activity for investigation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from temporalio import activity

if TYPE_CHECKING:
    from dataing.temporal.adapters import TemporalAgentAdapter


@dataclass
class InterpretEvidenceInput:
    """Input for interpret_evidence activity."""

    investigation_id: str
    hypothesis: dict[str, Any]
    query_result: dict[str, Any]
    alert_summary: str


@dataclass
class InterpretEvidenceResult:
    """Result from interpret_evidence activity."""

    hypothesis_id: str
    supports_hypothesis: bool
    confidence: float
    interpretation: str
    key_findings: list[str]
    error: str | None = None


def make_interpret_evidence_activity(adapter: TemporalAgentAdapter) -> Any:
    """Factory that creates interpret_evidence activity with injected adapter.

    Args:
        adapter: TemporalAgentAdapter for LLM operations.

    Returns:
        The interpret_evidence activity function.
    """

    @activity.defn
    async def interpret_evidence(input: InterpretEvidenceInput) -> InterpretEvidenceResult:
        """Interpret query result as evidence for/against hypothesis."""
        hypothesis_id = input.hypothesis.get("id", "unknown")

        try:
            evidence = await adapter.interpret_evidence(
                hypothesis=input.hypothesis,
                query_result=input.query_result,
                alert_summary=input.alert_summary,
            )
        except Exception as e:
            return InterpretEvidenceResult(
                hypothesis_id=hypothesis_id,
                supports_hypothesis=False,
                confidence=0.0,
                interpretation="",
                key_findings=[],
                error=f"Evidence interpretation failed: {e}",
            )

        return InterpretEvidenceResult(
            hypothesis_id=hypothesis_id,
            supports_hypothesis=evidence.get("supports_hypothesis", False),
            confidence=evidence.get("confidence", 0.0),
            interpretation=evidence.get("interpretation", ""),
            key_findings=evidence.get("key_findings", []),
        )

    return interpret_evidence
