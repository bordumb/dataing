"""Tests for trace context serialization."""

import os
from unittest.mock import patch

import pytest

from dataing.telemetry.config import get_tracer, init_telemetry, reset_telemetry
from dataing.telemetry.context import restore_trace_context, serialize_trace_context


@pytest.fixture(autouse=True)
def setup_tracing():
    """Enable tracing for context tests."""
    reset_telemetry()
    with patch.dict(os.environ, {"OTEL_TRACES_ENABLED": "true"}, clear=False):
        init_telemetry()
        yield
    reset_telemetry()


class TestSerializeTraceContext:
    """Tests for serialize_trace_context function."""

    def test_empty_without_active_span(self):
        """serialize_trace_context should return empty dict without active span."""
        carrier = serialize_trace_context()
        # May be empty or contain invalid trace context
        assert isinstance(carrier, dict)

    def test_serializes_active_span_context(self):
        """serialize_trace_context should serialize active span's context."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            carrier = serialize_trace_context()

            # Should contain traceparent header
            assert "traceparent" in carrier
            # traceparent format: version-trace_id-span_id-flags
            # e.g., "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
            parts = carrier["traceparent"].split("-")
            assert len(parts) == 4
            assert parts[0] == "00"  # version
            assert len(parts[1]) == 32  # trace_id (hex)
            assert len(parts[2]) == 16  # span_id (hex)

    def test_nested_spans_use_same_trace_id(self):
        """Nested spans should have the same trace_id."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("parent"):
            parent_carrier = serialize_trace_context()
            parent_trace_id = parent_carrier["traceparent"].split("-")[1]

            with tracer.start_as_current_span("child"):
                child_carrier = serialize_trace_context()
                child_trace_id = child_carrier["traceparent"].split("-")[1]

                # Same trace ID
                assert parent_trace_id == child_trace_id


class TestRestoreTraceContext:
    """Tests for restore_trace_context function."""

    def test_restores_valid_context(self):
        """restore_trace_context should restore a valid trace context."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("original"):
            carrier = serialize_trace_context()
            original_trace_id = carrier["traceparent"].split("-")[1]

        # Now restore and create a linked span
        ctx = restore_trace_context(carrier)
        assert ctx is not None

        # Create a span with the restored context
        with tracer.start_as_current_span("linked", context=ctx) as span:
            span_ctx = span.get_span_context()
            restored_trace_id = format(span_ctx.trace_id, "032x")
            # Should have the same trace ID
            assert restored_trace_id == original_trace_id

    def test_handles_empty_carrier(self):
        """restore_trace_context should handle empty carrier gracefully."""
        ctx = restore_trace_context({})
        # Should return a context (possibly invalid/empty)
        assert ctx is not None

    def test_handles_invalid_traceparent(self):
        """restore_trace_context should handle invalid traceparent gracefully."""
        ctx = restore_trace_context({"traceparent": "invalid"})
        # Should return a context without raising
        assert ctx is not None


class TestRoundTrip:
    """Tests for serialize/restore round-trip."""

    def test_full_round_trip(self):
        """Serializing and restoring should maintain trace continuity."""
        tracer = get_tracer("test")

        # Create parent span and serialize
        with tracer.start_as_current_span("producer") as producer_span:
            carrier = serialize_trace_context()
            producer_ctx = producer_span.get_span_context()
            original_trace_id = producer_ctx.trace_id

        # Restore context and create child span (simulating queue consumer)
        restored_ctx = restore_trace_context(carrier)
        with tracer.start_as_current_span("consumer", context=restored_ctx) as consumer_span:
            consumer_ctx = consumer_span.get_span_context()
            # Same trace ID proves continuity
            assert consumer_ctx.trace_id == original_trace_id
            # Different span ID proves it's a new span
            assert consumer_ctx.span_id != producer_ctx.span_id
