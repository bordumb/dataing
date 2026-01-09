"""Safety layer - Guardrails that cannot be bypassed.

This module contains all safety-related components:
- SQL query validation
- Circuit breaker for runaway investigations
- PII detection and redaction

Safety is non-negotiable - these components are designed to be
impossible to circumvent within the normal application flow.
"""

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .pii import redact_pii, scan_for_pii
from .validator import add_limit_if_missing, validate_query

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "validate_query",
    "add_limit_if_missing",
    "scan_for_pii",
    "redact_pii",
]
