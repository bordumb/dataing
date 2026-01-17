"""Generate query activity for investigation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from temporalio import activity

if TYPE_CHECKING:
    from dataing.temporal.adapters import TemporalAgentAdapter


@dataclass
class GenerateQueryInput:
    """Input for generate_query activity."""

    investigation_id: str
    hypothesis: dict[str, Any]
    schema_info: dict[str, Any]
    alert_summary: str
    alert: dict[str, Any] | None = None


@dataclass
class GenerateQueryResult:
    """Result from generate_query activity."""

    query: str
    hypothesis_id: str
    error: str | None = None


def make_generate_query_activity(adapter: TemporalAgentAdapter) -> Any:
    """Factory that creates generate_query activity with injected adapter.

    Args:
        adapter: TemporalAgentAdapter for LLM operations.

    Returns:
        The generate_query activity function.
    """

    @activity.defn
    async def generate_query(input: GenerateQueryInput) -> GenerateQueryResult:
        """Generate a SQL query to test a hypothesis."""
        hypothesis_id = input.hypothesis.get("id", "unknown")

        try:
            query = await adapter.generate_query(
                hypothesis=input.hypothesis,
                schema_info=input.schema_info,
                alert_summary=input.alert_summary,
                alert=input.alert,
            )
        except Exception as e:
            return GenerateQueryResult(
                query="",
                hypothesis_id=hypothesis_id,
                error=f"Query generation failed: {e}",
            )

        return GenerateQueryResult(
            query=query,
            hypothesis_id=hypothesis_id,
        )

    return generate_query
