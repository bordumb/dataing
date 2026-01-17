#!/usr/bin/env python3
"""Test script to verify Temporal crash recovery.

This script validates that Temporal properly resumes workflows after worker crash.
It's the core durability guarantee that Temporal provides.

Prerequisites:
    1. Temporal server running: temporal server start-dev
    2. Worker NOT running (script will start it)

Usage:
    python scripts/test_crash_recovery.py

The script will:
    1. Start a workflow with a slow activity
    2. Start a worker in a subprocess
    3. Wait for the first activity to complete
    4. Kill the worker (SIGKILL)
    5. Restart the worker
    6. Verify the workflow completes successfully
"""

import asyncio
import os
import signal
import subprocess
import sys
from datetime import timedelta
from typing import Any

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dataing", "src"))

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker


# Slow activity for testing crash recovery
@activity.defn
async def slow_gather_context(investigation_id: str, datasource_id: str) -> dict[str, Any]:
    """Slow activity that takes 10 seconds to complete."""
    print(f"[Activity] Starting slow_gather_context for {investigation_id}")
    await asyncio.sleep(10)  # Simulate slow operation
    print(f"[Activity] Completed slow_gather_context for {investigation_id}")
    return {
        "investigation_id": investigation_id,
        "datasource_id": datasource_id,
        "schema": {"tables": [{"name": "orders", "columns": ["id", "total"]}]},
    }


@activity.defn
async def slow_generate_hypotheses(
    investigation_id: str,
    alert_data: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Slow activity that takes 10 seconds to complete."""
    print(f"[Activity] Starting slow_generate_hypotheses for {investigation_id}")
    await asyncio.sleep(10)  # Simulate slow operation
    print(f"[Activity] Completed slow_generate_hypotheses for {investigation_id}")
    return [
        {
            "id": f"{investigation_id}-h1",
            "title": "Test hypothesis",
            "confidence": 0.8,
        },
    ]


@activity.defn
async def slow_synthesize(
    investigation_id: str,
    context: dict[str, Any],
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Slow activity that takes 10 seconds to complete."""
    print(f"[Activity] Starting slow_synthesize for {investigation_id}")
    await asyncio.sleep(10)  # Simulate slow operation
    print(f"[Activity] Completed slow_synthesize for {investigation_id}")
    return {
        "investigation_id": investigation_id,
        "summary": "Test synthesis result",
        "status": "completed",
    }


# Test workflow with slow activities
@workflow.defn
class CrashRecoveryTestWorkflow:
    """Test workflow with slow activities for crash recovery testing."""

    @workflow.run
    async def run(self, investigation_id: str) -> dict[str, Any]:
        """Run the test workflow."""
        workflow.logger.info(f"Starting workflow for {investigation_id}")

        # Step 1: Slow gather context
        context = await workflow.execute_activity(
            slow_gather_context,
            args=[investigation_id, "test-datasource"],
            start_to_close_timeout=timedelta(minutes=5),
        )
        workflow.logger.info("Completed gather_context")

        # Step 2: Slow generate hypotheses
        hypotheses = await workflow.execute_activity(
            slow_generate_hypotheses,
            args=[investigation_id, {"metric": "test"}, context],
            start_to_close_timeout=timedelta(minutes=5),
        )
        workflow.logger.info("Completed generate_hypotheses")

        # Step 3: Slow synthesize
        synthesis = await workflow.execute_activity(
            slow_synthesize,
            args=[investigation_id, context, hypotheses],
            start_to_close_timeout=timedelta(minutes=5),
        )
        workflow.logger.info("Completed synthesize")

        return {
            "investigation_id": investigation_id,
            "status": "completed",
            "context": context,
            "hypotheses": hypotheses,
            "synthesis": synthesis,
        }


async def run_worker(client: Client, task_queue: str) -> None:
    """Run a worker that processes the test workflow."""
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[CrashRecoveryTestWorkflow],
        activities=[slow_gather_context, slow_generate_hypotheses, slow_synthesize],
    )
    await worker.run()


async def main() -> None:
    """Run the crash recovery test."""
    print("=" * 60)
    print("Temporal Crash Recovery Test")
    print("=" * 60)

    # Connect to Temporal
    print("\n[1] Connecting to Temporal server...")
    try:
        client = await Client.connect("localhost:7233")
        print("    Connected to localhost:7233")
    except Exception as e:
        print(f"    ERROR: Failed to connect to Temporal: {e}")
        print("    Make sure Temporal is running: temporal server start-dev")
        sys.exit(1)

    task_queue = "crash-recovery-test"
    workflow_id = "crash-recovery-test-001"

    # Start the workflow
    print(f"\n[2] Starting workflow: {workflow_id}")
    handle = await client.start_workflow(
        CrashRecoveryTestWorkflow.run,
        workflow_id,
        id=workflow_id,
        task_queue=task_queue,
    )
    print(f"    Workflow started: {handle.id}")

    # Start worker in subprocess
    print("\n[3] Starting worker in subprocess...")
    worker_process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"""
import asyncio
import sys
sys.path.insert(0, "{os.path.dirname(__file__)}")
from test_crash_recovery import run_worker
from temporalio.client import Client

async def main():
    client = await Client.connect("localhost:7233")
    await run_worker(client, "{task_queue}")

asyncio.run(main())
""",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"    Worker started with PID: {worker_process.pid}")

    # Wait for first activity to complete
    print("\n[4] Waiting 15 seconds for first activity to complete...")
    await asyncio.sleep(15)

    # Kill the worker
    print(f"\n[5] KILLING worker (PID {worker_process.pid}) with SIGKILL...")
    os.kill(worker_process.pid, signal.SIGKILL)
    worker_process.wait()
    print("    Worker killed!")

    # Wait a moment
    print("\n[6] Waiting 5 seconds before restarting worker...")
    await asyncio.sleep(5)

    # Check workflow state
    desc = await handle.describe()
    print(f"    Workflow status: {desc.status.name}")

    # Restart worker
    print("\n[7] Restarting worker...")
    worker_process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"""
import asyncio
import sys
sys.path.insert(0, "{os.path.dirname(__file__)}")
from test_crash_recovery import run_worker
from temporalio.client import Client

async def main():
    client = await Client.connect("localhost:7233")
    await run_worker(client, "{task_queue}")

asyncio.run(main())
""",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"    Worker restarted with PID: {worker_process.pid}")

    # Wait for workflow to complete
    print("\n[8] Waiting for workflow to complete...")
    try:
        result = await asyncio.wait_for(handle.result(), timeout=120)
        print("    Workflow completed successfully!")
        print(f"    Result status: {result.get('status')}")

        # Verify result
        assert result.get("status") == "completed", "Workflow should complete"
        assert result.get("synthesis") is not None, "Synthesis should be present"
        print("\n" + "=" * 60)
        print("SUCCESS: Crash recovery test passed!")
        print("=" * 60)
        print("\nThe workflow resumed after worker crash and completed successfully.")
        print("This validates Temporal's core durability guarantee.")

    except TimeoutError:
        print("    ERROR: Workflow did not complete within timeout")
        sys.exit(1)
    finally:
        # Cleanup worker
        try:
            os.kill(worker_process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
