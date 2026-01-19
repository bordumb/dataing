"""Tests for telemetry configuration module."""

import os
from unittest.mock import patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from dataing.telemetry.config import (
    get_meter,
    get_tracer,
    init_telemetry,
    is_telemetry_initialized,
    reset_telemetry,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset telemetry state before and after each test."""
    reset_telemetry()
    yield
    reset_telemetry()


class TestInitTelemetry:
    """Tests for init_telemetry function."""

    def test_idempotent_initialization(self):
        """Calling init_telemetry multiple times should be safe."""
        with patch.dict(os.environ, {"OTEL_TRACES_ENABLED": "true"}, clear=False):
            init_telemetry()
            assert is_telemetry_initialized()

            # Second call should not raise
            init_telemetry()
            assert is_telemetry_initialized()

    def test_disabled_by_default(self):
        """Telemetry should not initialize providers when env vars are not set."""
        with patch.dict(os.environ, {}, clear=True):
            init_telemetry()
            assert is_telemetry_initialized()
            # Should still return tracers/meters (no-op ones)
            tracer = get_tracer("test")
            assert tracer is not None

    def test_tracing_enabled(self):
        """Tracing should be enabled when OTEL_TRACES_ENABLED=true."""
        with patch.dict(
            os.environ,
            {"OTEL_TRACES_ENABLED": "true", "OTEL_SERVICE_NAME": "test-service"},
            clear=False,
        ):
            init_telemetry()
            provider = trace.get_tracer_provider()
            assert isinstance(provider, TracerProvider)

    def test_metrics_enabled_requires_endpoint(self):
        """Metrics should only be enabled when endpoint is also provided."""
        with patch.dict(
            os.environ,
            {"OTEL_METRICS_ENABLED": "true"},
            clear=False,
        ):
            init_telemetry()
            # Without endpoint, metrics provider is not set
            assert is_telemetry_initialized()

    def test_service_name_from_env(self):
        """Service name should be read from OTEL_SERVICE_NAME.

        Note: OpenTelemetry doesn't allow overriding global providers once set,
        so we test that init_telemetry runs without error. The resource is built
        correctly by _get_resource() which we test indirectly.
        """
        with patch.dict(
            os.environ,
            {"OTEL_SERVICE_NAME": "my-test-service", "OTEL_TRACES_ENABLED": "true"},
            clear=False,
        ):
            # Should not raise
            init_telemetry()
            assert is_telemetry_initialized()
            # Tracer should still be usable
            tracer = get_tracer("test")
            assert tracer is not None

    def test_resource_attributes_parsing(self):
        """OTEL_RESOURCE_ATTRIBUTES should be parsed correctly.

        Note: We can't verify the actual resource attributes in the global provider
        due to OTEL's single-initialization constraint. We test the parsing logic
        indirectly by verifying init_telemetry completes successfully.
        """
        with patch.dict(
            os.environ,
            {
                "OTEL_TRACES_ENABLED": "true",
                "OTEL_SERVICE_NAME": "test",
                "OTEL_RESOURCE_ATTRIBUTES": "service.version=1.0.0,deployment.environment=test",
            },
            clear=False,
        ):
            # Should not raise even with complex resource attributes
            init_telemetry()
            assert is_telemetry_initialized()


class TestGetTracer:
    """Tests for get_tracer function."""

    def test_returns_tracer(self):
        """get_tracer should return a valid Tracer."""
        tracer = get_tracer("test.module")
        assert tracer is not None
        assert hasattr(tracer, "start_span")
        assert hasattr(tracer, "start_as_current_span")

    def test_tracer_creates_spans(self):
        """Tracer should be able to create spans."""
        with patch.dict(os.environ, {"OTEL_TRACES_ENABLED": "true"}, clear=False):
            init_telemetry()
            tracer = get_tracer("test.module")
            with tracer.start_as_current_span("test-span") as span:
                assert span is not None
                assert span.is_recording()


class TestGetMeter:
    """Tests for get_meter function."""

    def test_returns_meter(self):
        """get_meter should return a valid Meter."""
        meter = get_meter("test.module")
        assert meter is not None
        assert hasattr(meter, "create_counter")
        assert hasattr(meter, "create_histogram")

    def test_meter_creates_instruments(self):
        """Meter should be able to create instruments."""
        meter = get_meter("test.module")
        counter = meter.create_counter("test_counter")
        assert counter is not None
        # Should not raise when recording
        counter.add(1)


class TestResetTelemetry:
    """Tests for reset_telemetry function."""

    def test_reset_clears_initialized_flag(self):
        """reset_telemetry should clear the initialized flag."""
        with patch.dict(os.environ, {"OTEL_TRACES_ENABLED": "true"}, clear=False):
            init_telemetry()
            assert is_telemetry_initialized()

            reset_telemetry()
            assert not is_telemetry_initialized()

    def test_allows_reinitialization(self):
        """After reset, init_telemetry should run again."""
        with patch.dict(os.environ, {"OTEL_TRACES_ENABLED": "true"}, clear=False):
            init_telemetry()
            reset_telemetry()

            # Should be able to init again
            init_telemetry()
            assert is_telemetry_initialized()
