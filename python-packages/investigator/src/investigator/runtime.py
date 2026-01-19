"""Runtime module for local investigation execution.

Provides a local execution loop for running investigations outside of Temporal.
Useful for testing and simple deployments.
"""

from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

from dataing_investigator import Investigator

from .envelope import create_trace, wrap
from .security import SecurityViolation, validate_tool_call

# Type alias for tool executor function
ToolExecutor = Callable[[str, dict[str, Any]], Any]
UserResponder = Callable[[str], str]

T = TypeVar("T")


class InvestigationError(Exception):
    """Raised when an investigation fails."""

    pass


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

    # Build and send Start event
    start_event = _build_start_event(objective, scope)
    intent = _ingest_and_parse(inv, start_event)

    steps = 0
    while steps < max_steps:
        steps += 1

        if intent["type"] == "Idle":
            # State machine waiting - query again without event
            intent = _ingest_and_parse(inv, None)

        elif intent["type"] == "Call":
            payload = intent["payload"]
            call_id = payload["call_id"]
            tool_name = payload["name"]
            args = payload["args"]

            # Security validation before execution
            validate_tool_call(tool_name, args, scope)

            # Execute tool
            try:
                result = await tool_executor(tool_name, args)
            except Exception as e:
                # Tool execution failed - send error result
                result = {"error": str(e)}

            # Send CallResult event
            call_result_event = _build_call_result_event(call_id, result)
            intent = _ingest_and_parse(inv, call_result_event)

        elif intent["type"] == "RequestUser":
            question = intent["payload"]["question"]

            if user_responder is None:
                raise RuntimeError(
                    f"User response required but no responder provided. Question: {question}"
                )

            # Get user response
            response = user_responder(question)

            # Send UserResponse event
            user_response_event = _build_user_response_event(response)
            intent = _ingest_and_parse(inv, user_response_event)

        elif intent["type"] == "Finish":
            # Success - return the insight
            return {
                "status": "completed",
                "insight": intent["payload"]["insight"],
                "steps": steps,
                "trace_id": trace_id,
            }

        elif intent["type"] == "Error":
            # Investigation failed
            raise InvestigationError(intent["payload"]["message"])

        else:
            raise InvestigationError(f"Unknown intent type: {intent['type']}")

    raise InvestigationError(f"Investigation exceeded max_steps ({max_steps})")


def _ingest_and_parse(inv: Investigator, event_json: str | None) -> dict[str, Any]:
    """Ingest an event and parse the resulting intent.

    Args:
        inv: The Investigator instance.
        event_json: JSON string of the event, or None.

    Returns:
        Parsed intent dictionary.
    """
    intent_json = inv.ingest(event_json)
    result: dict[str, Any] = json.loads(intent_json)
    return result


def _build_start_event(objective: str, scope: dict[str, Any]) -> str:
    """Build a Start event JSON string.

    Args:
        objective: Investigation objective.
        scope: Security scope.

    Returns:
        JSON string of the Start event.
    """
    return json.dumps({
        "type": "Start",
        "payload": {
            "objective": objective,
            "scope": scope,
        },
    })


def _build_call_result_event(call_id: str, output: Any) -> str:
    """Build a CallResult event JSON string.

    Args:
        call_id: ID of the call being responded to.
        output: Result of the tool execution.

    Returns:
        JSON string of the CallResult event.
    """
    return json.dumps({
        "type": "CallResult",
        "payload": {
            "call_id": call_id,
            "output": output,
        },
    })


def _build_user_response_event(content: str) -> str:
    """Build a UserResponse event JSON string.

    Args:
        content: User's response content.

    Returns:
        JSON string of the UserResponse event.
    """
    return json.dumps({
        "type": "UserResponse",
        "payload": {
            "content": content,
        },
    })


def _build_cancel_event() -> str:
    """Build a Cancel event JSON string.

    Returns:
        JSON string of the Cancel event.
    """
    return json.dumps({
        "type": "Cancel",
    })


class LocalInvestigator:
    """Wrapper providing stateful investigation control.

    For more fine-grained control over the investigation loop,
    use this class instead of run_local().

    Example:
        >>> inv = LocalInvestigator()
        >>> inv.start("Find null spike", scope)
        >>> while not inv.is_terminal:
        ...     intent = inv.current_intent()
        ...     if intent["type"] == "Call":
        ...         result = execute_tool(intent["payload"])
        ...         inv.send_call_result(intent["payload"]["call_id"], result)
    """

    def __init__(self) -> None:
        """Initialize a new local investigator."""
        self._inv = Investigator()
        self._trace_id = create_trace()
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

        event = _build_start_event(objective, scope)
        intent = _ingest_and_parse(self._inv, event)
        self._started = True
        return intent

    def current_intent(self) -> dict[str, Any]:
        """Get the current intent without sending an event.

        Returns:
            The current intent.
        """
        return _ingest_and_parse(self._inv, None)

    def send_call_result(self, call_id: str, output: Any) -> dict[str, Any]:
        """Send a CallResult event.

        Args:
            call_id: ID of the completed call.
            output: Result of the tool execution.

        Returns:
            The next intent.
        """
        event = _build_call_result_event(call_id, output)
        return _ingest_and_parse(self._inv, event)

    def send_user_response(self, content: str) -> dict[str, Any]:
        """Send a UserResponse event.

        Args:
            content: User's response content.

        Returns:
            The next intent.
        """
        event = _build_user_response_event(content)
        return _ingest_and_parse(self._inv, event)

    def cancel(self) -> dict[str, Any]:
        """Cancel the investigation.

        Returns:
            The Error intent after cancellation.
        """
        event = _build_cancel_event()
        return _ingest_and_parse(self._inv, event)

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
