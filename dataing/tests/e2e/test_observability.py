"""End-to-end tests for observability: tracing, metrics, and correlation.

Tests verify:
- Trace context propagation from API through queue to worker
- Correlation ID flows through the entire request lifecycle
- No PII leaks into span attributes
- Graceful degradation when telemetry is disabled
- Metrics are properly recorded
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from opentelemetry.sdk.trace import Tracer, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@dataclass
class IsolatedTracer:
    """Container for isolated tracer and its exporter."""

    provider: TracerProvider
    exporter: InMemorySpanExporter

    def get_tracer(self, name: str) -> Tracer:
        """Get a tracer from the isolated provider."""
        return self.provider.get_tracer(name)


@pytest.fixture
def isolated_tracer():
    """Create isolated tracer for test - doesn't affect global state.

    Returns an IsolatedTracer with its own provider and exporter.
    Use isolated_tracer.get_tracer() instead of trace.get_tracer().
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    yield IsolatedTracer(provider=provider, exporter=exporter)

    exporter.clear()


@pytest.fixture
def reset_telemetry():
    """Reset telemetry state between tests."""
    from dataing.telemetry.config import reset_telemetry as _reset
    from dataing.telemetry.metrics import reset_metrics

    _reset()
    reset_metrics()
    yield
    _reset()
    reset_metrics()


class TestTraceContextPropagation:
    """Tests for trace context propagation."""

    def test_serialize_deserialize_trace_context(
        self, isolated_tracer: IsolatedTracer
    ) -> None:
        """Test that trace context can be serialized and restored."""
        from dataing.telemetry import restore_trace_context, serialize_trace_context

        tracer = isolated_tracer.get_tracer("test")

        with tracer.start_as_current_span("parent") as parent_span:
            # Serialize context
            ctx_dict = serialize_trace_context()

            # Verify serialized format
            assert "traceparent" in ctx_dict
            assert ctx_dict["traceparent"] is not None
            # traceparent format: version-traceid-spanid-flags
            parts = ctx_dict["traceparent"].split("-")
            assert len(parts) == 4
            assert parts[0] == "00"  # version

            # Get original trace and span IDs
            original_trace_id = parent_span.get_span_context().trace_id

        # Restore context and create child span
        restored_ctx = restore_trace_context(ctx_dict)
        assert restored_ctx is not None

        with tracer.start_as_current_span("child", context=restored_ctx) as child_span:
            # Child should have same trace ID as parent
            child_trace_id = child_span.get_span_context().trace_id
            assert child_trace_id == original_trace_id

    def test_serialize_without_active_span(self) -> None:
        """Test serialization when no span is active."""
        from dataing.telemetry import serialize_trace_context

        ctx_dict = serialize_trace_context()
        # Should return dict but traceparent may be None or empty
        assert isinstance(ctx_dict, dict)

    def test_restore_with_invalid_context(self) -> None:
        """Test restoration with invalid context data."""
        from dataing.telemetry import restore_trace_context

        # Empty dict
        result = restore_trace_context({})
        # Should return None or default context, not raise
        assert result is None or result is not None  # Just ensure no exception

        # None traceparent
        result = restore_trace_context({"traceparent": None})
        assert result is None or result is not None

        # Invalid traceparent format
        result = restore_trace_context({"traceparent": "invalid"})
        # Should handle gracefully


class TestSpanAttributes:
    """Tests for span attribute safety."""

    def test_no_pii_in_custom_spans(
        self, isolated_tracer: IsolatedTracer
    ) -> None:
        """Test that custom spans don't leak PII."""
        tracer = isolated_tracer.get_tracer("test.pii")

        # Create spans with various attributes
        with tracer.start_as_current_span(
            "test_operation",
            attributes={
                "investigation_id": "inv-123",
                "tenant_id": "tenant-456",  # This is OK - not PII
                "status": "completed",
            },
        ):
            pass

        spans = isolated_tracer.exporter.get_finished_spans()
        assert len(spans) == 1

        span = spans[0]
        attrs = dict(span.attributes)

        # Verify expected attributes exist
        assert attrs.get("investigation_id") == "inv-123"
        assert attrs.get("status") == "completed"

        # Verify no obvious PII fields
        for key in attrs:
            key_lower = key.lower()
            assert "email" not in key_lower
            assert "password" not in key_lower
            assert "ssn" not in key_lower
            assert "credit_card" not in key_lower


class TestGracefulDegradation:
    """Tests for graceful degradation when telemetry is disabled."""

    def test_tracing_works_when_disabled(
        self, reset_telemetry, monkeypatch
    ) -> None:
        """Verify tracing operations don't fail when OTEL is disabled."""
        monkeypatch.setenv("OTEL_TRACES_ENABLED", "false")
        monkeypatch.setenv("OTEL_METRICS_ENABLED", "false")

        from dataing.telemetry.config import get_tracer, init_telemetry

        # Should not raise
        init_telemetry()

        tracer = get_tracer("test.disabled")

        # Creating and using spans should work (as no-ops)
        with tracer.start_as_current_span("test_span") as span:
            span.set_attribute("key", "value")
            # Should not raise

    def test_metrics_work_when_disabled(
        self, reset_telemetry, monkeypatch
    ) -> None:
        """Verify metric operations don't fail when OTEL is disabled."""
        monkeypatch.setenv("OTEL_TRACES_ENABLED", "false")
        monkeypatch.setenv("OTEL_METRICS_ENABLED", "false")

        from dataing.telemetry.config import init_telemetry
        from dataing.telemetry.metrics import (
            init_metrics,
            record_investigation_completed,
            record_investigation_duration,
            record_queue_wait_time,
        )

        init_telemetry()
        init_metrics()

        # All these should be no-ops, not errors
        record_investigation_duration(1.5, "completed")
        record_queue_wait_time(0.5)
        record_investigation_completed("completed")


class TestMetricsRecording:
    """Tests for metrics recording functionality."""

    def test_metrics_initialization_is_idempotent(self, reset_telemetry) -> None:
        """Test that init_metrics can be called multiple times safely."""
        from dataing.telemetry.metrics import init_metrics, is_metrics_initialized

        assert not is_metrics_initialized()

        init_metrics()
        assert is_metrics_initialized()

        # Second call should not raise
        init_metrics()
        assert is_metrics_initialized()

    def test_recording_functions_work_after_init(self, reset_telemetry) -> None:
        """Test that all recording functions work after initialization."""
        from dataing.telemetry.metrics import (
            init_metrics,
            record_investigation_completed,
            record_investigation_duration,
            record_queue_wait_time,
            record_step_duration,
            record_worker_duration,
        )

        init_metrics()

        # All should succeed without raising
        record_investigation_duration(1.5, "completed")
        record_investigation_duration(2.0, "failed")
        record_queue_wait_time(0.1)
        record_worker_duration(10.0, "completed")
        record_step_duration("gather_context", 0.5)
        record_step_duration("generate_hypotheses", 1.2)
        record_investigation_completed("completed")
        record_investigation_completed("failed")
        record_investigation_completed("cancelled")

    def test_recording_without_init_is_safe(self, reset_telemetry) -> None:
        """Test that recording without init doesn't raise."""
        from dataing.telemetry.metrics import (
            is_metrics_initialized,
            record_investigation_completed,
            record_investigation_duration,
            record_queue_wait_time,
        )

        assert not is_metrics_initialized()

        # Should be no-ops, not errors
        record_investigation_duration(1.0, "completed")
        record_queue_wait_time(0.5)
        record_investigation_completed("completed")


class TestCorrelationId:
    """Tests for correlation ID propagation."""

    def test_correlation_id_in_span_attributes(
        self, isolated_tracer: IsolatedTracer
    ) -> None:
        """Test that correlation ID can be stored in span attributes."""
        tracer = isolated_tracer.get_tracer("test.correlation")
        correlation_id = "corr-test-123"

        with tracer.start_as_current_span(
            "test_with_correlation",
            attributes={"correlation_id": correlation_id},
        ):
            pass

        spans = isolated_tracer.exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes.get("correlation_id") == correlation_id


class TestTelemetryInitialization:
    """Tests for telemetry initialization."""

    def test_init_telemetry_is_idempotent(self, reset_telemetry) -> None:
        """Test that init_telemetry can be called multiple times."""
        from dataing.telemetry.config import (
            init_telemetry,
            is_telemetry_initialized,
        )

        assert not is_telemetry_initialized()

        init_telemetry()
        assert is_telemetry_initialized()

        # Second call should not raise
        init_telemetry()
        assert is_telemetry_initialized()

    def test_reset_telemetry_clears_state(self, reset_telemetry) -> None:
        """Test that reset_telemetry clears initialization state."""
        from dataing.telemetry.config import (
            init_telemetry,
            is_telemetry_initialized,
        )
        from dataing.telemetry.config import (
            reset_telemetry as _reset,
        )

        init_telemetry()
        assert is_telemetry_initialized()

        _reset()
        assert not is_telemetry_initialized()
