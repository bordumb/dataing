"""Generate hypotheses activity for investigation workflow.

Extracts business logic from GenerateHypothesesStep into a Temporal activity factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from temporalio import activity


class LLMProtocol(Protocol):
    """Protocol for LLM client used by generate_hypotheses activity."""

    async def generate_hypotheses(
        self,
        *,
        alert_summary: str,
        alert: dict[str, Any] | None,
        schema_info: dict[str, Any] | None,
        lineage_info: dict[str, Any] | None,
        num_hypotheses: int,
        pattern_hints: list[str] | None,
    ) -> list[Any]:
        """Generate hypotheses about potential root causes.

        Returns:
            List of Hypothesis objects (with .model_dump() method).
        """
        ...


@dataclass
class GenerateHypothesesInput:
    """Input for generate_hypotheses activity."""

    investigation_id: str
    alert_summary: str
    alert: dict[str, Any] | None
    schema_info: dict[str, Any] | None
    lineage_info: dict[str, Any] | None
    matched_patterns: list[dict[str, Any]]
    max_hypotheses: int = 5


@dataclass
class GenerateHypothesesResult:
    """Result from generate_hypotheses activity."""

    hypotheses: list[dict[str, Any]]
    error: str | None = None


def make_generate_hypotheses_activity(
    llm: LLMProtocol,
    max_hypotheses: int = 5,
) -> Any:
    """Factory that creates generate_hypotheses activity with injected dependencies.

    Args:
        llm: LLM client for generating hypotheses.
        max_hypotheses: Maximum number of hypotheses to generate.

    Returns:
        The generate_hypotheses activity function.
    """

    @activity.defn
    async def generate_hypotheses(input: GenerateHypothesesInput) -> GenerateHypothesesResult:
        """Generate hypotheses about potential root causes.

        This activity:
        1. Extracts pattern hints from matched patterns
        2. Calls LLM to generate hypotheses based on alert and context
        3. Returns list of hypothesis dictionaries
        """
        # Extract pattern hints if any patterns matched
        pattern_hints = [
            p.get("description", p.get("name", ""))
            for p in input.matched_patterns
        ]

        try:
            hypotheses = await llm.generate_hypotheses(
                alert_summary=input.alert_summary,
                alert=input.alert,
                schema_info=input.schema_info,
                lineage_info=input.lineage_info,
                num_hypotheses=input.max_hypotheses or max_hypotheses,
                pattern_hints=pattern_hints if pattern_hints else None,
            )
        except Exception as e:
            return GenerateHypothesesResult(
                hypotheses=[],
                error=f"Hypothesis generation failed: {e}",
            )

        # Convert hypotheses to dicts
        hypotheses_dicts = [h.model_dump() for h in hypotheses]

        return GenerateHypothesesResult(hypotheses=hypotheses_dicts)

    return generate_hypotheses


# Standalone activity for POC/testing (returns mock hypotheses)
@activity.defn
async def generate_hypotheses(
    investigation_id: str,
    alert_data: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """POC generate_hypotheses activity with mock data.

    Used for testing without real dependencies. Production code should use
    make_generate_hypotheses_activity() factory instead.
    """
    return [
        {
            "id": f"{investigation_id}-h1",
            "title": "Null values in orders.total column",
            "explanation": "The alert may be caused by unexpected NULL values "
            "in the total column, which could indicate data pipeline issues.",
            "query": "SELECT COUNT(*) FROM orders WHERE total IS NULL",
            "confidence": 0.8,
        },
        {
            "id": f"{investigation_id}-h2",
            "title": "Missing foreign key references",
            "explanation": "Orders may reference customers that don't exist, "
            "indicating a data integrity issue.",
            "query": "SELECT COUNT(*) FROM orders o "
            "LEFT JOIN customers c ON o.customer_id = c.id "
            "WHERE c.id IS NULL",
            "confidence": 0.6,
        },
        {
            "id": f"{investigation_id}-h3",
            "title": "Recent volume spike",
            "explanation": "There may be an unusual increase in order volume "
            "that triggered the anomaly detection.",
            "query": "SELECT DATE(created_at), COUNT(*) FROM orders "
            "GROUP BY DATE(created_at) ORDER BY 1 DESC LIMIT 7",
            "confidence": 0.5,
        },
    ]
