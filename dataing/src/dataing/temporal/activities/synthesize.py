"""Synthesize findings activity for investigation workflow.

Extracts business logic from SynthesizeStep into a Temporal activity factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from temporalio import activity


class LLMProtocol(Protocol):
    """Protocol for LLM client used by synthesize activity."""

    async def synthesize_findings(
        self,
        *,
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Synthesize evidence into root cause finding.

        Returns:
            Synthesis dict with:
            - root_cause: str
            - confidence: float (0.0 to 1.0)
            - recommendations: list[str]
            - supporting_evidence: list[str]
        """
        ...


@dataclass
class SynthesizeInput:
    """Input for synthesize activity."""

    investigation_id: str
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    alert_summary: str
    confidence_threshold: float = 0.85


@dataclass
class SynthesizeResult:
    """Result from synthesize activity."""

    root_cause: str
    confidence: float
    recommendations: list[str]
    supporting_evidence: list[str]
    needs_counter_analysis: bool
    error: str | None = None


def make_synthesize_activity(
    llm: LLMProtocol,
    confidence_threshold: float = 0.85,
) -> Any:
    """Factory that creates synthesize activity with injected dependencies.

    Args:
        llm: LLM client for synthesizing findings.
        confidence_threshold: Minimum confidence to skip counter-analysis.

    Returns:
        The synthesize activity function.
    """

    @activity.defn
    async def synthesize(input: SynthesizeInput) -> SynthesizeResult:
        """Synthesize evidence from hypothesis investigations into root cause finding.

        This activity:
        1. Collects all evidence
        2. Calls LLM to synthesize findings into root cause analysis
        3. Returns whether counter-analysis is needed based on confidence
        """
        try:
            synthesis = await llm.synthesize_findings(
                evidence=input.evidence,
                hypotheses=input.hypotheses,
                alert_summary=input.alert_summary,
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

        # Check confidence threshold
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


# Standalone activity for POC/testing (returns mock synthesis)
@activity.defn
async def synthesize(
    investigation_id: str,
    context: dict[str, Any],
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """POC synthesize activity with mock result.

    Used for testing without real dependencies. Production code should use
    make_synthesize_activity() factory instead.
    """
    return {
        "investigation_id": investigation_id,
        "summary": "The investigation identified potential data quality issues "
        "in the orders table. The primary finding is NULL values in the total "
        "column, which suggests a data pipeline issue in the upstream source.",
        "root_cause": {
            "primary": "NULL values in orders.total column",
            "confidence": 0.8,
            "evidence": [
                "Sample data shows NULL values in total column",
                "Query found NULL values in recent orders",
            ],
        },
        "recommendations": [
            "Add NOT NULL constraint to orders.total column",
            "Investigate upstream data source for missing values",
            "Add data validation in the ETL pipeline",
        ],
        "hypotheses_evaluated": len(hypotheses),
        "status": "completed",
    }
