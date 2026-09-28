"""Fake activities for running InvestigationWorkflow on Temporal's test server.

Each fake returns the dict shape the workflow reads. Hypothesis evaluations can be
held open (to steer a run while its subagents are working) and every call is
recorded, so tests can assert what the manager and its subagents did.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from temporalio import activity

INVESTIGATION_TASK_QUEUE = "investigation-tests"


def hypothesis(hypothesis_id: str, title: str) -> dict[str, Any]:
    """Return a hypothesis dict as generate_hypotheses produces it."""
    return {
        "id": hypothesis_id,
        "title": title,
        "category": "data_quality",
        "reasoning": f"Because {title}",
        "suggested_query": f"SELECT 1 -- {hypothesis_id}",
    }


@dataclass
class FakeInvestigation:
    """Scriptable fakes for every activity InvestigationWorkflow and its children call."""

    hypotheses: list[dict[str, Any]] = field(
        default_factory=lambda: [
            hypothesis("h1", "app_v2 writes a different status"),
            hypothesis("h2", "events not landing"),
            hypothesis("h3", "late-arriving events"),
        ]
    )
    confidence: float = 0.9
    hold: set[str] = field(default_factory=set)
    released: asyncio.Event = field(default_factory=asyncio.Event)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def names(self) -> list[str]:
        """Return the activity names in call order."""
        return [name for name, _ in self.calls]

    def inputs(self, name: str) -> list[dict[str, Any]]:
        """Return the inputs of every call to one activity."""
        return [payload for called, payload in self.calls if called == name]

    def activities(self) -> list[Any]:
        """Return the fake activities."""
        fake = self

        def record(name: str, payload: dict[str, Any]) -> None:
            fake.calls.append((name, payload))

        @activity.defn(name="gather_context")
        async def gather_context(payload: dict[str, Any]) -> dict[str, Any]:
            record("gather_context", payload)
            return {"schema_info": {"tables": ["orders"]}, "lineage_info": None}

        @activity.defn(name="check_patterns")
        async def check_patterns(payload: dict[str, Any]) -> dict[str, Any]:
            record("check_patterns", payload)
            return {"matched_patterns": []}

        @activity.defn(name="generate_hypotheses")
        async def generate_hypotheses(payload: dict[str, Any]) -> dict[str, Any]:
            record("generate_hypotheses", payload)
            return {"hypotheses": fake.hypotheses}

        @activity.defn(name="capture_snapshot")
        async def capture_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "storage_path": None}

        @activity.defn(name="generate_query")
        async def generate_query(payload: dict[str, Any]) -> dict[str, Any]:
            record("generate_query", payload)
            hypothesis_id = payload["hypothesis"]["id"]
            if hypothesis_id in fake.hold:
                while not fake.released.is_set():
                    activity.heartbeat()
                    await asyncio.sleep(0.02)
            return {"query": f"SELECT 1 -- {hypothesis_id}"}

        @activity.defn(name="execute_query")
        async def execute_query(payload: dict[str, Any]) -> dict[str, Any]:
            record("execute_query", payload)
            return {"columns": ["n"], "rows": [{"n": 1}], "row_count": 1}

        @activity.defn(name="interpret_evidence")
        async def interpret_evidence(payload: dict[str, Any]) -> dict[str, Any]:
            record("interpret_evidence", payload)
            return {
                "supports_hypothesis": payload["hypothesis"]["id"] == "h1",
                "confidence": 0.8,
                "interpretation": f"Checked {payload['hypothesis']['id']}",
                "key_findings": [],
            }

        @activity.defn(name="synthesize")
        async def synthesize(payload: dict[str, Any]) -> dict[str, Any]:
            record("synthesize", payload)
            return {
                "root_cause": "app_v2 writes COMPLETE instead of completed",
                "confidence": fake.confidence,
                "recommendations": ["Normalize status in the loader"],
                "supporting_evidence": ["h1"],
                "needs_counter_analysis": False,
            }

        @activity.defn(name="finalize_evidence_chain")
        async def finalize_evidence_chain(payload: dict[str, Any]) -> dict[str, Any]:
            return {"root_hash": "abc123"}

        @activity.defn(name="counter_analyze")
        async def counter_analyze(payload: dict[str, Any]) -> dict[str, Any]:
            record("counter_analyze", payload)
            return {"alternative_explanations": [], "weaknesses": [], "recommendation": "accept"}

        @activity.defn(name="publish_investigation_outcome")
        async def publish_investigation_outcome(payload: dict[str, Any]) -> dict[str, Any]:
            record("publish_investigation_outcome", payload)
            return {"published": True}

        @activity.defn(name="formulate_hypothesis")
        async def formulate_hypothesis(payload: dict[str, Any]) -> dict[str, Any]:
            record("formulate_hypothesis", payload)
            return {"hypothesis": hypothesis(payload["hypothesis_id"], payload["text"])}

        @activity.defn(name="record_steer_outcome")
        async def record_steer_outcome(payload: dict[str, Any]) -> dict[str, Any]:
            record("record_steer_outcome", payload)
            return {"recorded": True}

        return [
            gather_context,
            check_patterns,
            generate_hypotheses,
            capture_snapshot,
            generate_query,
            execute_query,
            interpret_evidence,
            synthesize,
            finalize_evidence_chain,
            counter_analyze,
            publish_investigation_outcome,
            formulate_hypothesis,
            record_steer_outcome,
        ]
