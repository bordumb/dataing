"""What each steer does in each phase of a run (docs/specs/0001_issue_chat.md §7.8)."""

from __future__ import annotations

import pytest

from dataing.agents.prompts.brief import BRIEF_METADATA_KEY
from dataing.temporal.workflows.steering import (
    BRIEF_KEY,
    FINISHED_OUTCOME,
    Action,
    Phase,
    RunState,
    Steer,
    decide,
    next_hypothesis_id,
    steering_note,
    with_steering_notes,
)

STATE = RunState(
    statuses={"h1": "supported", "h2": "running", "h3": "ruled_out"},
    titles={"h1": "app_v2 status", "h2": "late events", "h3": "duplicates"},
    max_hypotheses=5,
)


def s(kind: str, text: str = "because", hypothesis_id: str | None = None) -> Steer:
    """Return a steer."""
    return Steer(steer_id="s1", kind=kind, text=text, hypothesis_id=hypothesis_id)


@pytest.mark.parametrize(
    ("steer", "phase", "applied", "action", "outcome"),
    [
        (s("add_context"), Phase.BEFORE_HYPOTHESES, True, Action.NOTE, None),
        (s("add_context"), Phase.EVALUATION, True, Action.NOTE, None),
        (s("add_context", ""), Phase.EVALUATION, False, None, "The context is empty"),
        (s("rule_out", "late events"), Phase.BEFORE_HYPOTHESES, True, Action.EXCLUDE, None),
        (s("rule_out", "", "h2"), Phase.EVALUATION, True, Action.CANCEL, None),
        (s("rule_out", "x", "h1"), Phase.EVALUATION, True, Action.SET_ASIDE, None),
        (s("rule_out", "x", "h3"), Phase.EVALUATION, False, None, None),
        (s("rule_out", "x", "h9"), Phase.EVALUATION, False, None, "No hypothesis h9 in this run"),
        (s("rule_out", "x"), Phase.EVALUATION, False, None, "Name the hypothesis to rule out"),
        (s("add_hypothesis"), Phase.BEFORE_HYPOTHESES, True, Action.DEFER, None),
        (s("add_hypothesis"), Phase.EVALUATION, True, Action.ADD, None),
        (s("add_hypothesis", "  "), Phase.EVALUATION, False, None, "Say what to test"),
        (s("add_hypothesis"), Phase.SYNTHESIS, False, None, None),
        (s("stop_and_synthesize"), Phase.BEFORE_HYPOTHESES, False, None, None),
        (s("stop_and_synthesize"), Phase.EVALUATION, True, Action.STOP, None),
        (s("stop_and_synthesize"), Phase.SYNTHESIS, False, None, "Already concluding"),
        (s("add_context"), Phase.FINISHED, False, None, FINISHED_OUTCOME),
        (s("reroute"), Phase.EVALUATION, False, None, "Unknown steer kind: reroute"),
    ],
)
def test_decide(
    steer: Steer, phase: Phase, applied: bool, action: Action | None, outcome: str | None
) -> None:
    """Each steer kind is applied or rejected as the spec's table says."""
    decision = decide(steer, phase, STATE)

    assert (decision.applied, decision.action) == (applied, action)
    if outcome is not None:
        assert decision.outcome == outcome


def test_changes_after_synthesis_resynthesize() -> None:
    """Context or a ruled-out hypothesis after synthesis ran asks for one re-synthesis."""
    synthesized = RunState(**{**STATE.__dict__, "synthesized": True})

    assert decide(s("add_context"), Phase.SYNTHESIS, synthesized).resynthesize
    assert decide(s("rule_out", "x", "h1"), Phase.SYNTHESIS, synthesized).resynthesize
    assert not decide(s("add_context"), Phase.SYNTHESIS, STATE).resynthesize


def test_add_hypothesis_is_capped_at_max_plus_three() -> None:
    """A run tests at most max_hypotheses + 3 hypotheses."""
    full = RunState(statuses={f"h{i}": "running" for i in range(1, 5)}, titles={}, max_hypotheses=1)

    decision = decide(s("add_hypothesis"), Phase.EVALUATION, full)

    assert not decision.applied
    assert decision.outcome == "This run already has its limit of 4 hypotheses"


def test_next_hypothesis_id_skips_taken_ids() -> None:
    """New hypotheses continue the h1, h2, ... sequence."""
    assert next_hypothesis_id(["h1", "h2", "h3"]) == "h4"
    assert next_hypothesis_id(["h1", "h4"]) == "h3"
    assert next_hypothesis_id(["h1", "h2", "h3", "h4"]) == "h5"
    assert next_hypothesis_id([]) == "h1"


def test_notes_are_appended_to_the_team_brief() -> None:
    """Steering notes reach every prompt through the brief in the alert's metadata."""
    alert = {"dataset_ids": ["orders"], "metadata": {BRIEF_KEY: "Symptom: orders dropped"}}
    notes = [
        steering_note(s("add_context", "app_v2 shipped at 09:00")),
        steering_note(s("rule_out", "clock skew", "h2")),
    ]

    steered = with_steering_notes(alert, notes)

    assert BRIEF_KEY == BRIEF_METADATA_KEY
    assert steered["metadata"][BRIEF_KEY] == (
        "Symptom: orders dropped\n\n"
        "## Added while the investigation ran\n"
        "- Context from the team: app_v2 shipped at 09:00\n"
        "- Ruled out by a person: h2: clock skew"
    )
    assert alert["metadata"][BRIEF_KEY] == "Symptom: orders dropped"
    assert with_steering_notes(alert, []) is alert


def test_notes_start_a_brief_when_the_alert_has_none() -> None:
    """A check-started run has no brief; steering notes become one."""
    steered = with_steering_notes({"metadata": None}, ["Context from the team: x"])

    assert steered["metadata"][BRIEF_KEY].startswith("## Added while the investigation ran")
