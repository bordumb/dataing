"""Runtime module for local investigation execution.

Provides a local execution loop for running investigations outside of Temporal.
Useful for testing and simple deployments.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, TypeVar

from dataing_investigator import Investigator, protocol_version

from .envelope import create_trace
from .security import validate_tool_call

# Type alias for tool executor function
ToolExecutor = Callable[[str, dict[str, Any]], Any]
UserResponder = Callable[[str, str], str]  # (question_id, prompt) -> response

T = TypeVar("T")


class InvestigationError(Exception):
    """Raised when an investigation fails."""

    pass


class EnvelopeBuilder:
    """Builds event envelopes with monotonically increasing steps."""

    def __init__(self) -> None:
        """Initialize envelope builder."""
        self._step = 0

    def build(self, event: dict[str, Any]) -> str:
        """Build an envelope for the given event.

        Args:
            event: The event payload.

        Returns:
            JSON string of the envelope.
        """
        self._step += 1
        envelope = {
            "protocol_version": protocol_version(),
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "step": self._step,
            "event": event,
        }
        return json.dumps(envelope)


async def run_local(
    objective: str,
    scope: dict[str, Any],
    tool_executor: ToolExecutor,
    user_responder: UserResponder | None = None,
    max_steps: int = 100,
) -> dict[str, Any]:
    """Run an investigation locally (not in Temporal).

    This provides a simple execution loop for running investigations
    without the overhead of Temporal. Useful for:
    - Local testing and development
    - Simple deployments without durability requirements
    - Debugging investigation logic

    Args:
        objective: The investigation objective/description.
        scope: Security scope with user_id, tenant_id, permissions.
        tool_executor: Async function to execute tool calls.
            Signature: (tool_name: str, args: dict) -> Any
        user_responder: Optional function to get user responses for HITL.
            Signature: (question_id: str, prompt: str) -> str
            If None and user response is needed, raises RuntimeError.
        max_steps: Maximum number of steps before aborting (prevents infinite loops).

    Returns:
        Final investigation result from the Finish intent.

    Raises:
        InvestigationError: If investigation fails or max_steps exceeded.
        SecurityViolation: If a tool call violates security policy.
        RuntimeError: If user response needed but no responder provided.
    """
    inv = Investigator()
    trace_id = create_trace()
    envelope_builder = EnvelopeBuilder()

    # Build and send Start event
    start_event = {"type": "Start", "payload": {"objective": objective, "scope": scope}}
    envelope = envelope_builder.build(start_event)
    intent = _ingest_and_parse(inv, envelope)

    loop_count = 0
    while loop_count < max_steps:
        loop_count += 1

        if intent["type"] == "Idle":
            # State machine waiting - query without event
            intent = json.loads(inv.query())

        elif intent["type"] == "RequestCall":
            payload = intent["payload"]
            tool_name = payload["name"]
            args = payload["args"]

            # Generate a call_id and send CallScheduled
            call_id = f"call_{uuid.uuid4().hex[:12]}"
            scheduled_event = {
                "type": "CallScheduled",
                "payload": {"call_id": call_id, "name": tool_name},
            }
            envelope = envelope_builder.build(scheduled_event)
            intent = _ingest_and_parse(inv, envelope)

            # Should return Idle, now execute the tool
            if intent["type"] != "Idle":
                raise InvestigationError(
                    f"Expected Idle after CallScheduled, got {intent['type']}"
                )

            # Security validation before execution
            validate_tool_call(tool_name, args, scope)

            # Execute tool
            try:
                result = await tool_executor(tool_name, args)
            except Exception as e:
                # Tool execution failed - send error result
                result = {"error": str(e)}

            # Send CallResult event
            call_result_event = {
                "type": "CallResult",
                "payload": {"call_id": call_id, "output": result},
            }
            envelope = envelope_builder.build(call_result_event)
            intent = _ingest_and_parse(inv, envelope)

        elif intent["type"] == "RequestUser":
            payload = intent["payload"]
            question_id = payload["question_id"]
            prompt = payload["prompt"]

            if user_responder is None:
                raise RuntimeError(
                    f"User response required but no responder provided. Prompt: {prompt}"
                )

            # Get user response
            response = user_responder(question_id, prompt)

            # Send UserResponse event
            user_response_event = {
                "type": "UserResponse",
                "payload": {"question_id": question_id, "content": response},
            }
            envelope = envelope_builder.build(user_response_event)
            intent = _ingest_and_parse(inv, envelope)

        elif intent["type"] == "Finish":
            # Success - return the insight
            return {
                "status": "completed",
                "insight": intent["payload"]["insight"],
                "steps": loop_count,
                "trace_id": trace_id,
            }

        elif intent["type"] == "Error":
            # Investigation failed
            raise InvestigationError(intent["payload"]["message"])

        else:
            raise InvestigationError(f"Unknown intent type: {intent['type']}")

    raise InvestigationError(f"Investigation exceeded max_steps ({max_steps})")


def _ingest_and_parse(inv: Investigator, envelope_json: str) -> dict[str, Any]:
    """Ingest an envelope and parse the resulting intent.

    Args:
        inv: The Investigator instance.
        envelope_json: JSON string of the envelope.

    Returns:
        Parsed intent dictionary.
    """
    intent_json = inv.ingest(envelope_json)
    result: dict[str, Any] = json.loads(intent_json)
    return result


class LocalInvestigator:
    """Wrapper providing stateful investigation control.

    For more fine-grained control over the investigation loop,
    use this class instead of run_local().

    Example:
        >>> inv = LocalInvestigator()
        >>> intent = inv.start("Find null spike", scope)
        >>> while not inv.is_terminal:
        ...     intent = inv.current_intent()
        ...     if intent["type"] == "RequestCall":
        ...         call_id = inv.schedule_call(intent["payload"]["name"])
        ...         result = execute_tool(intent["payload"])
        ...         intent = inv.send_call_result(call_id, result)
    """

    def __init__(self) -> None:
        """Initialize a new local investigator."""
        self._inv = Investigator()
        self._trace_id = create_trace()
        self._envelope_builder = EnvelopeBuilder()
        self._started = False

    @property
    def is_terminal(self) -> bool:
        """Check if investigation is in a terminal state."""
        return self._inv.is_terminal()

    @property
    def current_phase(self) -> str:
        """Get the current investigation phase."""
        return self._inv.current_phase()

    @property
    def trace_id(self) -> str:
        """Get the trace ID for this investigation."""
        return self._trace_id

    def start(self, objective: str, scope: dict[str, Any]) -> dict[str, Any]:
        """Start the investigation with the given objective.

        Args:
            objective: Investigation objective.
            scope: Security scope.

        Returns:
            The first intent after starting.
        """
        if self._started:
            raise RuntimeError("Investigation already started")

        event = {"type": "Start", "payload": {"objective": objective, "scope": scope}}
        envelope = self._envelope_builder.build(event)
        intent = _ingest_and_parse(self._inv, envelope)
        self._started = True
        return intent

    def current_intent(self) -> dict[str, Any]:
        """Get the current intent without sending an event.

        Returns:
            The current intent.
        """
        intent_json = self._inv.query()
        return json.loads(intent_json)

    def schedule_call(self, name: str) -> str:
        """Schedule a call by sending CallScheduled event.

        Args:
            name: Name of the tool being scheduled.

        Returns:
            The generated call_id.
        """
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        event = {
            "type": "CallScheduled",
            "payload": {"call_id": call_id, "name": name},
        }
        envelope = self._envelope_builder.build(event)
        _ingest_and_parse(self._inv, envelope)
        return call_id

    def send_call_result(self, call_id: str, output: Any) -> dict[str, Any]:
        """Send a CallResult event.

        Args:
            call_id: ID of the completed call.
            output: Result of the tool execution.

        Returns:
            The next intent.
        """
        event = {
            "type": "CallResult",
            "payload": {"call_id": call_id, "output": output},
        }
        envelope = self._envelope_builder.build(event)
        return _ingest_and_parse(self._inv, envelope)

    def send_user_response(self, question_id: str, content: str) -> dict[str, Any]:
        """Send a UserResponse event.

        Args:
            question_id: ID of the question being answered.
            content: User's response content.

        Returns:
            The next intent.
        """
        event = {
            "type": "UserResponse",
            "payload": {"question_id": question_id, "content": content},
        }
        envelope = self._envelope_builder.build(event)
        return _ingest_and_parse(self._inv, envelope)

    def cancel(self) -> dict[str, Any]:
        """Cancel the investigation.

        Returns:
            The Error intent after cancellation.
        """
        event = {"type": "Cancel"}
        envelope = self._envelope_builder.build(event)
        return _ingest_and_parse(self._inv, envelope)

    def snapshot(self) -> str:
        """Get a JSON snapshot of the current state.

        Returns:
            JSON string of the state.
        """
        return self._inv.snapshot()

    @classmethod
    def restore(cls, state_json: str) -> "LocalInvestigator":
        """Restore from a saved snapshot.

        Args:
            state_json: JSON string of a saved state.

        Returns:
            A LocalInvestigator restored to the saved state.
        """
        instance = cls()
        instance._inv = Investigator.restore(state_json)
        instance._started = True
        return instance
