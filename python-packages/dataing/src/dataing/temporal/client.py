"""Temporal client for interacting with investigation and agent workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temporalio.client import Client, WorkflowHandle
from temporalio.service import RPCError

from dataing.temporal.agents.protocol import AgentWorkflowInput, AgentWorkflowResult
from dataing.temporal.workflows.agent import AgentWorkflow, AgentWorkflowQueryStatus
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


@dataclass
class AgentWorkflowStatus:
    """Status of an agent workflow."""

    workflow_id: str
    run_id: str | None
    workflow_status: str  # Temporal workflow status
    session_id: str | None = None
    agent_name: str | None = None
    turn_count: int | None = None
    total_tokens: int | None = None
    last_response: str | None = None
    is_processing: bool = False


class TemporalAgentClient:
    """Client for interacting with agent workflows via Temporal.

    This client provides a high-level interface for:
    - Starting agent sessions (workflows)
    - Sending messages via signals
    - Querying session status
    - Getting responses

    Usage:
        client = await TemporalAgentClient.connect(
            host="localhost:7233",
            namespace="default",
            task_queue="investigations",
        )

        # Start or get agent session
        handle = await client.start_or_get_session(
            agent_name="dataing-assistant",
            session_id="sess-123",
            tenant_id="tenant-1",
        )

        # Send message
        await client.send_message("sess-123", "What's wrong with the data?")

        # Poll for response
        status = await client.get_status("sess-123")
    """

    def __init__(
        self,
        client: Client,
        task_queue: str = "investigations",
    ) -> None:
        """Initialize the Temporal agent client.

        Args:
            client: Temporal client connection.
            task_queue: Task queue for agent workflows.
        """
        self._client = client
        self._task_queue = task_queue

    @classmethod
    async def connect(
        cls,
        host: str = "localhost:7233",
        namespace: str = "default",
        task_queue: str = "investigations",
    ) -> TemporalAgentClient:
        """Connect to Temporal and create client.

        Args:
            host: Temporal server host.
            namespace: Temporal namespace.
            task_queue: Task queue for agent workflows.

        Returns:
            Connected TemporalAgentClient.
        """
        client = await Client.connect(target_host=host, namespace=namespace)
        return cls(client=client, task_queue=task_queue)

    def _workflow_id(self, session_id: str) -> str:
        """Generate workflow ID for a session.

        Args:
            session_id: Session ID.

        Returns:
            Workflow ID in format "assistant-{session_id}".
        """
        return f"assistant-{session_id}"

    async def start_session(
        self,
        agent_name: str,
        session_id: str,
        tenant_id: str,
        context: dict[str, Any] | None = None,
        initial_message: str | None = None,
    ) -> WorkflowHandle[AgentWorkflowResult, Any]:
        """Start a new agent session workflow.

        Args:
            agent_name: Name of the agent to use.
            session_id: Unique session ID.
            tenant_id: Tenant ID for multi-tenancy.
            context: Optional initial context.
            initial_message: Optional first message to process.

        Returns:
            Workflow handle for the session.
        """
        input_data = AgentWorkflowInput(
            agent_name=agent_name,
            session_id=session_id,
            tenant_id=tenant_id,
            context=context or {},
            initial_message=initial_message,
        )

        handle: WorkflowHandle[AgentWorkflowResult, Any] = await self._client.start_workflow(
            AgentWorkflow.run,
            input_data,
            id=self._workflow_id(session_id),
            task_queue=self._task_queue,
        )

        return handle

    async def get_handle(self, session_id: str) -> WorkflowHandle[AgentWorkflowResult, Any]:
        """Get a handle to an existing session workflow.

        Args:
            session_id: Session ID.

        Returns:
            Workflow handle for the session.
        """
        handle: WorkflowHandle[AgentWorkflowResult, Any] = self._client.get_workflow_handle(
            self._workflow_id(session_id),
            result_type=AgentWorkflowResult,
        )
        return handle

    async def workflow_exists(self, session_id: str) -> bool:
        """Check if a workflow exists for the session.

        Args:
            session_id: Session ID.

        Returns:
            True if workflow exists and is running.
        """
        try:
            handle = await self.get_handle(session_id)
            desc = await handle.describe()
            # Check if workflow is running
            status = desc.status
            if status is None:
                return False
            status_name = status.name if hasattr(status, "name") else str(status)
            return status_name == "RUNNING"
        except RPCError:
            return False

    async def start_or_get_session(
        self,
        agent_name: str,
        session_id: str,
        tenant_id: str,
        context: dict[str, Any] | None = None,
    ) -> WorkflowHandle[AgentWorkflowResult, Any]:
        """Start a new session or get existing one.

        Args:
            agent_name: Name of the agent to use.
            session_id: Unique session ID.
            tenant_id: Tenant ID for multi-tenancy.
            context: Optional context.

        Returns:
            Workflow handle for the session.
        """
        if await self.workflow_exists(session_id):
            return await self.get_handle(session_id)
        return await self.start_session(
            agent_name=agent_name,
            session_id=session_id,
            tenant_id=tenant_id,
            context=context,
        )

    async def send_message(self, session_id: str, message: str) -> None:
        """Send a message to an agent session.

        Args:
            session_id: Session ID.
            message: The user's message.
        """
        handle = await self.get_handle(session_id)
        await handle.signal(AgentWorkflow.send_message, message)

    async def update_context(self, session_id: str, context: dict[str, Any]) -> None:
        """Update the context for a session.

        Args:
            session_id: Session ID.
            context: Context to merge with existing context.
        """
        handle = await self.get_handle(session_id)
        await handle.signal(AgentWorkflow.update_context, context)

    async def complete_session(self, session_id: str) -> None:
        """Complete a session and end the workflow.

        Args:
            session_id: Session ID.
        """
        handle = await self.get_handle(session_id)
        await handle.signal(AgentWorkflow.complete_session)

    async def get_status(self, session_id: str) -> AgentWorkflowStatus:
        """Get the status of an agent session.

        Args:
            session_id: Session ID.

        Returns:
            Session status including workflow state and progress.
        """
        handle = await self.get_handle(session_id)
        desc = await handle.describe()

        # Map Temporal status
        status = desc.status
        if status is None:
            workflow_status = "unknown"
        else:
            status_name = status.name if hasattr(status, "name") else str(status)
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

        query_status: AgentWorkflowQueryStatus | None = None

        # If running, try to get detailed status via query
        if workflow_status == "running":
            try:
                query_status = await handle.query(AgentWorkflow.get_status)
            except Exception:
                pass

        return AgentWorkflowStatus(
            workflow_id=self._workflow_id(session_id),
            run_id=desc.run_id,
            workflow_status=workflow_status,
            session_id=query_status.session_id if query_status else None,
            agent_name=query_status.agent_name if query_status else None,
            turn_count=query_status.turn_count if query_status else None,
            total_tokens=query_status.total_tokens if query_status else None,
            last_response=query_status.last_response if query_status else None,
            is_processing=query_status.is_processing if query_status else False,
        )

    async def get_last_turn(self, session_id: str) -> dict[str, Any] | None:
        """Get the most recent turn from a session.

        Args:
            session_id: Session ID.

        Returns:
            Last turn dictionary or None if no turns yet.
        """
        handle = await self.get_handle(session_id)
        result: dict[str, Any] | None = await handle.query(AgentWorkflow.get_last_turn)
        return result

    async def wait_for_response(
        self,
        session_id: str,
        timeout_seconds: float = 300,
        poll_interval: float = 0.5,
    ) -> str | None:
        """Wait for the agent to finish processing and return the response.

        Args:
            session_id: Session ID.
            timeout_seconds: Maximum time to wait.
            poll_interval: Time between polls.

        Returns:
            The agent's response, or None if timeout.
        """
        import asyncio

        start_time = asyncio.get_event_loop().time()

        while True:
            status = await self.get_status(session_id)

            # If not processing and we have a response, return it
            if not status.is_processing and status.last_response:
                return status.last_response

            # Check for workflow completion or error
            if status.workflow_status in ("completed", "failed", "cancelled"):
                return status.last_response

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_seconds:
                return None

            await asyncio.sleep(poll_interval)
