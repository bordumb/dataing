"""Tests for the Rust Investigator bindings."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from dataing_investigator import (
    Investigator,
    InvalidTransitionError,
    ProtocolMismatchError,
    SerializationError,
    StateError,
    StepViolationError,
    UnexpectedCallError,
    protocol_version,
)


class EnvelopeBuilder:
    """Helper to build event envelopes for tests."""

    def __init__(self) -> None:
        """Initialize envelope builder."""
        self._step = 0

    def build(self, event: dict[str, Any]) -> str:
        """Build an envelope for the given event."""
        self._step += 1
        envelope = {
            "protocol_version": protocol_version(),
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "step": self._step,
            "event": event,
        }
        return json.dumps(envelope)


class TestInvestigatorBasics:
    """Test basic Investigator functionality."""

    def test_new_investigator(self) -> None:
        """Test creating a new Investigator."""
        inv = Investigator()
        state = json.loads(inv.snapshot())
        assert state["phase"]["type"] == "Init"
        assert state["step"] == 0
        assert state["version"] == protocol_version()

    def test_current_phase_and_step(self) -> None:
        """Test phase and step accessors."""
        inv = Investigator()
        assert inv.current_phase() == "init"
        assert inv.current_step() == 0
        assert not inv.is_terminal()

    def test_protocol_version(self) -> None:
        """Test protocol version is returned."""
        assert protocol_version() == 1

    def test_query_returns_idle_in_init(self) -> None:
        """Test query() returns Idle in Init phase."""
        inv = Investigator()
        intent = json.loads(inv.query())
        assert intent["type"] == "Idle"


class TestInvestigatorEvents:
    """Test Investigator event handling."""

    def test_start_event(self, basic_scope: dict[str, Any]) -> None:
        """Test Start event transitions to GatheringContext."""
        inv = Investigator()
        builder = EnvelopeBuilder()

        start_event = {
            "type": "Start",
            "payload": {
                "objective": "Test investigation",
                "scope": basic_scope,
            },
        }
        envelope = builder.build(start_event)
        intent_json = inv.ingest(envelope)
        intent = json.loads(intent_json)

        # Should emit RequestCall (no call_id)
        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "get_schema"
        assert "call_id" not in intent["payload"]
        assert inv.current_phase() == "gathering_context"

    def test_call_scheduling_handshake(self, basic_scope: dict[str, Any]) -> None:
        """Test the two-step call scheduling handshake."""
        inv = Investigator()
        builder = EnvelopeBuilder()

        # Start
        start = builder.build({
            "type": "Start",
            "payload": {"objective": "Test", "scope": basic_scope},
        })
        intent = json.loads(inv.ingest(start))
        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "get_schema"

        # Workflow assigns call_id via CallScheduled
        scheduled = builder.build({
            "type": "CallScheduled",
            "payload": {"call_id": "call_001", "name": "get_schema"},
        })
        intent = json.loads(inv.ingest(scheduled))
        assert intent["type"] == "Idle"

        # Now send CallResult
        result = builder.build({
            "type": "CallResult",
            "payload": {"call_id": "call_001", "output": {"tables": []}},
        })
        intent = json.loads(inv.ingest(result))

        # Should move to next phase
        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "generate_hypotheses"

    def test_cancel_event(self, basic_scope: dict[str, Any]) -> None:
        """Test Cancel event transitions to Failed."""
        inv = Investigator()
        builder = EnvelopeBuilder()

        start = builder.build({
            "type": "Start",
            "payload": {"objective": "Test", "scope": basic_scope},
        })
        inv.ingest(start)

        cancel = builder.build({"type": "Cancel"})
        intent = json.loads(inv.ingest(cancel))

        assert intent["type"] == "Error"
        assert inv.is_terminal()

    def test_unexpected_call_scheduled_fails(self, basic_scope: dict[str, Any]) -> None:
        """Test that wrong name in CallScheduled raises error."""
        inv = Investigator()
        builder = EnvelopeBuilder()

        start = builder.build({
            "type": "Start",
            "payload": {"objective": "Test", "scope": basic_scope},
        })
        inv.ingest(start)

        # Send CallScheduled with wrong name
        scheduled = builder.build({
            "type": "CallScheduled",
            "payload": {"call_id": "call_001", "name": "wrong_name"},
        })

        with pytest.raises(UnexpectedCallError):
            inv.ingest(scheduled)


class TestInvestigatorProtocolValidation:
    """Test protocol validation."""

    def test_protocol_version_mismatch(self, basic_scope: dict[str, Any]) -> None:
        """Test that wrong protocol version raises error."""
        inv = Investigator()

        envelope = json.dumps({
            "protocol_version": 999,
            "event_id": "evt_001",
            "step": 1,
            "event": {"type": "Cancel"},
        })

        with pytest.raises(ProtocolMismatchError):
            inv.ingest(envelope)

    def test_step_violation(self, basic_scope: dict[str, Any]) -> None:
        """Test that non-monotonic step raises error."""
        inv = Investigator()
        builder = EnvelopeBuilder()

        # First event with step 1
        start = builder.build({
            "type": "Start",
            "payload": {"objective": "Test", "scope": basic_scope},
        })
        inv.ingest(start)

        # Try to send event with step 1 (not > current)
        envelope = json.dumps({
            "protocol_version": protocol_version(),
            "event_id": "evt_002",
            "step": 1,  # Same as first event
            "event": {"type": "Cancel"},
        })

        with pytest.raises(StepViolationError):
            inv.ingest(envelope)

    def test_duplicate_event_idempotent(self, basic_scope: dict[str, Any]) -> None:
        """Test that duplicate event_id is handled idempotently."""
        inv = Investigator()

        # Send start event
        envelope1 = json.dumps({
            "protocol_version": protocol_version(),
            "event_id": "evt_001",
            "step": 1,
            "event": {
                "type": "Start",
                "payload": {"objective": "Test", "scope": basic_scope},
            },
        })
        inv.ingest(envelope1)
        assert inv.current_phase() == "gathering_context"

        # Same event_id with higher step - should be ignored
        envelope2 = json.dumps({
            "protocol_version": protocol_version(),
            "event_id": "evt_001",  # duplicate
            "step": 2,
            "event": {"type": "Cancel"},
        })
        inv.ingest(envelope2)

        # State should NOT have changed
        assert inv.current_phase() == "gathering_context"
        assert inv.current_step() == 1


class TestInvestigatorSerialization:
    """Test Investigator snapshot/restore."""

    def test_restore_from_snapshot(self, basic_scope: dict[str, Any]) -> None:
        """Test restoring from a snapshot."""
        inv1 = Investigator()
        builder = EnvelopeBuilder()

        start = builder.build({
            "type": "Start",
            "payload": {"objective": "Test", "scope": basic_scope},
        })
        inv1.ingest(start)
        snapshot = inv1.snapshot()

        inv2 = Investigator.restore(snapshot)
        assert inv1.snapshot() == inv2.snapshot()
        assert inv1.current_phase() == inv2.current_phase()
        assert inv1.current_step() == inv2.current_step()

    def test_restore_invalid_json(self) -> None:
        """Test restoring from invalid JSON raises error."""
        with pytest.raises(SerializationError):
            Investigator.restore("not valid json")

    def test_restore_invalid_state(self) -> None:
        """Test restoring from invalid state raises error."""
        with pytest.raises(SerializationError):
            Investigator.restore('{"invalid": "state"}')


class TestInvestigatorErrors:
    """Test Investigator error handling."""

    def test_invalid_envelope_json(self) -> None:
        """Test invalid JSON raises SerializationError."""
        inv = Investigator()
        with pytest.raises(SerializationError):
            inv.ingest("not valid json")

    def test_invalid_envelope_structure(self) -> None:
        """Test invalid envelope structure raises error."""
        inv = Investigator()
        with pytest.raises(SerializationError):
            inv.ingest('{"invalid": "envelope"}')


class TestInvestigatorFullCycle:
    """Test full investigation cycle."""

    def test_full_investigation_cycle(self, basic_scope: dict[str, Any]) -> None:
        """Test a complete investigation from start to finish."""
        inv = Investigator()
        builder = EnvelopeBuilder()

        # Start
        start = builder.build({
            "type": "Start",
            "payload": {"objective": "Test", "scope": basic_scope},
        })
        intent = json.loads(inv.ingest(start))
        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "get_schema"

        # CallScheduled for get_schema
        scheduled = builder.build({
            "type": "CallScheduled",
            "payload": {"call_id": "c1", "name": "get_schema"},
        })
        intent = json.loads(inv.ingest(scheduled))
        assert intent["type"] == "Idle"

        # CallResult for get_schema -> GeneratingHypotheses
        result1 = builder.build({
            "type": "CallResult",
            "payload": {"call_id": "c1", "output": {"tables": []}},
        })
        intent = json.loads(inv.ingest(result1))
        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "generate_hypotheses"

        # CallScheduled for generate_hypotheses
        scheduled = builder.build({
            "type": "CallScheduled",
            "payload": {"call_id": "c2", "name": "generate_hypotheses"},
        })
        intent = json.loads(inv.ingest(scheduled))
        assert intent["type"] == "Idle"

        # CallResult with 1 hypothesis -> EvaluatingHypotheses
        result2 = builder.build({
            "type": "CallResult",
            "payload": {
                "call_id": "c2",
                "output": [{"id": "h1", "title": "Test"}],
            },
        })
        intent = json.loads(inv.ingest(result2))
        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "evaluate_hypothesis"

        # CallScheduled for evaluate_hypothesis
        scheduled = builder.build({
            "type": "CallScheduled",
            "payload": {"call_id": "c3", "name": "evaluate_hypothesis"},
        })
        intent = json.loads(inv.ingest(scheduled))
        assert intent["type"] == "Idle"

        # Evaluation result -> Synthesizing
        result3 = builder.build({
            "type": "CallResult",
            "payload": {"call_id": "c3", "output": {"supported": True}},
        })
        intent = json.loads(inv.ingest(result3))
        assert intent["type"] == "RequestCall"
        assert intent["payload"]["name"] == "synthesize"

        # CallScheduled for synthesize
        scheduled = builder.build({
            "type": "CallScheduled",
            "payload": {"call_id": "c4", "name": "synthesize"},
        })
        intent = json.loads(inv.ingest(scheduled))
        assert intent["type"] == "Idle"

        # Synthesis result -> Finished
        result4 = builder.build({
            "type": "CallResult",
            "payload": {"call_id": "c4", "output": {"insight": "Root cause found"}},
        })
        intent = json.loads(inv.ingest(result4))
        assert intent["type"] == "Finish"
        assert intent["payload"]["insight"] == "Root cause found"
        assert inv.is_terminal()
