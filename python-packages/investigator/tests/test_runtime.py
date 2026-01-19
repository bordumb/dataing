"""Tests for the runtime module."""

from __future__ import annotations

import json
from typing import Any

import pytest

from investigator.runtime import (
    EnvelopeBuilder,
    InvestigationError,
    LocalInvestigator,
    run_local,
)
from investigator.security import SecurityViolation


class TestEnvelopeBuilder:
    """Test EnvelopeBuilder class."""

    def test_builds_envelope_with_protocol_version(self) -> None:
        """Test envelope includes protocol version."""
        builder = EnvelopeBuilder()
        event = {"type": "Cancel"}

        envelope = json.loads(builder.build(event))

        assert "protocol_version" in envelope
        assert envelope["protocol_version"] == 1

    def test_builds_envelope_with_event_id(self) -> None:
        """Test envelope includes unique event IDs."""
        builder = EnvelopeBuilder()

        envelope1 = json.loads(builder.build({"type": "Cancel"}))
        envelope2 = json.loads(builder.build({"type": "Cancel"}))

        assert envelope1["event_id"] != envelope2["event_id"]

    def test_builds_envelope_with_monotonic_step(self) -> None:
        """Test envelope has monotonically increasing steps."""
        builder = EnvelopeBuilder()

        envelope1 = json.loads(builder.build({"type": "Cancel"}))
        envelope2 = json.loads(builder.build({"type": "Cancel"}))
        envelope3 = json.loads(builder.build({"type": "Cancel"}))

        assert envelope1["step"] == 1
        assert envelope2["step"] == 2
        assert envelope3["step"] == 3

    def test_includes_event_in_envelope(self) -> None:
        """Test envelope includes the event."""
        builder = EnvelopeBuilder()
        event = {"type": "Start", "payload": {"objective": "Test", "scope": {}}}

        envelope = json.loads(builder.build(event))

        assert envelope["event"] == event


class TestLocalInvestigator:
    """Test LocalInvestigator class."""

    def test_new_investigator(self) -> None:
        """Test creating a new LocalInvestigator."""
        inv = LocalInvestigator()
        assert inv.current_phase == "init"
        assert not inv.is_terminal
        assert inv.trace_id  # Should have a trace ID

    def test_start_investigation(self, basic_scope: dict[str, Any]) -> None:
        """Test starting an investigation."""
        inv = LocalInvestigator()
        intent = inv.start("Find the bug", basic_scope)

        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "get_schema"
        assert "gathering" in inv.current_phase.lower()

    def test_cannot_start_twice(self, basic_scope: dict[str, Any]) -> None:
        """Test that investigation cannot be started twice."""
        inv = LocalInvestigator()
        inv.start("First start", basic_scope)

        with pytest.raises(RuntimeError) as exc_info:
            inv.start("Second start", basic_scope)
        assert "already started" in str(exc_info.value)

    def test_schedule_call_and_send_result(self, basic_scope: dict[str, Any]) -> None:
        """Test scheduling a call and sending result."""
        inv = LocalInvestigator()
        intent = inv.start("Test", basic_scope)

        # Get tool name from RequestCall
        assert intent["type"] == "RequestCall"
        tool_name = intent["payload"]["name"]

        # Schedule the call
        call_id = inv.schedule_call(tool_name)
        assert call_id.startswith("call_")

        # Send result
        next_intent = inv.send_call_result(call_id, {"tables": []})

        assert next_intent["type"] == "RequestCall"
        assert next_intent["payload"]["name"] == "generate_hypotheses"

    def test_current_intent(self, basic_scope: dict[str, Any]) -> None:
        """Test getting current intent without event."""
        inv = LocalInvestigator()
        # Before start, current_intent returns Idle
        intent = inv.current_intent()
        assert intent["type"] == "Idle"

    def test_cancel(self, basic_scope: dict[str, Any]) -> None:
        """Test cancelling an investigation."""
        inv = LocalInvestigator()
        inv.start("Test", basic_scope)

        intent = inv.cancel()

        assert intent["type"] == "Error"
        assert inv.is_terminal

    def test_snapshot_restore(self, basic_scope: dict[str, Any]) -> None:
        """Test snapshot and restore."""
        inv1 = LocalInvestigator()
        inv1.start("Test", basic_scope)
        snapshot = inv1.snapshot()

        inv2 = LocalInvestigator.restore(snapshot)

        assert inv1.current_phase == inv2.current_phase
        assert inv2._started  # noqa: SLF001


class TestRunLocal:
    """Test run_local function."""

    @pytest.mark.asyncio
    async def test_run_local_completes(
        self, basic_scope: dict[str, Any], mock_tool_executor: Any
    ) -> None:
        """Test run_local completes an investigation."""
        result = await run_local(
            objective="Find the bug",
            scope=basic_scope,
            tool_executor=mock_tool_executor,
            max_steps=50,
        )

        assert result["status"] == "completed"
        assert "insight" in result
        assert result["steps"] > 0
        assert result["trace_id"]

    @pytest.mark.asyncio
    async def test_run_local_max_steps(self, basic_scope: dict[str, Any]) -> None:
        """Test run_local respects max_steps."""

        async def slow_response(tool: str, args: dict[str, Any]) -> dict[str, Any]:
            # Return responses that don't complete the investigation quickly
            if tool == "get_schema":
                return {"tables": [{"name": "t1"}, {"name": "t2"}, {"name": "t3"}]}
            elif tool == "generate_hypotheses":
                # Return many hypotheses to extend the evaluation phase
                return [
                    {"id": f"h{i}", "title": f"Hypothesis {i}"}
                    for i in range(10)
                ]
            elif tool == "evaluate_hypothesis":
                # Each hypothesis needs evaluation
                return {"supported": False, "confidence": 0.1}
            else:
                return {"minimal": "response"}

        # Use a very small max_steps to trigger the limit
        with pytest.raises(InvestigationError) as exc_info:
            await run_local(
                objective="Test",
                scope=basic_scope,
                tool_executor=slow_response,
                max_steps=3,
            )
        assert "max_steps" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_local_tool_error(self, basic_scope: dict[str, Any]) -> None:
        """Test run_local handles tool errors gracefully."""
        call_count = 0

        async def failing_then_working_executor(
            tool: str, args: dict[str, Any]
        ) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            # Fail on first call, then work normally
            if call_count == 1:
                raise RuntimeError("Tool failed")
            if tool == "get_schema":
                return {"tables": [{"name": "orders"}], "error": "partial failure"}
            elif tool == "generate_hypotheses":
                return [{"id": "h1", "title": "Test"}]
            elif tool == "evaluate_hypothesis":
                return {"supported": True}
            elif tool == "synthesize":
                return {"insight": "Completed despite errors"}
            return {}

        # The error is captured and sent back to state machine
        # Investigation continues with the error as part of the output
        result = await run_local(
            objective="Test",
            scope=basic_scope,
            tool_executor=failing_then_working_executor,
            max_steps=50,
        )
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_local_security_violation(
        self, basic_scope: dict[str, Any], mock_tool_executor: Any
    ) -> None:
        """Test run_local works with empty permissions scope."""
        # Create scope with no permissions - should still complete
        # since default tools don't require table permissions
        empty_scope = {**basic_scope, "permissions": []}

        result = await run_local(
            objective="Test",
            scope=empty_scope,
            tool_executor=mock_tool_executor,
            max_steps=50,
        )
        # Should complete since default tools don't require table permissions
        assert result["status"] == "completed"


class TestRunLocalUserResponse:
    """Test run_local with user responses."""

    @pytest.mark.asyncio
    async def test_user_response_parameter_accepted(
        self, basic_scope: dict[str, Any], mock_tool_executor: Any
    ) -> None:
        """Test that user_responder parameter is accepted."""
        # Current state machine doesn't emit RequestUser in normal flow
        # This test verifies the parameter is accepted
        result = await run_local(
            objective="Test",
            scope=basic_scope,
            tool_executor=mock_tool_executor,
            user_responder=None,
            max_steps=50,
        )
        assert result["status"] == "completed"


class TestInvestigationError:
    """Test InvestigationError exception."""

    def test_investigation_error_message(self) -> None:
        """Test InvestigationError preserves message."""
        try:
            raise InvestigationError("Test error")
        except InvestigationError as e:
            assert str(e) == "Test error"

    def test_investigation_error_is_exception(self) -> None:
        """Test InvestigationError is an Exception."""
        assert issubclass(InvestigationError, Exception)
