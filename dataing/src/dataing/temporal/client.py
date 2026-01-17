"""Temporal client for interacting with investigation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temporalio.client import Client

from dataing.temporal.workflows.investigation import (
    InvestigationInput,
    InvestigationResult,
    InvestigationWorkflow,
)


@dataclass
class InvestigationStatus:
    """Status of an investigation workflow."""

    workflow_id: str
    run_id: str | None
    status: str
    result: InvestigationResult | None = None


class TemporalInvestigationClient:
    """Client for interacting with investigation workflows via Temporal.

    This client provides a high-level interface for:
    - Starting investigations
    - Cancelling investigations
    - Sending user input signals
    - Querying investigation status

    Usage:
        client = await TemporalInvestigationClient.connect(
            host="localhost:7233",
            namespace="default",
            task_queue="investigations",
        )

        # Start investigation
        handle = await client.start_investigation(
            investigation_id="inv-123",
            tenant_id="tenant-1",
            datasource_id="ds-1",
            alert_data={"type": "null_spike", "table": "orders"},
        )

        # Cancel if needed
        await client.cancel_investigation("inv-123")

        # Send user input
        await client.send_user_input("inv-123", {"feedback": "..."})
    """

    def __init__(
        self,
        client: Client,
        task_queue: str = "investigations",
    ) -> None:
        """Initialize the Temporal investigation client.

        Args:
            client: Temporal client connection.
            task_queue: Task queue for investigation workflows.
        """
        self._client = client
        self._task_queue = task_queue

    @classmethod
    async def connect(
        cls,
        host: str = "localhost:7233",
        namespace: str = "default",
        task_queue: str = "investigations",
    ) -> TemporalInvestigationClient:
        """Connect to Temporal and create client.

        Args:
            host: Temporal server host.
            namespace: Temporal namespace.
            task_queue: Task queue for investigation workflows.

        Returns:
            Connected TemporalInvestigationClient.
        """
        client = await Client.connect(target_host=host, namespace=namespace)
        return cls(client=client, task_queue=task_queue)

    async def start_investigation(
        self,
        investigation_id: str,
        tenant_id: str,
        datasource_id: str,
        alert_data: dict[str, Any],
        alert_summary: str = "",
        max_hypotheses: int = 5,
        confidence_threshold: float = 0.85,
    ) -> Any:
        """Start a new investigation workflow.

        Args:
            investigation_id: Unique ID for the investigation.
            tenant_id: Tenant ID for multi-tenancy.
            datasource_id: Data source to investigate.
            alert_data: Alert data that triggered the investigation.
            alert_summary: Human-readable summary of the alert.
            max_hypotheses: Maximum hypotheses to generate.
            confidence_threshold: Confidence threshold for counter-analysis.

        Returns:
            Workflow handle for tracking and interacting with the investigation.
        """
        input_data = InvestigationInput(
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            alert_data=alert_data,
            alert_summary=alert_summary,
            max_hypotheses=max_hypotheses,
            confidence_threshold=confidence_threshold,
        )

        handle = await self._client.start_workflow(
            InvestigationWorkflow.run,
            input_data,
            id=investigation_id,
            task_queue=self._task_queue,
        )

        return handle

    async def get_handle(self, investigation_id: str) -> Any:
        """Get a handle to an existing investigation workflow.

        Args:
            investigation_id: ID of the investigation.

        Returns:
            Workflow handle for the investigation.
        """
        return self._client.get_workflow_handle(
            investigation_id,
            result_type=InvestigationResult,
        )

    async def cancel_investigation(self, investigation_id: str) -> None:
        """Cancel an investigation.

        Sends the cancel_investigation signal to the workflow, which will
        gracefully stop the investigation and return a cancelled result.

        Args:
            investigation_id: ID of the investigation to cancel.
        """
        handle = await self.get_handle(investigation_id)
        await handle.signal(InvestigationWorkflow.cancel_investigation)

    async def send_user_input(
        self,
        investigation_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Send user input to an investigation awaiting feedback.

        Args:
            investigation_id: ID of the investigation.
            payload: User feedback data (e.g., {"feedback": "...", "action": "..."}).
        """
        handle = await self.get_handle(investigation_id)
        await handle.signal(InvestigationWorkflow.user_input, payload)

    async def get_result(self, investigation_id: str) -> InvestigationResult:
        """Get the result of a completed investigation.

        Args:
            investigation_id: ID of the investigation.

        Returns:
            Investigation result.

        Raises:
            WorkflowFailureError: If the workflow failed.
        """
        handle = await self.get_handle(investigation_id)
        result: InvestigationResult = await handle.result()
        return result

    async def get_status(self, investigation_id: str) -> InvestigationStatus:
        """Get the status of an investigation.

        Args:
            investigation_id: ID of the investigation.

        Returns:
            Investigation status including workflow state.
        """
        handle = await self.get_handle(investigation_id)
        desc = await handle.describe()

        # Map Temporal status to our status
        status_map = {
            "RUNNING": "running",
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CANCELED": "cancelled",
            "TERMINATED": "terminated",
            "TIMED_OUT": "timed_out",
        }
        status = status_map.get(str(desc.status), "unknown")

        result = None
        if status == "completed":
            try:
                result = await handle.result()
            except Exception:
                pass

        return InvestigationStatus(
            workflow_id=investigation_id,
            run_id=desc.run_id,
            status=status,
            result=result,
        )
