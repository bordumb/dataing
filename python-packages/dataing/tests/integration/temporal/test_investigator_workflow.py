"""End-to-end tests for InvestigatorWorkflow with Rust state machine.

These tests verify the full Temporal + Rust state machine integration.
They require a running Temporal server at localhost:7233.

Run with: pytest -m temporal
Skip if Temporal unavailable: tests will be automatically skipped.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest

# Skip all tests if Temporal is not available
pytestmark = [
    pytest.mark.temporal,
    pytest.mark.skipif(
        os.environ.get("SKIP_TEMPORAL_TESTS", "1") == "1",
        reason="SKIP_TEMPORAL_TESTS=1 or Temporal server not available",
    ),
]

try:
    from temporalio.client import Client
    from temporalio.worker import Worker

    from investigator.temporal import (
        BrainStepInput,
        BrainStepOutput,
        InvestigatorInput,
        InvestigatorResult,
        InvestigatorStatus,
        InvestigatorWorkflow,
        brain_step,
    )

    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False
    Client = None  # type: ignore[misc, assignment]
    Worker = None  # type: ignore[misc, assignment]


TASK_QUEUE = "test-investigator-queue"


@pytest.fixture
async def temporal_client() -> Client:
    """Connect to Temporal server."""
    if not TEMPORAL_AVAILABLE:
        pytest.skip("temporalio not installed")

    try:
        client = await Client.connect("localhost:7233")
        return client
    except Exception as e:
        pytest.skip(f"Temporal server not available: {e}")


@pytest.fixture
async def worker(temporal_client: Client):
    """Start a worker for the test queue."""
    async with Worker(
        temporal_client,
        task_queue=TASK_QUEUE,
        workflows=[InvestigatorWorkflow],
        activities=[brain_step],
    ):
        yield


@pytest.fixture
def test_scope() -> dict[str, Any]:
    """Create a test scope."""
    return {
        "user_id": "test-user",
        "tenant_id": "test-tenant",
        "permissions": ["orders", "customers"],
    }


class TestInvestigatorWorkflowE2E:
    """End-to-end tests for the InvestigatorWorkflow."""

    @pytest.mark.asyncio
    async def test_full_investigation_lifecycle(
        self, temporal_client: Client, worker: None, test_scope: dict[str, Any]
    ) -> None:
        """Test complete investigation from start to finish."""
        workflow_id = f"test-investigation-{uuid.uuid4()}"

        handle = await temporal_client.start_workflow(
            InvestigatorWorkflow.run,
            InvestigatorInput(
                investigation_id=workflow_id,
                objective="Find the root cause of null spike in orders table",
                scope=test_scope,
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        # Wait for result with timeout
        result: InvestigatorResult = await asyncio.wait_for(
            handle.result(), timeout=60.0
        )

        # Verify result
        assert result.investigation_id == workflow_id
        assert result.status == "completed"
        assert result.insight is not None
        assert result.steps > 0
        assert result.trace_id != ""

    @pytest.mark.asyncio
    async def test_query_status(
        self, temporal_client: Client, worker: None, test_scope: dict[str, Any]
    ) -> None:
        """Test querying workflow status."""
        workflow_id = f"test-query-{uuid.uuid4()}"

        handle = await temporal_client.start_workflow(
            InvestigatorWorkflow.run,
            InvestigatorInput(
                investigation_id=workflow_id,
                objective="Test status query",
                scope=test_scope,
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        # Query status while running
        await asyncio.sleep(0.1)  # Give workflow time to start
        status: InvestigatorStatus = await handle.query(
            InvestigatorWorkflow.get_status
        )

        assert status.investigation_id == workflow_id
        assert status.step >= 0
        assert not status.is_terminal  # Should still be running

        # Wait for completion
        await asyncio.wait_for(handle.result(), timeout=60.0)

    @pytest.mark.asyncio
    async def test_cancel_signal(
        self, temporal_client: Client, worker: None, test_scope: dict[str, Any]
    ) -> None:
        """Test cancelling investigation via signal."""
        workflow_id = f"test-cancel-{uuid.uuid4()}"

        handle = await temporal_client.start_workflow(
            InvestigatorWorkflow.run,
            InvestigatorInput(
                investigation_id=workflow_id,
                objective="Test cancellation",
                scope=test_scope,
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        # Give workflow time to start
        await asyncio.sleep(0.1)

        # Send cancel signal
        await handle.signal(InvestigatorWorkflow.cancel)

        # Wait for result
        result: InvestigatorResult = await asyncio.wait_for(
            handle.result(), timeout=10.0
        )

        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_deterministic_replay(
        self, temporal_client: Client, worker: None, test_scope: dict[str, Any]
    ) -> None:
        """Verify workflow replays deterministically.

        This test runs the same workflow twice and verifies consistent results.
        Temporal's replay mechanism ensures deterministic execution.
        """
        # First run
        workflow_id_1 = f"test-replay-1-{uuid.uuid4()}"
        handle_1 = await temporal_client.start_workflow(
            InvestigatorWorkflow.run,
            InvestigatorInput(
                investigation_id=workflow_id_1,
                objective="Deterministic test",
                scope=test_scope,
            ),
            id=workflow_id_1,
            task_queue=TASK_QUEUE,
        )
        result_1: InvestigatorResult = await asyncio.wait_for(
            handle_1.result(), timeout=60.0
        )

        # Second run with same input
        workflow_id_2 = f"test-replay-2-{uuid.uuid4()}"
        handle_2 = await temporal_client.start_workflow(
            InvestigatorWorkflow.run,
            InvestigatorInput(
                investigation_id=workflow_id_2,
                objective="Deterministic test",
                scope=test_scope,
            ),
            id=workflow_id_2,
            task_queue=TASK_QUEUE,
        )
        result_2: InvestigatorResult = await asyncio.wait_for(
            handle_2.result(), timeout=60.0
        )

        # Both should complete with same status
        assert result_1.status == result_2.status == "completed"
        # Same number of steps (deterministic)
        assert result_1.steps == result_2.steps
        # Same insight (deterministic state machine)
        assert result_1.insight == result_2.insight


class TestBrainStepActivity:
    """Unit tests for the brain_step activity."""

    @pytest.mark.asyncio
    async def test_brain_step_new_investigator(self) -> None:
        """Test brain_step with new investigator."""
        if not TEMPORAL_AVAILABLE:
            pytest.skip("temporalio not installed")

        import json

        start_event = json.dumps({
            "type": "Start",
            "payload": {
                "objective": "Test",
                "scope": {
                    "user_id": "u1",
                    "tenant_id": "t1",
                    "permissions": [],
                },
            },
        })

        input_data = BrainStepInput(state_json=None, event_json=start_event)

        # Call activity directly (not through Temporal)
        result = await brain_step(input_data)

        assert result.new_state_json is not None
        assert result.intent["type"] == "Call"
        assert result.intent["payload"]["name"] == "get_schema"

    @pytest.mark.asyncio
    async def test_brain_step_restore_and_continue(self) -> None:
        """Test brain_step with restored state."""
        if not TEMPORAL_AVAILABLE:
            pytest.skip("temporalio not installed")

        import json

        # First step to get initial state
        start_event = json.dumps({
            "type": "Start",
            "payload": {
                "objective": "Test",
                "scope": {"user_id": "u1", "tenant_id": "t1", "permissions": []},
            },
        })

        result1 = await brain_step(BrainStepInput(state_json=None, event_json=start_event))
        call_id = result1.intent["payload"]["call_id"]

        # Second step with CallResult
        call_result_event = json.dumps({
            "type": "CallResult",
            "payload": {
                "call_id": call_id,
                "output": {"tables": [{"name": "orders"}]},
            },
        })

        result2 = await brain_step(
            BrainStepInput(
                state_json=result1.new_state_json,
                event_json=call_result_event,
            )
        )

        # Should progress to next phase
        assert result2.intent["type"] == "Call"
        assert result2.intent["payload"]["name"] == "generate_hypotheses"


class TestSignalDeduplication:
    """Test signal deduplication in the workflow."""

    @pytest.mark.asyncio
    async def test_duplicate_signals_ignored(
        self, temporal_client: Client, worker: None, test_scope: dict[str, Any]
    ) -> None:
        """Test that duplicate signals are ignored."""
        workflow_id = f"test-dedup-{uuid.uuid4()}"

        handle = await temporal_client.start_workflow(
            InvestigatorWorkflow.run,
            InvestigatorInput(
                investigation_id=workflow_id,
                objective="Test deduplication",
                scope=test_scope,
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        # Send the same signal multiple times with same ID
        signal_id = f"sig-{uuid.uuid4()}"
        await handle.signal(
            InvestigatorWorkflow.user_response, signal_id, "response-1"
        )
        await handle.signal(
            InvestigatorWorkflow.user_response, signal_id, "response-2"
        )
        await handle.signal(
            InvestigatorWorkflow.user_response, signal_id, "response-3"
        )

        # Cancel to end the workflow
        await handle.signal(InvestigatorWorkflow.cancel)

        result: InvestigatorResult = await asyncio.wait_for(
            handle.result(), timeout=10.0
        )

        # Workflow should complete (was cancelled)
        assert result.status == "cancelled"
