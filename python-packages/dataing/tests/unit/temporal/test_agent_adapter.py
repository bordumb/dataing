"""Unit tests for TemporalAgentAdapter synthesis inputs."""

from __future__ import annotations

from typing import Any

from dataing.agents.client import AgentClient, SynthesisResponse
from dataing.temporal.adapters import TemporalAgentAdapter


class RecordingAgent:
    """BondAgent stand-in that records prompts and returns a canned response."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.system_prompts: list[str | None] = []

    async def ask(self, prompt: str, *, dynamic_instructions: str | None = None, **_: Any) -> Any:
        self.prompts.append(prompt)
        self.system_prompts.append(dynamic_instructions)
        return self.response


INCONCLUSIVE = SynthesisResponse(
    root_cause=None,
    confidence=0.2,
    causal_chain=["Queries failed", "No evidence collected"],
    estimated_onset="unknown",
    affected_scope="orders table (unverified)",
    supporting_evidence=["No hypothesis could be tested"],
    recommendations=["Restore connectivity to the orders datasource"],
)


async def test_untested_hypotheses_reach_synthesis_prompt() -> None:
    """Untested hypotheses from the workflow appear in the prompt sent to the LLM."""
    client = AgentClient(api_key="test-key")
    synthesis_agent = RecordingAgent(INCONCLUSIVE)
    client._synthesis_agent = synthesis_agent  # type: ignore[assignment]

    result = await TemporalAgentAdapter(client).synthesize_findings_for_temporal(
        evidence=[],
        hypotheses=[{"id": "h-2", "title": "Schema change renamed amount"}],
        alert_summary="orders.amount null rate spiked to 40%",
        untested_hypotheses=[
            {
                "hypothesis_id": "h-2",
                "title": "Schema change renamed amount",
                "error": "Query execution failed: connection refused",
            }
        ],
    )

    [prompt] = synthesis_agent.prompts
    [system_prompt] = synthesis_agent.system_prompts
    assert system_prompt is not None
    assert "UNTESTED HYPOTHESES" in system_prompt
    assert "## Untested Hypotheses" in prompt
    assert (
        "- h-2 (Schema change renamed amount): Query execution failed: connection refused"
    ) in prompt
    assert result["root_cause"] is None
