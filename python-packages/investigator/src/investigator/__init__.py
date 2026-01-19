"""Investigator - Rust-powered investigation state machine runtime.

This package provides a Python interface to the Rust state machine for
data quality investigations. The state machine manages the investigation
lifecycle with deterministic transitions and versioned snapshots.

Example:
    >>> from investigator import Investigator
    >>> inv = Investigator()
    >>> print(inv.current_phase())
    'init'
"""

from dataing_investigator import (
    Investigator,
    InvalidTransitionError,
    SerializationError,
    StateError,
    protocol_version,
)

from investigator.envelope import (
    Envelope,
    create_child_envelope,
    create_trace,
    extract_trace_id,
    unwrap,
    wrap,
)
from investigator.security import (
    SecurityViolation,
    create_scope,
    validate_tool_call,
)

__all__ = [
    # Rust bindings
    "Investigator",
    "StateError",
    "SerializationError",
    "InvalidTransitionError",
    "protocol_version",
    # Envelope
    "Envelope",
    "wrap",
    "unwrap",
    "create_trace",
    "extract_trace_id",
    "create_child_envelope",
    # Security
    "SecurityViolation",
    "validate_tool_call",
    "create_scope",
]

__version__ = "0.1.0"
