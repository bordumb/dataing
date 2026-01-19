"""OTEL SDK initialization - idempotent and env-var aware."""

import os
from functools import lru_cache
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_initialized = False


@lru_cache(maxsize=1)
def _get_resource() -> Resource:
    """Build resource from standard OTEL env vars."""
    attrs: dict[str, Any] = {SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "dataing")}

    # Parse OTEL_RESOURCE_ATTRIBUTES
    resource_attrs = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    for attr in resource_attrs.split(","):
        if "=" in attr:
            key, value = attr.split("=", 1)
            attrs[key.strip()] = value.strip()

    return Resource.create(attrs)


def init_telemetry() -> None:
    """Initialize OTEL SDK. Safe to call multiple times (idempotent)."""
    global _initialized
    if _initialized:
        return

    resource = _get_resource()
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    # Initialize tracing if enabled
    if os.getenv("OTEL_TRACES_ENABLED", "").lower() == "true":
        tracer_provider = TracerProvider(resource=resource)
        if endpoint:
            # Import lazily to avoid dependency issues when OTEL is disabled
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            span_exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

    # Initialize metrics if enabled
    if os.getenv("OTEL_METRICS_ENABLED", "").lower() == "true":
        if endpoint:
            # Import lazily to avoid dependency issues when OTEL is disabled
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )

            metric_exporter = OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
            reader = PeriodicExportingMetricReader(metric_exporter)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)

    _initialized = True


def reset_telemetry() -> None:
    """Reset telemetry state for testing. NOT for production use."""
    global _initialized
    _initialized = False
    _get_resource.cache_clear()


def is_telemetry_initialized() -> bool:
    """Check if telemetry has been initialized."""
    return _initialized


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for instrumentation."""
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Get a meter for metrics."""
    return metrics.get_meter(name)
