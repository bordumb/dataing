"""Envelope module for distributed tracing context propagation.

Provides correlation IDs for tracing events through the investigation
state machine and external services.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, TypedDict


class Envelope(TypedDict):
    """Envelope for wrapping payloads with tracing context.

    Attributes:
        id: Unique identifier for this envelope.
        trace_id: Trace ID linking related events.
        parent_id: Optional parent envelope ID for causality tracking.
        payload: The wrapped payload data.
    """

    id: str
    trace_id: str
    parent_id: str | None
    payload: dict[str, Any]


def wrap(
    payload: dict[str, Any],
    trace_id: str,
    parent_id: str | None = None,
) -> str:
    """Wrap a payload in an envelope for tracing.

    Args:
        payload: The data to wrap.
        trace_id: The trace ID for correlation.
        parent_id: Optional parent envelope ID.

    Returns:
        JSON string of the envelope.
    """
    envelope: Envelope = {
        "id": str(uuid.uuid4()),
        "trace_id": trace_id,
        "parent_id": parent_id,
        "payload": payload,
    }
    return json.dumps(envelope)


def unwrap(json_str: str) -> Envelope:
    """Unwrap an envelope from a JSON string.

    Args:
        json_str: JSON string of an envelope.

    Returns:
        The parsed Envelope.

    Raises:
        json.JSONDecodeError: If JSON is invalid.
        KeyError: If required fields are missing.
    """
    data = json.loads(json_str)
    # Validate required fields
    required = {"id", "trace_id", "parent_id", "payload"}
    missing = required - set(data.keys())
    if missing:
        raise KeyError(f"Missing envelope fields: {missing}")
    return Envelope(
        id=data["id"],
        trace_id=data["trace_id"],
        parent_id=data["parent_id"],
        payload=data["payload"],
    )


def create_trace() -> str:
    """Create a new trace ID.

    For Temporal workflows, use workflow.uuid4() instead for
    deterministic replay.

    Returns:
        A new UUID string for use as a trace ID.
    """
    return str(uuid.uuid4())


def extract_trace_id(envelope: Envelope) -> str:
    """Extract the trace ID from an envelope.

    Args:
        envelope: The envelope to extract from.

    Returns:
        The trace ID.
    """
    return envelope["trace_id"]


def create_child_envelope(
    parent: Envelope,
    payload: dict[str, Any],
) -> str:
    """Create a child envelope linked to a parent.

    Args:
        parent: The parent envelope.
        payload: The child payload data.

    Returns:
        JSON string of the child envelope.
    """
    return wrap(payload, parent["trace_id"], parent["id"])
