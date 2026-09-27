"""Unit tests for the interpret_evidence activity."""

from __future__ import annotations

from typing import Any

from dataing.temporal.activities import (
    InterpretEvidenceInput,
    InterpretEvidenceResult,
    make_interpret_evidence_activity,
)

INTERPRET_INPUT = InterpretEvidenceInput(
    investigation_id="inv-1",
    hypothesis={"id": "h-1", "title": "Upstream ETL wrote NULL amounts"},
    query_result={"query": "SELECT amount FROM orders", "rows": [], "row_count": 0},
    alert_summary="orders.amount null rate spiked to 40%",
)


class FailingAgent:
    """TemporalAgentAdapter stub whose interpretation always fails."""

    async def interpret_evidence(self, **_: Any) -> dict[str, Any]:
        raise RuntimeError("LLM request timed out")


async def test_failed_interpretation_returns_error_result_without_verdict() -> None:
    """An interpretation failure carries no verdict: False would read as refuted."""
    interpret_evidence = make_interpret_evidence_activity(adapter=FailingAgent())

    result = await interpret_evidence(INTERPRET_INPUT)

    assert result == InterpretEvidenceResult(
        hypothesis_id="h-1",
        supports_hypothesis=None,
        confidence=0.0,
        interpretation="",
        key_findings=[],
        error="Evidence interpretation failed: LLM request timed out",
    )
