"""W3C trace context serialization for queue propagation."""

from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject


def serialize_trace_context() -> dict[str, str]:
    """Serialize current trace context for queue payload.

    Returns a dict containing W3C trace context headers (traceparent, tracestate)
    that can be passed through a message queue to maintain trace continuity.
    """
    carrier: dict[str, str] = {}
    inject(carrier)  # Injects traceparent, tracestate
    return carrier


def restore_trace_context(carrier: dict[str, str]) -> Context:
    """Restore trace context from queue payload.

    Takes a dict containing W3C trace context headers and returns an
    OpenTelemetry Context that can be used to create linked spans.

    Args:
        carrier: Dict with traceparent/tracestate from serialize_trace_context()

    Returns:
        Context object to use when creating child spans
    """
    return extract(carrier)
