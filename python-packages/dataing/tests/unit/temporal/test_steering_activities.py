"""The formulate_hypothesis activity and steer outcome text (spec 0001 §7.8)."""

from __future__ import annotations

from temporalio.testing import ActivityEnvironment

from dataing.core.domain_types import Hypothesis
from dataing.temporal.activities.steering import formulate_hypothesis, steer_outcome_text


async def test_formulated_hypothesis_is_a_valid_hypothesis() -> None:
    """A person's text becomes a hypothesis the subagent's query step accepts."""
    result = await ActivityEnvironment().run(
        formulate_hypothesis,
        {"hypothesis_id": "h4", "text": "  timezone bug\nin the loader ", "alert_summary": "x"},
    )

    hypothesis = Hypothesis.model_validate(result["hypothesis"])
    assert (hypothesis.id, hypothesis.title) == ("h4", "timezone bug in the loader")


async def test_long_text_gets_a_short_title() -> None:
    """Titles stay short; the full text is kept in the reasoning."""
    text = "word " * 60
    result = await ActivityEnvironment().run(
        formulate_hypothesis, {"hypothesis_id": "h5", "text": text}
    )

    assert len(result["hypothesis"]["title"]) == 120
    assert result["hypothesis"]["title"].endswith("...")
    assert text.strip() in result["hypothesis"]["reasoning"]


def test_outcome_text() -> None:
    """The thread says when a steer applied, or why it didn't."""
    assert steer_outcome_text("applied", "evaluation", "Cancelled h3") == (
        "Applied during evaluation: Cancelled h3"
    )
    assert steer_outcome_text("rejected", "finished", "Finished: use Continue investigating") == (
        "Not applied: Finished: use Continue investigating"
    )
