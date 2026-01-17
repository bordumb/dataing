"""Interpret evidence activity for investigation workflow.

Extracts business logic from InterpretEvidenceStep into a Temporal activity factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from temporalio import activity


class LLMProtocol(Protocol):
    """Protocol for LLM client used by interpret_evidence activity."""

    async def interpret_evidence(
        self,
        *,
        hypothesis: dict[str, Any],
        query_result: dict[str, Any],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Interpret query result as evidence for/against hypothesis.

        Returns:
            Evidence dict with:
            - supports_hypothesis: bool
            - confidence: float (0.0 to 1.0)
            - interpretation: str - Human-readable explanation
            - key_findings: list[str] - Bullet points of findings
        """
        ...


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


def make_interpret_evidence_activity(llm: LLMProtocol) -> Any:
    """Factory that creates interpret_evidence activity with injected dependencies.

    Args:
        llm: LLM client for interpreting evidence.

    Returns:
        The interpret_evidence activity function.
    """

    @activity.defn
    async def interpret_evidence(input: InterpretEvidenceInput) -> InterpretEvidenceResult:
        """Interpret query result as evidence for/against hypothesis.

        This activity:
        1. Receives hypothesis and query result
        2. Calls LLM to interpret the evidence
        3. Returns structured evidence interpretation
        """
        hypothesis_id = input.hypothesis.get("id", "unknown")

        try:
            evidence = await llm.interpret_evidence(
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


# Standalone activity for POC/testing (returns mock interpretation)
@activity.defn
async def interpret_evidence(
    investigation_id: str,
    hypothesis: dict[str, Any],
    query_result: dict[str, Any],
) -> dict[str, Any]:
    """POC interpret_evidence activity with mock result.

    Used for testing without real dependencies. Production code should use
    make_interpret_evidence_activity() factory instead.
    """
    hypothesis_id = hypothesis.get("id", "unknown")
    return {
        "hypothesis_id": hypothesis_id,
        "supports_hypothesis": True,
        "confidence": 0.75,
        "interpretation": "Query results support the hypothesis.",
        "key_findings": ["Found 42 matching records", "Pattern matches expected anomaly"],
    }
