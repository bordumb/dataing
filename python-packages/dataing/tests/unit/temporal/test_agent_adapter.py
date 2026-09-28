"""Unit tests for TemporalAgentAdapter synthesis inputs."""

from __future__ import annotations

from typing import Any

import pytest

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


async def test_untested_hypotheses_reach_synthesis_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Untested hypotheses from the workflow appear in the prompt sent to the LLM."""
    synthesis_agent = RecordingAgent(INCONCLUSIVE)
    # AgentClient builds a fresh BondAgent for every call, so record through that.
    monkeypatch.setattr("dataing.agents.client.BondAgent", lambda **_: synthesis_agent)
    client = AgentClient(api_key="test-key")

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


async def test_team_brief_and_ruled_out_hypotheses_reach_synthesis_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthesis sees the brief with steering notes and what people ruled out."""
    synthesis_agent = RecordingAgent(INCONCLUSIVE)
    monkeypatch.setattr("dataing.agents.client.BondAgent", lambda **_: synthesis_agent)
    alert = {
        "dataset_ids": ["public.orders"],
        "metric_spec": {
            "metric_type": "description",
            "expression": "Completed orders dropped",
            "display_name": "Orders dropped",
        },
        "anomaly_type": "custom",
        "expected_value": 0.0,
        "actual_value": 0.0,
        "deviation_pct": 0.0,
        "anomaly_date": "2026-09-14",
        "severity": "high",
        "metadata": {"brief": "Context from the team: app_v2 shipped at 09:00"},
    }

    await TemporalAgentAdapter(AgentClient(api_key="test-key")).synthesize_findings_for_temporal(
        evidence=[],
        hypotheses=[],
        alert_summary="Completed orders dropped",
        untested_hypotheses=[],
        alert=alert,
        ruled_out_hypotheses=[
            {"hypothesis_id": "h3", "title": "late events", "reason": "Events land in minutes"}
        ],
    )

    [prompt] = synthesis_agent.prompts
    [system_prompt] = synthesis_agent.system_prompts
    assert "## Team brief" in prompt
    assert "Context from the team: app_v2 shipped at 09:00" in prompt
    assert "## Ruled Out by the Team" in prompt
    assert "- h3 (late events): Events land in minutes" in prompt
    assert system_prompt is not None
    assert "Ruled Out by the Team" in system_prompt
