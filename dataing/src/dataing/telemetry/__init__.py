"""Telemetry module for OpenTelemetry tracing and metrics."""

from dataing.telemetry.config import get_meter, get_tracer, init_telemetry
from dataing.telemetry.context import restore_trace_context, serialize_trace_context
from dataing.telemetry.correlation import CorrelationMiddleware
from dataing.telemetry.logging import configure_logging
from dataing.telemetry.structlog_processor import add_trace_context

__all__ = [
    "init_telemetry",
    "get_tracer",
    "get_meter",
    "serialize_trace_context",
    "restore_trace_context",
    "add_trace_context",
    "CorrelationMiddleware",
    "configure_logging",
]
