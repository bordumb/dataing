"""Temporal workflow integration for the Rust state machine.

This module provides Temporal workflow and activity definitions that use
the Rust Investigator state machine for durable, deterministic execution.

Example usage:
    ```python
    from investigator.temporal import (
        InvestigatorWorkflow,
        InvestigatorInput,
        brain_step,
    )

    # Register workflow and activity with worker
    worker = Worker(
        client,
        task_queue="investigator",
        workflows=[InvestigatorWorkflow],
        activities=[brain_step],
    )
    ```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from dataing_investigator import Investigator
    from investigator.security import SecurityViolation, validate_tool_call


# === Activity Definitions ===


@dataclass
class BrainStepInput:
    """Input for the brain_step activity."""

    state_json: str | None
    event_json: str


@dataclass
class BrainStepOutput:
    """Output from the brain_step activity."""

    new_state_json: str
    intent: dict[str, Any]


@activity.defn
async def brain_step(input: BrainStepInput) -> BrainStepOutput:
    """Execute one step of the state machine.

    This activity is the core of the investigation loop. It:
    1. Restores state from JSON (or creates new state)
    2. Ingests the event
    3. Returns the new state and intent

    The activity is pure computation - no side effects.
    Side effects (tool calls) happen in the workflow.
    """
    if input.state_json:
        inv = Investigator.restore(input.state_json)
    else:
        inv = Investigator()

    intent_json = inv.ingest(input.event_json)

    return BrainStepOutput(
        new_state_json=inv.snapshot(),
        intent=json.loads(intent_json),
    )


# === Workflow Definitions ===


@dataclass
class InvestigatorInput:
    """Input for starting an investigator workflow."""

    investigation_id: str
    objective: str
    scope: dict[str, Any]
    # For continue_as_new resumption
    checkpoint_state: str | None = None
    checkpoint_step: int = 0


@dataclass
class InvestigatorResult:
    """Result of a completed investigation."""

    investigation_id: str
    status: str  # "completed", "failed", "cancelled"
    insight: str | None = None
    error: str | None = None
    steps: int = 0
    trace_id: str = ""


@dataclass
class InvestigatorStatus:
    """Status returned by the get_status query."""

    investigation_id: str
    phase: str
    step: int
    is_terminal: bool
    awaiting_user: bool
    current_question: str | None


@workflow.defn
class InvestigatorWorkflow:
    """Temporal workflow using the Rust Investigator state machine.

    This workflow demonstrates the integration pattern:
    - State machine logic runs in activities (pure computation)
    - Tool execution happens in the workflow (side effects)
    - HITL via signals/queries
    - Signal dedup via seen_signal_ids
    - continue_as_new at step threshold

    Signals:
    - user_response(signal_id, content): Submit user response
    - cancel(): Cancel the investigation

    Queries:
    - get_status(): Get current investigation status
    """

    # Step threshold for continue_as_new
    MAX_STEPS_BEFORE_CONTINUE = 100

    def __init__(self) -> None:
        """Initialize workflow state."""
        self._state_json: str | None = None
        self._current_phase = "init"
        self._step = 0
        self._is_terminal = False
        self._awaiting_user = False
        self._current_question: str | None = None
        self._user_response_queue: list[str] = []
        self._seen_signal_ids: set[str] = set()
        self._cancelled = False
        self._investigation_id = ""
        self._trace_id = ""

    @workflow.signal
    def user_response(self, signal_id: str, content: str) -> None:
        """Signal to submit a user response.

        Uses signal_id for deduplication - duplicate signals are ignored.

        Args:
            signal_id: Unique ID for this signal (for dedup).
            content: User's response content.
        """
        if signal_id in self._seen_signal_ids:
            workflow.logger.info(f"Ignoring duplicate signal: {signal_id}")
            return
        self._seen_signal_ids.add(signal_id)
        self._user_response_queue.append(content)

    @workflow.signal
    def cancel(self) -> None:
        """Signal to cancel the investigation."""
        self._cancelled = True

    @workflow.query
    def get_status(self) -> InvestigatorStatus:
        """Query the current status of the investigation."""
        return InvestigatorStatus(
            investigation_id=self._investigation_id,
            phase=self._current_phase,
            step=self._step,
            is_terminal=self._is_terminal,
            awaiting_user=self._awaiting_user,
            current_question=self._current_question,
        )

    @workflow.run
    async def run(self, input: InvestigatorInput) -> InvestigatorResult:
        """Execute the investigation workflow.

        Args:
            input: Investigation input with objective and scope.

        Returns:
            InvestigatorResult with status and findings.
        """
        self._investigation_id = input.investigation_id
        self._trace_id = str(workflow.uuid4())

        # Restore from checkpoint if continuing
        if input.checkpoint_state:
            self._state_json = input.checkpoint_state
            self._step = input.checkpoint_step

        # Build Start event (only if not resuming)
        if not input.checkpoint_state:
            start_event = json.dumps({
                "type": "Start",
                "payload": {
                    "objective": input.objective,
                    "scope": input.scope,
                },
            })
        else:
            start_event = None

        # Run the investigation loop
        while not self._is_terminal and not self._cancelled:
            # Check for continue_as_new threshold
            if self._step >= self.MAX_STEPS_BEFORE_CONTINUE + input.checkpoint_step:
                workflow.logger.info(
                    f"Step threshold reached ({self._step}), continuing as new"
                )
                workflow.continue_as_new(
                    InvestigatorInput(
                        investigation_id=input.investigation_id,
                        objective=input.objective,
                        scope=input.scope,
                        checkpoint_state=self._state_json,
                        checkpoint_step=self._step,
                    )
                )

            # Execute brain step
            step_input = BrainStepInput(
                state_json=self._state_json,
                event_json=start_event if start_event else "null",
            )
            step_output = await workflow.execute_activity(
                brain_step,
                step_input,
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Clear start_event after first iteration
            start_event = None

            # Update local state
            self._state_json = step_output.new_state_json
            self._step += 1
            intent = step_output.intent

            # Update phase from state
            state = json.loads(self._state_json)
            self._current_phase = state.get("phase", {}).get("type", "unknown").lower()

            # Handle intent
            if intent["type"] == "Idle":
                # Need to wait for something - this shouldn't happen often
                await workflow.sleep(timedelta(milliseconds=100))

            elif intent["type"] == "Call":
                # Execute tool call
                result = await self._execute_tool_call(intent["payload"], input.scope)

                # Build CallResult event
                call_result_event = json.dumps({
                    "type": "CallResult",
                    "payload": {
                        "call_id": intent["payload"]["call_id"],
                        "output": result,
                    },
                })

                # Feed result back to state machine
                step_input = BrainStepInput(
                    state_json=self._state_json,
                    event_json=call_result_event,
                )
                step_output = await workflow.execute_activity(
                    brain_step,
                    step_input,
                    start_to_close_timeout=timedelta(seconds=30),
                )
                self._state_json = step_output.new_state_json
                self._step += 1

            elif intent["type"] == "RequestUser":
                # Enter HITL mode
                self._awaiting_user = True
                self._current_question = intent["payload"]["question"]

                # Wait for user response or cancellation
                await workflow.wait_condition(
                    lambda: len(self._user_response_queue) > 0 or self._cancelled,
                    timeout=timedelta(hours=24),
                )

                if self._cancelled:
                    break

                # Get response and build event
                response = self._user_response_queue.pop(0)
                user_response_event = json.dumps({
                    "type": "UserResponse",
                    "payload": {"content": response},
                })

                # Feed response back to state machine
                step_input = BrainStepInput(
                    state_json=self._state_json,
                    event_json=user_response_event,
                )
                step_output = await workflow.execute_activity(
                    brain_step,
                    step_input,
                    start_to_close_timeout=timedelta(seconds=30),
                )
                self._state_json = step_output.new_state_json
                self._step += 1

                self._awaiting_user = False
                self._current_question = None

            elif intent["type"] == "Finish":
                self._is_terminal = True
                return InvestigatorResult(
                    investigation_id=input.investigation_id,
                    status="completed",
                    insight=intent["payload"]["insight"],
                    steps=self._step,
                    trace_id=self._trace_id,
                )

            elif intent["type"] == "Error":
                self._is_terminal = True
                return InvestigatorResult(
                    investigation_id=input.investigation_id,
                    status="failed",
                    error=intent["payload"]["message"],
                    steps=self._step,
                    trace_id=self._trace_id,
                )

        # Cancelled
        return InvestigatorResult(
            investigation_id=input.investigation_id,
            status="cancelled",
            steps=self._step,
            trace_id=self._trace_id,
        )

    async def _execute_tool_call(
        self,
        payload: dict[str, Any],
        scope: dict[str, Any],
    ) -> Any:
        """Execute a tool call with security validation.

        Args:
            payload: The Call intent payload.
            scope: Security scope.

        Returns:
            Tool execution result.

        Raises:
            SecurityViolation: If call violates security policy.
        """
        tool_name = payload["name"]
        args = payload["args"]

        # Security validation before execution
        try:
            validate_tool_call(tool_name, args, scope)
        except SecurityViolation as e:
            workflow.logger.warning(f"Security violation: {e}")
            return {"error": str(e)}

        # Execute tool based on name
        # In production, this would dispatch to actual tool implementations
        if tool_name == "get_schema":
            # Mock schema gathering
            return await self._mock_get_schema(args)
        elif tool_name == "generate_hypotheses":
            # Mock hypothesis generation
            return await self._mock_generate_hypotheses(args)
        elif tool_name == "evaluate_hypothesis":
            # Mock hypothesis evaluation
            return await self._mock_evaluate_hypothesis(args)
        elif tool_name == "synthesize":
            # Mock synthesis
            return await self._mock_synthesize(args)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _mock_get_schema(self, args: dict[str, Any]) -> dict[str, Any]:
        """Mock schema gathering tool."""
        return {
            "tables": [
                {"name": "orders", "columns": ["id", "customer_id", "amount", "created_at"]}
            ]
        }

    async def _mock_generate_hypotheses(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        """Mock hypothesis generation tool."""
        return [
            {"id": "h1", "title": "ETL job failure", "reasoning": "Upstream ETL may have failed"},
            {"id": "h2", "title": "Schema change", "reasoning": "A column type may have changed"},
        ]

    async def _mock_evaluate_hypothesis(self, args: dict[str, Any]) -> dict[str, Any]:
        """Mock hypothesis evaluation tool."""
        return {"supported": True, "confidence": 0.85}

    async def _mock_synthesize(self, args: dict[str, Any]) -> dict[str, Any]:
        """Mock synthesis tool."""
        return {"insight": "Root cause: ETL job failed at 3:00 AM due to timeout"}
