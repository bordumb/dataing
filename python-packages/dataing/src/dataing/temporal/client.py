"""Temporal client for interacting with investigation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temporalio.client import Client

from dataing.temporal.workflows.investigation import (
    InvestigationInput,
    InvestigationQueryStatus,
    InvestigationResult,
    InvestigationWorkflow,
)


@dataclass
class InvestigationStatus:
    """Status of an investigation workflow."""

    workflow_id: str
    run_id: str | None
    workflow_status: str  # Temporal workflow status
    result: InvestigationResult | None = None
    # Query-level status (only available for running workflows)
    current_step: str | None = None
    progress: float | None = None
    is_complete: bool | None = None
    is_cancelled: bool | None = None
    is_awaiting_user: bool | None = None
    hypotheses_count: int | None = None
    hypotheses_evaluated: int | None = None
    evidence_count: int | None = None


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

        Queries the workflow for detailed progress information if running,
        or returns the final result if completed.

        Args:
            investigation_id: ID of the investigation.

        Returns:
            Investigation status including workflow state and progress.
        """
        handle = await self.get_handle(investigation_id)
        desc = await handle.describe()

        # Map Temporal status to our status
        # desc.status is a WorkflowExecutionStatus enum, get its name
        status_name = desc.status.name if hasattr(desc.status, "name") else str(desc.status)
        status_map = {
            "RUNNING": "running",
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CANCELED": "cancelled",
            "CANCELLED": "cancelled",
            "TERMINATED": "terminated",
            "TIMED_OUT": "timed_out",
        }
        workflow_status = status_map.get(status_name, "unknown")

        result = None
        query_status: InvestigationQueryStatus | None = None

        # If running, try to get detailed status via query
        if workflow_status == "running":
            try:
                query_status = await handle.query(InvestigationWorkflow.get_status)
            except Exception:
                # Query failed, continue with basic status
                pass

        # If completed, get the result
        if workflow_status == "completed":
            try:
                result = await handle.result()
            except Exception:
                pass

        return InvestigationStatus(
            workflow_id=investigation_id,
            run_id=desc.run_id,
            workflow_status=workflow_status,
            result=result,
            current_step=query_status.current_step if query_status else None,
            progress=query_status.progress if query_status else None,
            is_complete=query_status.is_complete if query_status else None,
            is_cancelled=query_status.is_cancelled if query_status else None,
            is_awaiting_user=query_status.is_awaiting_user if query_status else None,
            hypotheses_count=query_status.hypotheses_count if query_status else None,
            hypotheses_evaluated=query_status.hypotheses_evaluated if query_status else None,
            evidence_count=query_status.evidence_count if query_status else None,
        )

    async def query_status(self, investigation_id: str) -> InvestigationQueryStatus:
        """Query the detailed status of a running investigation.

        This method only works on running workflows. For completed workflows,
        use get_status() or get_result() instead.

        Args:
            investigation_id: ID of the investigation.

        Returns:
            Detailed status including current step, progress, and counts.

        Raises:
            WorkflowNotFoundError: If the workflow doesn't exist.
            QueryRejectedError: If the workflow is not running.
        """
        handle = await self.get_handle(investigation_id)
        status: InvestigationQueryStatus = await handle.query(InvestigationWorkflow.get_status)
        return status
