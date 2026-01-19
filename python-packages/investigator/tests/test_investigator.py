"""Tests for the Rust Investigator bindings."""

from __future__ import annotations

import json
from typing import Any

import pytest

from dataing_investigator import (
    Investigator,
    InvalidTransitionError,
    SerializationError,
    StateError,
    protocol_version,
)


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


class TestInvestigatorEvents:
    """Test Investigator event handling."""

    def test_start_event(self, basic_scope: dict[str, Any]) -> None:
        """Test Start event transitions to GatheringContext."""
        inv = Investigator()
        # Use scope without extra field
        start_event = json.dumps({
            "type": "Start",
            "payload": {
                "objective": "Test investigation",
                "scope": basic_scope,
            },
        })
        intent_json = inv.ingest(start_event)
        intent = json.loads(intent_json)

        assert intent["type"] == "Call"
        assert intent["payload"]["name"] == "get_schema"
        assert inv.current_phase() == "gathering_context"

    def test_call_result_event(self, start_event: str) -> None:
        """Test CallResult event progresses the investigation."""
        inv = Investigator()
        intent = json.loads(inv.ingest(start_event))
        call_id = intent["payload"]["call_id"]

        # Send CallResult
        call_result = json.dumps({
            "type": "CallResult",
            "payload": {
                "call_id": call_id,
                "output": {"tables": [{"name": "orders"}]},
            },
        })
        intent = json.loads(inv.ingest(call_result))

        # Should move to next phase
        assert intent["type"] == "Call"
        assert intent["payload"]["name"] == "generate_hypotheses"

    def test_cancel_event(self, start_event: str) -> None:
        """Test Cancel event transitions to Failed."""
        inv = Investigator()
        inv.ingest(start_event)

        cancel_event = json.dumps({"type": "Cancel"})
        intent = json.loads(inv.ingest(cancel_event))

        assert intent["type"] == "Error"
        assert inv.is_terminal()

    def test_invalid_call_id_fails(self, start_event: str) -> None:
        """Test that wrong call_id leads to Failed phase."""
        inv = Investigator()
        inv.ingest(start_event)

        # Send CallResult with wrong call_id
        bad_result = json.dumps({
            "type": "CallResult",
            "payload": {
                "call_id": "wrong-id",
                "output": {},
            },
        })
        intent = json.loads(inv.ingest(bad_result))

        assert intent["type"] == "Error"
        assert inv.is_terminal()


class TestInvestigatorSerialization:
    """Test Investigator snapshot/restore."""

    def test_restore_from_snapshot(self, start_event: str) -> None:
        """Test restoring from a snapshot."""
        inv1 = Investigator()
        inv1.ingest(start_event)
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

    def test_invalid_event_json(self) -> None:
        """Test invalid JSON raises SerializationError."""
        inv = Investigator()
        with pytest.raises(SerializationError):
            inv.ingest("not valid json")

    def test_invalid_event_structure(self) -> None:
        """Test invalid event structure raises error."""
        inv = Investigator()
        with pytest.raises(SerializationError):
            inv.ingest('{"invalid": "event"}')

    def test_ingest_none_returns_idle(self) -> None:
        """Test ingesting None returns current intent."""
        inv = Investigator()
        intent = json.loads(inv.ingest(None))
        # In Init phase, idle is returned
        assert intent["type"] == "Idle"


class TestInvestigatorFullCycle:
    """Test full investigation cycle."""

    def test_full_investigation_cycle(self, basic_scope: dict[str, Any]) -> None:
        """Test a complete investigation from start to finish."""
        inv = Investigator()

        # Start
        start = json.dumps({
            "type": "Start",
            "payload": {"objective": "Test", "scope": basic_scope},
        })
        intent = json.loads(inv.ingest(start))
        assert intent["type"] == "Call"
        call_id_1 = intent["payload"]["call_id"]

        # Schema result -> GeneratingHypotheses
        result1 = json.dumps({
            "type": "CallResult",
            "payload": {"call_id": call_id_1, "output": {"tables": []}},
        })
        intent = json.loads(inv.ingest(result1))
        assert intent["type"] == "Call"
        call_id_2 = intent["payload"]["call_id"]

        # Hypotheses result -> EvaluatingHypotheses
        result2 = json.dumps({
            "type": "CallResult",
            "payload": {
                "call_id": call_id_2,
                "output": [{"id": "h1", "title": "Test"}],
            },
        })
        intent = json.loads(inv.ingest(result2))
        assert intent["type"] == "Call"
        call_id_3 = intent["payload"]["call_id"]

        # Evaluation result -> Synthesizing
        result3 = json.dumps({
            "type": "CallResult",
            "payload": {"call_id": call_id_3, "output": {"supported": True}},
        })
        intent = json.loads(inv.ingest(result3))
        assert intent["type"] == "Call"
        call_id_4 = intent["payload"]["call_id"]

        # Synthesis result -> Finished
        result4 = json.dumps({
            "type": "CallResult",
            "payload": {"call_id": call_id_4, "output": {"insight": "Root cause found"}},
        })
        intent = json.loads(inv.ingest(result4))
        assert intent["type"] == "Finish"
        assert inv.is_terminal()
