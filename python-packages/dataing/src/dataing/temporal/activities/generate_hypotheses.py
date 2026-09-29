"""Generate hypotheses activity for investigation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from temporalio import activity

from dataing.agents.errors import classify_llm_error
from dataing.temporal.errors import llm_activity_error

if TYPE_CHECKING:
    from dataing.temporal.adapters import TemporalAgentAdapter


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
    code_changes: list[dict[str, Any]] | None = None


@dataclass
class GenerateHypothesesResult:
    """Result from generate_hypotheses activity."""

    hypotheses: list[dict[str, Any]]
    error: str | None = None


def make_generate_hypotheses_activity(
    adapter: TemporalAgentAdapter,
    max_hypotheses: int = 5,
) -> Any:
    """Factory that creates generate_hypotheses activity with injected adapter.

    Args:
        adapter: TemporalAgentAdapter for LLM operations.
        max_hypotheses: Maximum number of hypotheses to generate.

    Returns:
        The generate_hypotheses activity function.
    """

    @activity.defn
    async def generate_hypotheses(input: GenerateHypothesesInput) -> GenerateHypothesesResult:
        """Generate hypotheses about potential root causes."""
        pattern_hints = [p.get("description", p.get("name", "")) for p in input.matched_patterns]

        try:
            hypotheses = await adapter.generate_hypotheses_for_temporal(
                alert_summary=input.alert_summary,
                alert=input.alert,
                schema_info=input.schema_info,
                lineage_info=input.lineage_info,
                num_hypotheses=input.max_hypotheses or max_hypotheses,
                pattern_hints=pattern_hints if pattern_hints else None,
                code_changes=input.code_changes,
            )
        except Exception as e:
            failure = classify_llm_error(e)
            if failure is not None:
                raise llm_activity_error(failure) from e
            return GenerateHypothesesResult(
                hypotheses=[],
                error=f"Hypothesis generation failed: {e}",
            )

        return GenerateHypothesesResult(hypotheses=hypotheses)

    return generate_hypotheses
