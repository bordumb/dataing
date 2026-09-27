"""Unit tests for TemporalAgentAdapter synthesis inputs."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import models

from dataing.agents.client import AgentClient, SynthesisResponse
from dataing.temporal.adapters import TemporalAgentAdapter


class RecordingAsk:
    """AgentClient._ask stand-in that records prompts and returns a canned response."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.system_prompts: list[str] = []

    async def __call__(
        self, name: str, output_type: type[Any], prompt: str, *, instructions: str, **_: Any
    ) -> Any:
        self.prompts.append(prompt)
        self.system_prompts.append(instructions)
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


async def test_untested_hypotheses_reach_synthesis_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Untested hypotheses from the workflow appear in the prompt sent to the LLM."""
    # If the stub below ever stops applying, fail instead of calling Anthropic.
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    client = AgentClient(api_key="test-key")
    ask = RecordingAsk(INCONCLUSIVE)
    monkeypatch.setattr(client, "_ask", ask)

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

    [prompt] = ask.prompts
    [system_prompt] = ask.system_prompts
    assert "UNTESTED HYPOTHESES" in system_prompt
    assert "## Untested Hypotheses" in prompt
    assert (
        "- h-2 (Schema change renamed amount): Query execution failed: connection refused"
    ) in prompt
    assert result["root_cause"] is None
