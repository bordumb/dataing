"""Domain-specific exceptions.

All exceptions in the dataing system inherit from DataingError,
making it easy to catch all system errors while still being able
to handle specific error types.
"""

from __future__ import annotations


class DataingError(Exception):
    """Base exception for all dataing errors.

    All custom exceptions in the system should inherit from this class
    to enable catching all dataing-specific errors with a single except clause.
    """

    pass


class SchemaDiscoveryError(DataingError):
    """Failed to discover database schema.

    This is a FATAL error - investigation cannot proceed without schema.
    Indicates database connectivity issues or permissions problems.

    The investigation will fail fast when this error is raised,
    rather than attempting to continue without schema information.
    """

    pass


class CircuitBreakerTripped(DataingError):
    """Safety limit exceeded.

    Raised when one of the circuit breaker conditions is met:
    - Too many queries executed
    - Too many retries on same hypothesis
    - Duplicate query detected (stall)
    - Total investigation time exceeded

    This is a safety mechanism to prevent runaway investigations
    that could consume excessive resources or enter infinite loops.
    """

    pass


class QueryValidationError(DataingError):
    """Query failed safety validation.

    Raised when a generated SQL query fails safety checks:
    - Contains forbidden statements (DROP, DELETE, UPDATE, etc.)
    - Is not a SELECT statement
    - Missing required LIMIT clause
    - Contains other dangerous patterns

    This ensures that only safe, read-only queries are executed.
    """

    pass


class LLMError(DataingError):
    """LLM call failed.

    Raised when an LLM API call fails. The `retryable` attribute
    indicates whether the error is likely transient and worth retrying.

    Attributes:
        retryable: Whether this error is likely transient.
    """

    def __init__(self, message: str, retryable: bool = True) -> None:
        """Initialize LLMError.

        Args:
            message: Error description.
            retryable: Whether error is transient and retryable.
        """
        super().__init__(message)
        self.retryable = retryable


class TimeoutError(DataingError):  # noqa: A001
    """Investigation or query exceeded time limit.

    Raised when:
    - A single query exceeds its timeout
    - The entire investigation exceeds the maximum duration

    This prevents investigations from running indefinitely.
    """

    pass


class SnapshotSizeExceededError(DataingError):
    """Snapshot archive exceeds maximum allowed size.

    Raised when building a snapshot archive that exceeds the configured
    max_size_bytes limit. This prevents creating excessively large archives
    that would be impractical to transfer or store.

    Attributes:
        actual_size: The actual size of the archive in bytes.
        max_size: The maximum allowed size in bytes.
    """

    def __init__(self, actual_size: int, max_size: int) -> None:
        """Initialize SnapshotSizeExceededError.

        Args:
            actual_size: The actual archive size in bytes.
            max_size: The maximum allowed size in bytes.
        """
        super().__init__(
            f"Snapshot size ({actual_size:,} bytes) exceeds maximum " f"({max_size:,} bytes)"
        )
        self.actual_size = actual_size
        self.max_size = max_size
