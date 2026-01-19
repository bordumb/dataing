"""Structlog processor to inject trace context into all logs."""

from typing import Any

from opentelemetry import trace


def add_trace_context(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor to inject trace/span IDs into logs.

    Adds trace_id and span_id to every log entry when there is an active span.
    This enables correlating logs with distributed traces.

    Args:
        logger: The wrapped logger object (unused)
        method_name: Name of the logging method called (unused)
        event_dict: The event dictionary to modify

    Returns:
        The modified event dictionary with trace context added
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")

    return event_dict
