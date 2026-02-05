"""Generic agent workflow for Temporal execution.

This workflow provides a unified way to run any registered agent through Temporal,
with signals for message passing and queries for status monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from dataing.temporal.activities.agent_turn import AgentTurnActivityInput
    from dataing.temporal.agents.protocol import (
        AgentTurnResult,
        AgentWorkflowInput,
        AgentWorkflowResult,
    )


@dataclass
class AgentWorkflowQueryStatus:
    """Status returned by the get_status query."""

    session_id: str
    agent_name: str
    status: str  # "waiting", "processing", "complete", "error"
    turn_count: int
    total_tokens: int
    last_response: str | None
    is_processing: bool


@workflow.defn
class AgentWorkflow:
    """Generic workflow for running any registered agent.

    This workflow:
    1. Waits for messages via signal
    2. Executes agent turns via the agent_turn activity
    3. Tracks conversation state and tokens
    4. Supports status queries

    Usage:
        # Start workflow
        handle = await client.start_workflow(
            AgentWorkflow.run,
            AgentWorkflowInput(
                agent_name="dataing-assistant",
                session_id="sess-123",
                tenant_id="tenant-456",
            ),
            id="assistant-sess-123",
            task_queue="investigations",
        )

        # Send message via signal
        await handle.signal(AgentWorkflow.send_message, "What's wrong?")

        # Query status
        status = await handle.query(AgentWorkflow.get_status)
    """

    def __init__(self) -> None:
        """Initialize workflow state."""
        self._turns: list[dict[str, Any]] = []
        self._status = "waiting"
        self._pending_message: str | None = None
        self._total_tokens = 0
        self._last_response: str | None = None
        self._is_processing = False
        self._session_id = ""
        self._agent_name = ""
        self._tenant_id = ""
        self._context: dict[str, Any] = {}

    @workflow.signal
    def send_message(self, message: str) -> None:
        """Signal to send a new message to the agent.

        Args:
            message: The user's message to process.
        """
        workflow.logger.info(f"Received message signal: {message[:100]}...")
        self._pending_message = message

    @workflow.signal
    def update_context(self, context: dict[str, Any]) -> None:
        """Signal to update the workflow context.

        Args:
            context: New context to merge with existing context.
        """
        self._context.update(context)
        workflow.logger.info(f"Context updated with keys: {list(context.keys())}")

    @workflow.signal
    def complete_session(self) -> None:
        """Signal to complete the session and end the workflow."""
        workflow.logger.info("Received complete_session signal")
        self._status = "complete"

    @workflow.query
    def get_status(self) -> AgentWorkflowQueryStatus:
        """Query current workflow status.

        Returns:
            AgentWorkflowQueryStatus with current state.
        """
        return AgentWorkflowQueryStatus(
            session_id=self._session_id,
            agent_name=self._agent_name,
            status=self._status,
            turn_count=len(self._turns),
            total_tokens=self._total_tokens,
            last_response=self._last_response,
            is_processing=self._is_processing,
        )

    @workflow.query
    def get_turns(self) -> list[dict[str, Any]]:
        """Query all recorded turns.

        Returns:
            List of turn dictionaries.
        """
        return self._turns

    @workflow.query
    def get_last_turn(self) -> dict[str, Any] | None:
        """Query the most recent turn.

        Returns:
            Last turn dictionary or None if no turns yet.
        """
        return self._turns[-1] if self._turns else None

    @workflow.run
    async def run(self, input: AgentWorkflowInput) -> AgentWorkflowResult:
        """Execute the agent workflow.

        This workflow runs a loop that:
        1. Waits for a message signal
        2. Executes an agent turn
        3. Records the result
        4. Repeats until complete

        Args:
            input: Workflow input with agent name and session info.

        Returns:
            AgentWorkflowResult with all turns and totals.
        """
        self._session_id = input.session_id
        self._agent_name = input.agent_name
        self._tenant_id = input.tenant_id
        self._context = input.context.copy() if input.context else {}
        self._status = "waiting"

        workflow.logger.info(
            f"Starting agent workflow: agent={input.agent_name}, session={input.session_id}"
        )

        # Process initial message if provided
        if input.initial_message:
            self._pending_message = input.initial_message

        # Main processing loop
        while self._status not in ("complete", "error"):
            # Wait for a message or completion signal
            await workflow.wait_condition(
                lambda: self._pending_message is not None or self._status == "complete"
            )

            # Check if we should exit
            if self._status == "complete":
                break

            # Get the pending message
            message = self._pending_message
            self._pending_message = None

            if message is None:
                continue

            # Process the message
            self._is_processing = True
            self._status = "processing"

            try:
                # Execute agent turn via activity
                activity_input = AgentTurnActivityInput(
                    agent_name=self._agent_name,
                    message=message,
                    session_id=self._session_id,
                    context=self._context,
                    tenant_id=self._tenant_id,
                )

                result_dict = await workflow.execute_activity(
                    "agent_turn",
                    activity_input,
                    start_to_close_timeout=timedelta(minutes=5),
                    heartbeat_timeout=timedelta(minutes=2),
                )

                # Parse result
                result = AgentTurnResult.from_dict(result_dict)

                # Record the turn
                turn_record = {
                    "message": message,
                    "response": result.response,
                    "tool_calls": [tc.to_dict() for tc in result.tool_calls],
                    "tokens_used": result.tokens_used,
                    "is_complete": result.is_complete,
                }
                self._turns.append(turn_record)
                self._total_tokens += result.tokens_used
                self._last_response = result.response

                workflow.logger.info(
                    f"Turn completed: turn={len(self._turns)}, tokens={result.tokens_used}"
                )

                # Check if agent signals completion
                if result.is_complete:
                    self._status = "complete"
                else:
                    self._status = "waiting"

            except Exception as e:
                workflow.logger.error(f"Agent turn failed: {e}")
                self._status = "error"
                self._turns.append(
                    {
                        "message": message,
                        "error": str(e),
                    }
                )

            finally:
                self._is_processing = False

        workflow.logger.info(
            f"Agent workflow completed: turns={len(self._turns)}, tokens={self._total_tokens}"
        )

        return AgentWorkflowResult(
            session_id=self._session_id,
            turns=self._turns,
            total_tokens=self._total_tokens,
            status=self._status,
        )
