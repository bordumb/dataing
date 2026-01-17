"""Generate query activity for investigation workflow.

Extracts business logic from GenerateQueryStep into a Temporal activity factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from temporalio import activity


class LLMProtocol(Protocol):
    """Protocol for LLM client used by generate_query activity."""

    async def generate_query(
        self,
        *,
        hypothesis: dict[str, Any],
        schema_info: dict[str, Any],
        alert_summary: str,
        alert: dict[str, Any] | None,
    ) -> str:
        """Generate a SQL query to test the hypothesis."""
        ...


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


def make_generate_query_activity(llm: LLMProtocol) -> Any:
    """Factory that creates generate_query activity with injected dependencies.

    Args:
        llm: LLM client for generating queries.

    Returns:
        The generate_query activity function.
    """

    @activity.defn
    async def generate_query(input: GenerateQueryInput) -> GenerateQueryResult:
        """Generate a SQL query to test a hypothesis.

        This activity:
        1. Receives hypothesis and schema info
        2. Calls LLM to generate a query to test the hypothesis
        3. Returns the generated query
        """
        hypothesis_id = input.hypothesis.get("id", "unknown")

        try:
            query = await llm.generate_query(
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


# Standalone activity for POC/testing (returns mock query)
@activity.defn
async def generate_query(
    investigation_id: str,
    hypothesis: dict[str, Any],
    schema_info: dict[str, Any],
) -> str:
    """POC generate_query activity with mock query.

    Used for testing without real dependencies. Production code should use
    make_generate_query_activity() factory instead.
    """
    hypothesis_id = hypothesis.get("id", "unknown")
    query = f"-- Query for hypothesis {hypothesis_id}\n"
    query += "SELECT COUNT(*) FROM orders WHERE total IS NULL"
    return query
