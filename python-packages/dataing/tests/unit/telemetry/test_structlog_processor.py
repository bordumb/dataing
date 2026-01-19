"""Tests for structlog trace context processor."""

import os
from unittest.mock import patch

import pytest

from dataing.telemetry.config import get_tracer, init_telemetry, reset_telemetry
from dataing.telemetry.structlog_processor import add_trace_context


@pytest.fixture(autouse=True)
def setup_tracing():
    """Enable tracing for processor tests."""
    reset_telemetry()
    with patch.dict(os.environ, {"OTEL_TRACES_ENABLED": "true"}, clear=False):
        init_telemetry()
        yield
    reset_telemetry()


class TestAddTraceContext:
    """Tests for add_trace_context processor."""

    def test_adds_nothing_without_active_span(self):
        """Processor should not add trace_id/span_id without active span."""
        event_dict: dict[str, str] = {"event": "test message"}
        result = add_trace_context(None, "info", event_dict)

        assert "trace_id" not in result
        assert "span_id" not in result
        assert result["event"] == "test message"

    def test_adds_trace_context_with_active_span(self):
        """Processor should add trace_id and span_id with active span."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            event_dict: dict[str, str] = {"event": "test message"}
            result = add_trace_context(None, "info", event_dict)

            assert "trace_id" in result
            assert "span_id" in result
            # Both should be hex strings
            assert len(result["trace_id"]) == 32
            assert len(result["span_id"]) == 16
            # Original event preserved
            assert result["event"] == "test message"

    def test_trace_id_matches_span_context(self):
        """trace_id should match the current span's trace ID."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("test-span") as span:
            span_ctx = span.get_span_context()
            expected_trace_id = format(span_ctx.trace_id, "032x")
            expected_span_id = format(span_ctx.span_id, "016x")

            event_dict: dict[str, str] = {}
            result = add_trace_context(None, "info", event_dict)

            assert result["trace_id"] == expected_trace_id
            assert result["span_id"] == expected_span_id

    def test_preserves_existing_event_dict_keys(self):
        """Processor should preserve all existing keys in event_dict."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            event_dict = {
                "event": "test",
                "user_id": "123",
                "custom_field": "value",
            }
            result = add_trace_context(None, "info", event_dict)

            assert result["event"] == "test"
            assert result["user_id"] == "123"
            assert result["custom_field"] == "value"
            assert "trace_id" in result
            assert "span_id" in result

    def test_nested_spans_have_same_trace_id(self):
        """Nested spans should have the same trace_id but different span_id."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("parent"):
            parent_result = add_trace_context(None, "info", {})
            parent_trace_id = parent_result["trace_id"]
            parent_span_id = parent_result["span_id"]

            with tracer.start_as_current_span("child"):
                child_result = add_trace_context(None, "info", {})
                child_trace_id = child_result["trace_id"]
                child_span_id = child_result["span_id"]

                # Same trace ID
                assert parent_trace_id == child_trace_id
                # Different span ID
                assert parent_span_id != child_span_id

    def test_logger_and_method_name_ignored(self):
        """Processor should ignore logger and method_name parameters."""
        tracer = get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            event_dict: dict[str, str] = {"event": "test"}

            # These parameters are passed by structlog but we don't use them
            result = add_trace_context("some_logger", "debug", event_dict)

            assert "trace_id" in result
            assert result["event"] == "test"
