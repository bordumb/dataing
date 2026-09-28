"""Record InvestigationWorkflow histories for replay tests.

Run from the repository root with the worktree's sources on the path, setting
PYTHONPATH to python-packages/dataing/src and python-packages/dataing/tests:

    python python-packages/dataing/tests/fixtures/record_investigation_histories.py <label>

Histories recorded before a workflow change let test_investigation_replay.py
prove that runs already in flight still replay after it (workflow.patched).
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from fixtures.investigation_env import INVESTIGATION_TASK_QUEUE, FakeInvestigation
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from dataing.temporal.workflows import (
    EvaluateHypothesisWorkflow,
    InvestigationInput,
    InvestigationWorkflow,
)

HISTORY_DIR = Path(__file__).parent / "temporal_histories"


def investigation_input(investigation_id: str, *, brief: bool = True) -> InvestigationInput:
    """Return an input like the issue spawn route builds."""
    alert: dict[str, Any] = {
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
        "issue_id": str(uuid.UUID(int=7)),
    }
    if brief:
        alert["brief"] = {"version": 1, "symptom": "Completed orders dropped"}
    return InvestigationInput(
        investigation_id=investigation_id,
        tenant_id=str(uuid.UUID(int=1)),
        datasource_id=str(uuid.UUID(int=2)),
        alert_data=alert,
        alert_summary="Completed orders dropped",
        enable_snapshots=False,
    )


async def record(label: str) -> None:
    """Run a completed and a cancelled investigation and save their histories."""
    HISTORY_DIR.mkdir(exist_ok=True)
    fake = FakeInvestigation()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=INVESTIGATION_TASK_QUEUE,
            workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow],
            activities=fake.activities(),
        ):
            completed = await env.client.start_workflow(
                InvestigationWorkflow.run,
                investigation_input("replay-completed"),
                id="replay-completed",
                task_queue=INVESTIGATION_TASK_QUEUE,
            )
            await completed.result()

            fake.hold.add("h1")
            cancelled = await env.client.start_workflow(
                InvestigationWorkflow.run,
                investigation_input("replay-cancelled"),
                id="replay-cancelled",
                task_queue=INVESTIGATION_TASK_QUEUE,
            )
            while "generate_query" not in fake.names()[len(fake.calls) - 6 :]:
                await asyncio.sleep(0.05)
            await cancelled.signal(InvestigationWorkflow.cancel_investigation)
            fake.released.set()
            await cancelled.result()

            for handle, name in ((completed, "completed"), (cancelled, "cancelled")):
                history = await handle.fetch_history()
                path = HISTORY_DIR / f"investigation_{label}_{name}.json"
                path.write_text(json.dumps(json.loads(history.to_json()), indent=1) + "\n")
                print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(record(sys.argv[1] if len(sys.argv) > 1 else "baseline"))
