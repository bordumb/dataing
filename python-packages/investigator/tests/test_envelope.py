"""Tests for the envelope module."""

from __future__ import annotations

import json
from typing import Any

import pytest

from investigator.envelope import (
    Envelope,
    create_child_envelope,
    create_trace,
    extract_trace_id,
    unwrap,
    wrap,
)


class TestWrapUnwrap:
    """Test wrap/unwrap functionality."""

    def test_wrap_creates_json_string(self) -> None:
        """Test wrap creates a valid JSON string."""
        payload = {"test": "data", "number": 42}
        trace_id = create_trace()

        result = wrap(payload, trace_id)

        # wrap returns a JSON string
        assert isinstance(result, str)
        envelope = json.loads(result)
        assert envelope["trace_id"] == trace_id
        assert envelope["payload"] == payload
        assert "id" in envelope

    def test_unwrap_returns_envelope(self) -> None:
        """Test unwrap returns an Envelope dict."""
        payload = {"test": "data", "nested": {"key": "value"}}
        trace_id = create_trace()

        json_str = wrap(payload, trace_id)
        envelope = unwrap(json_str)

        assert envelope["payload"] == payload
        assert envelope["trace_id"] == trace_id
        assert "id" in envelope

    def test_wrap_unwrap_roundtrip(self) -> None:
        """Test wrap/unwrap roundtrip preserves data."""
        original = {"key": "value", "list": [1, 2, 3], "nested": {"a": "b"}}
        trace_id = create_trace()

        json_str = wrap(original, trace_id)
        envelope = unwrap(json_str)

        assert envelope["payload"] == original

    def test_wrap_with_parent_id(self) -> None:
        """Test wrap with parent_id."""
        payload = {"test": "data"}
        trace_id = create_trace()
        parent_id = "parent-123"

        json_str = wrap(payload, trace_id, parent_id)
        envelope = unwrap(json_str)

        assert envelope["parent_id"] == parent_id

    def test_wrap_without_parent_id(self) -> None:
        """Test wrap without parent_id sets it to None."""
        payload = {"test": "data"}
        trace_id = create_trace()

        json_str = wrap(payload, trace_id)
        envelope = unwrap(json_str)

        assert envelope["parent_id"] is None

    def test_unwrap_missing_fields_raises(self) -> None:
        """Test unwrap raises KeyError for missing fields."""
        bad_json = json.dumps({"only_one_field": "value"})

        with pytest.raises(KeyError):
            unwrap(bad_json)


class TestTraceId:
    """Test trace ID functionality."""

    def test_create_trace_is_string(self) -> None:
        """Test create_trace returns a string."""
        trace_id = create_trace()
        assert isinstance(trace_id, str)
        assert len(trace_id) > 0

    def test_create_trace_unique(self) -> None:
        """Test create_trace returns unique IDs."""
        traces = [create_trace() for _ in range(100)]
        assert len(set(traces)) == 100

    def test_extract_trace_id(self) -> None:
        """Test extract_trace_id from envelope dict."""
        trace_id = create_trace()
        json_str = wrap({"test": "data"}, trace_id)
        envelope = unwrap(json_str)

        extracted = extract_trace_id(envelope)
        assert extracted == trace_id


class TestChildEnvelope:
    """Test child envelope creation."""

    def test_create_child_envelope(self) -> None:
        """Test creating a child envelope."""
        parent_json = wrap({"parent": "data"}, create_trace())
        parent = unwrap(parent_json)
        child_payload = {"child": "data"}

        child_json = create_child_envelope(parent, child_payload)
        child = unwrap(child_json)

        # Child should have same trace_id
        assert child["trace_id"] == parent["trace_id"]
        assert child["payload"] == child_payload
        # Child should reference parent's id
        assert child["parent_id"] == parent["id"]

    def test_child_envelope_preserves_trace(self) -> None:
        """Test child preserves parent trace ID."""
        trace_id = "custom-trace-123"
        parent: Envelope = {
            "id": "parent-id-456",
            "trace_id": trace_id,
            "parent_id": None,
            "payload": {"parent": True},
        }

        child_json = create_child_envelope(parent, {"child": True})
        child = unwrap(child_json)

        assert child["trace_id"] == trace_id
        assert child["parent_id"] == "parent-id-456"


class TestEnvelopeSerialization:
    """Test envelope JSON serialization."""

    def test_envelope_json_roundtrip(self) -> None:
        """Test envelope can be serialized and deserialized."""
        original_json = wrap({"test": "data"}, create_trace())
        original = unwrap(original_json)

        # Re-serialize and parse
        json_str = json.dumps(original)
        restored: Envelope = json.loads(json_str)

        assert restored == original

    def test_envelope_with_complex_payload(self) -> None:
        """Test envelope with complex nested payload."""
        payload = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"a": {"b": {"c": "deep"}}},
        }

        json_str = wrap(payload, create_trace())
        envelope = unwrap(json_str)

        assert envelope["payload"] == payload
