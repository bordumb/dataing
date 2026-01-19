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

__all__ = [
    "Investigator",
    "StateError",
    "SerializationError",
    "InvalidTransitionError",
    "protocol_version",
]

__version__ = "0.1.0"
