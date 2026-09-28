"""Steering a running investigation (docs/specs/0001_issue_chat.md §7.8).

People steer a run with four kinds of steer. The workflow applies queued steers at
checkpoints; what a steer does depends on the phase the run is in. The decisions
here are pure functions of the steer and the run's state, so the workflow only
carries them out.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

STEER_KINDS = ("add_context", "rule_out", "add_hypothesis", "stop_and_synthesize")
# People can add this many hypotheses beyond the run's max_hypotheses
EXTRA_HYPOTHESES = 3

# A hypothesis is pending or running until its subagent finishes
UNFINISHED = frozenset({"pending", "running"})
RULED_OUT = "ruled_out"

FINISHED_OUTCOME = "Finished: use Continue investigating"
STEERING_HEADING = "Added while the investigation ran"
# The alert metadata key prompts read the team brief from (agents.prompts.brief)
BRIEF_KEY = "brief"


class Phase(StrEnum):
    """Where a run is when it applies a steer."""

    BEFORE_HYPOTHESES = "before_hypotheses"
    EVALUATION = "evaluation"
    SYNTHESIS = "synthesis"
    FINISHED = "finished"


class Action(StrEnum):
    """What the workflow does for an applied steer."""

    NOTE = "note"  # Add context to later prompts
    EXCLUDE = "exclude"  # Tell hypothesis generation what a person ruled out
    DEFER = "defer"  # Keep queued until hypotheses exist
    CANCEL = "cancel"  # Cancel a hypothesis's subagent
    SET_ASIDE = "set_aside"  # Mark a finished hypothesis ruled out by a person
    ADD = "add"  # Formulate a hypothesis and start its subagent
    STOP = "stop"  # Cancel every running subagent and conclude


@dataclass(frozen=True)
class Steer:
    """A steer as the API signals it."""

    steer_id: str
    kind: str
    text: str = ""
    hypothesis_id: str | None = None
    actor_user_id: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Steer:
        """Build a steer from the signal payload."""
        hypothesis_id = payload.get("hypothesis_id")
        actor = payload.get("actor_user_id")
        return cls(
            steer_id=str(payload.get("steer_id", "")),
            kind=str(payload.get("kind", "")),
            text=str(payload.get("text") or ""),
            hypothesis_id=str(hypothesis_id) if hypothesis_id else None,
            actor_user_id=str(actor) if actor else None,
        )


@dataclass(frozen=True)
class Decision:
    """How a steer ends. A rejected steer has no action."""

    applied: bool
    outcome: str
    action: Action | None = None
    resynthesize: bool = False


@dataclass(frozen=True)
class RunState:
    """What a steer decision needs to know about the run."""

    statuses: dict[str, str]  # Hypothesis id -> pending, running, supported, ...
    titles: dict[str, str]
    max_hypotheses: int
    synthesized: bool = False  # Synthesis ran once, so a change re-synthesizes

    def label(self, hypothesis_id: str) -> str:
        """Return "H3 'late-arriving events'" for an outcome message."""
        title = self.titles.get(hypothesis_id, "")
        return f"{hypothesis_id} '{title}'" if title else hypothesis_id


def _rejected(outcome: str) -> Decision:
    return Decision(applied=False, outcome=outcome)


def decide(steer: Steer, phase: Phase, state: RunState) -> Decision:
    """Decide what a steer does in a phase of the run."""
    if phase is Phase.FINISHED:
        return _rejected(FINISHED_OUTCOME)
    if steer.kind == "add_context":
        return _add_context(steer, phase, state)
    if steer.kind == "rule_out":
        return _rule_out(steer, phase, state)
    if steer.kind == "add_hypothesis":
        return _add_hypothesis(steer, phase, state)
    if steer.kind == "stop_and_synthesize":
        return _stop(phase)
    return _rejected(f"Unknown steer kind: {steer.kind}")


def _add_context(steer: Steer, phase: Phase, state: RunState) -> Decision:
    if not steer.text.strip():
        return _rejected("The context is empty")
    if phase is Phase.BEFORE_HYPOTHESES:
        return Decision(True, "Added to hypothesis generation", Action.NOTE)
    if phase is Phase.EVALUATION:
        return Decision(
            True, "Given to subagents started from now on and to synthesis", Action.NOTE
        )
    if state.synthesized:
        return Decision(True, "Re-synthesizing with it", Action.NOTE, resynthesize=True)
    return Decision(True, "Given to synthesis", Action.NOTE)


def _rule_out(steer: Steer, phase: Phase, state: RunState) -> Decision:
    if phase is Phase.BEFORE_HYPOTHESES:
        if not (steer.text.strip() or steer.hypothesis_id):
            return _rejected("Say what to rule out")
        return Decision(True, "Stored as an exclusion for hypothesis generation", Action.EXCLUDE)
    hypothesis_id = steer.hypothesis_id
    if not hypothesis_id:
        return _rejected("Name the hypothesis to rule out")
    status = state.statuses.get(hypothesis_id)
    if status is None:
        return _rejected(f"No hypothesis {hypothesis_id} in this run")
    if status == RULED_OUT:
        return _rejected(f"{state.label(hypothesis_id)} is already ruled out")
    if status in UNFINISHED:
        return Decision(True, f"Cancelled {state.label(hypothesis_id)}", Action.CANCEL)
    return Decision(
        True,
        f"Set aside {state.label(hypothesis_id)} ({status}) as ruled out by a person",
        Action.SET_ASIDE,
        resynthesize=phase is Phase.SYNTHESIS and state.synthesized,
    )


def _add_hypothesis(steer: Steer, phase: Phase, state: RunState) -> Decision:
    if not steer.text.strip():
        return _rejected("Say what to test")
    if phase is Phase.BEFORE_HYPOTHESES:
        return Decision(True, "Waiting for the generated hypotheses", Action.DEFER)
    if phase is Phase.SYNTHESIS:
        return _rejected("Too late for this run: use Continue investigating")
    limit = state.max_hypotheses + EXTRA_HYPOTHESES
    if len(state.statuses) >= limit:
        return _rejected(f"This run already has its limit of {limit} hypotheses")
    return Decision(True, "Testing it as a new hypothesis", Action.ADD)


def _stop(phase: Phase) -> Decision:
    if phase is Phase.BEFORE_HYPOTHESES:
        return _rejected("No hypotheses yet, so there is nothing to conclude")
    if phase is Phase.SYNTHESIS:
        return _rejected("Already concluding")
    return Decision(True, "Stopped the remaining subagents; concluding now", Action.STOP)


def next_hypothesis_id(existing: list[str]) -> str:
    """Return the next free id in the h1, h2, ... sequence."""
    taken = set(existing)
    number = len(existing) + 1
    while f"h{number}" in taken:
        number += 1
    return f"h{number}"


def steering_note(steer: Steer) -> str:
    """Return the line a steer adds to later prompts."""
    if steer.kind == "rule_out":
        target = f"{steer.hypothesis_id}: " if steer.hypothesis_id else ""
        return f"Ruled out by a person: {target}{steer.text}".rstrip(": ")
    return f"Context from the team: {steer.text}"


def with_steering_notes(alert: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    """Return the alert with steering notes appended to its team brief.

    Every prompt that renders the alert shows the brief (agents/prompts/brief.py),
    so notes added here reach hypothesis generation, later subagents and synthesis.
    """
    if not notes:
        return alert
    metadata = dict(alert.get("metadata") or {})
    brief = str(metadata.get(BRIEF_KEY) or "").rstrip()
    section = "\n".join([f"## {STEERING_HEADING}", *[f"- {note}" for note in notes]])
    metadata[BRIEF_KEY] = f"{brief}\n\n{section}" if brief else section
    return {**alert, "metadata": metadata}
