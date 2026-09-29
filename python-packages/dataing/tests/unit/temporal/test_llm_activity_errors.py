"""LLM activities fail instead of returning empty results (docs/specs/0001_issue_chat.md §7.12).

An error the API returns becomes a Temporal ApplicationError: LLMRejected, which no
retry can fix, or LLMUnavailable, which the activity's retry policy tries again.
Other errors keep coming back in the result's `error` field, as before.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fixtures.llm_errors import anthropic_error
from temporalio.exceptions import ApplicationError

from dataing.temporal.activities import (
    CounterAnalyzeInput,
    GenerateHypothesesInput,
    GenerateQueryInput,
    InterpretEvidenceInput,
    SynthesizeInput,
    make_counter_analyze_activity,
    make_generate_hypotheses_activity,
    make_generate_query_activity,
    make_interpret_evidence_activity,
    make_synthesize_activity,
)

HYPOTHESIS = {"id": "h1", "title": "app_v2 writes a different status"}
INVALID_KEY = (
    "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and "
    "restart the API and the worker."
)


class FailingAdapter:
    """TemporalAgentAdapter stub whose every LLM call raises the same error."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def generate_hypotheses_for_temporal(self, **_: Any) -> list[dict[str, Any]]:
        raise self.error

    async def generate_query(self, **_: Any) -> str:
        raise self.error

    async def interpret_evidence(self, **_: Any) -> dict[str, Any]:
        raise self.error

    async def synthesize_findings_for_temporal(self, **_: Any) -> dict[str, Any]:
        raise self.error

    async def counter_analyze(self, **_: Any) -> dict[str, Any]:
        raise self.error


Run = Callable[[FailingAdapter], Awaitable[Any]]

ACTIVITIES: list[tuple[str, Run]] = [
    (
        "generate_hypotheses",
        lambda adapter: make_generate_hypotheses_activity(adapter)(  # type: ignore[arg-type]
            GenerateHypothesesInput(
                investigation_id="inv-1",
                alert_summary="orders dropped",
                alert=None,
                schema_info=None,
                lineage_info=None,
                matched_patterns=[],
            )
        ),
    ),
    (
        "generate_query",
        lambda adapter: make_generate_query_activity(adapter)(  # type: ignore[arg-type]
            GenerateQueryInput(
                investigation_id="inv-1",
                hypothesis=HYPOTHESIS,
                schema_info={},
                alert_summary="orders dropped",
            )
        ),
    ),
    (
        "interpret_evidence",
        lambda adapter: make_interpret_evidence_activity(adapter)(  # type: ignore[arg-type]
            InterpretEvidenceInput(
                investigation_id="inv-1",
                hypothesis=HYPOTHESIS,
                query_result={"query": "SELECT 1", "rows": [], "row_count": 0},
                alert_summary="orders dropped",
            )
        ),
    ),
    (
        "synthesize",
        lambda adapter: make_synthesize_activity(adapter)(  # type: ignore[arg-type]
            SynthesizeInput(
                investigation_id="inv-1",
                evidence=[],
                hypotheses=[HYPOTHESIS],
                alert_summary="orders dropped",
            )
        ),
    ),
    (
        "counter_analyze",
        lambda adapter: make_counter_analyze_activity(adapter)(  # type: ignore[arg-type]
            CounterAnalyzeInput(
                investigation_id="inv-1",
                synthesis={"root_cause": "x", "confidence": 0.5},
                evidence=[],
                hypotheses=[HYPOTHESIS],
            )
        ),
    ),
]
NAMES = [name for name, _ in ACTIVITIES]


@pytest.mark.parametrize(("name", "run"), ACTIVITIES, ids=NAMES)
async def test_a_rejected_key_fails_the_activity_for_good(name: str, run: Run) -> None:
    """A 401 is LLMRejected and non-retryable, with the code and what to fix."""
    with pytest.raises(ApplicationError) as caught:
        await run(FailingAdapter(anthropic_error(401)))

    error = caught.value
    assert error.type == "LLMRejected"
    assert error.non_retryable
    assert error.message == INVALID_KEY
    assert list(error.details) == [{"code": "invalid_key", "message": INVALID_KEY}]


@pytest.mark.parametrize(("name", "run"), ACTIVITIES, ids=NAMES)
async def test_an_overloaded_api_fails_the_activity_for_a_retry(name: str, run: Run) -> None:
    """A 529 is LLMUnavailable, which the retry policy tries again."""
    with pytest.raises(ApplicationError) as caught:
        await run(FailingAdapter(anthropic_error(529)))

    error = caught.value
    assert error.type == "LLMUnavailable"
    assert not error.non_retryable
    assert list(error.details) == [
        {"code": "overloaded", "message": "Anthropic is overloaded (529)."}
    ]


@pytest.mark.parametrize(("name", "run"), ACTIVITIES, ids=NAMES)
async def test_other_errors_still_come_back_in_the_result(name: str, run: Run) -> None:
    """An error that isn't from the API keeps its old path: the result's error field."""
    result = await run(FailingAdapter(RuntimeError("output didn't validate")))

    assert result.error is not None
    assert "output didn't validate" in result.error
