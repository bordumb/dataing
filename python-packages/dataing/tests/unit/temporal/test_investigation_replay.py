"""Recorded InvestigationWorkflow histories still replay on the current code.

Histories in tests/fixtures/temporal_histories were recorded before later workflow
changes (tests/fixtures/record_investigation_histories.py). Replaying them proves
that runs in flight during a deploy keep working: new code paths must sit behind
workflow.patched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from dataing.temporal.sandbox import workflow_runner
from dataing.temporal.workflows import EvaluateHypothesisWorkflow, InvestigationWorkflow

HISTORIES = sorted((Path(__file__).parents[2] / "fixtures" / "temporal_histories").glob("*.json"))


@pytest.mark.parametrize("path", HISTORIES, ids=[p.stem for p in HISTORIES])
async def test_recorded_history_replays(path: Path) -> None:
    """The current workflow code makes the same decisions as the recorded run."""
    # Recorded as workflow id "replay-<outcome>"; child ids derive from it
    workflow_id = f"replay-{path.stem.rsplit('_', 1)[1]}"
    history = WorkflowHistory.from_json(workflow_id, json.loads(path.read_text()))
    replayer = Replayer(
        workflow_runner=workflow_runner(),
        workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow],
    )

    await replayer.replay_workflow(history)


def test_histories_are_present() -> None:
    """At least the pre-steering baseline is recorded."""
    assert any("pre_steering" in p.stem for p in HISTORIES)
