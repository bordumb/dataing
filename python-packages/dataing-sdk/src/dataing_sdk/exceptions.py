"""SDK exceptions for Dataing."""

from __future__ import annotations


class DataingError(Exception):
    """Base exception for all Dataing SDK errors."""

    pass


class AuthError(DataingError):
    """Authentication or authorization failed."""

    pass


class RateLimitError(DataingError):
    """Rate limit exceeded."""

    retry_after: float | None

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Initialize rate limit error.

        Args:
            message: Error message.
            retry_after: Seconds to wait before retrying.
        """
        super().__init__(message)
        self.retry_after = retry_after


class AmbiguousAssetError(DataingError):
    """Asset reference matched multiple datasources."""

    candidates: list[dict]

    def __init__(self, message: str, candidates: list[dict] | None = None) -> None:
        """Initialize ambiguous asset error.

        Args:
            message: Error message.
            candidates: List of possible matches with datasource info.
        """
        super().__init__(message)
        self.candidates = candidates or []


class NotFoundError(DataingError):
    """Requested resource not found."""

    pass


class ValidationError(DataingError):
    """Request validation failed."""

    pass


class ServerError(DataingError):
    """Server-side error occurred."""

    pass


class TimeoutError(DataingError):
    """Request timed out."""

    pass


class StreamError(DataingError):
    """Error during SSE streaming."""

    pass


class ReplayWindowExpiredError(StreamError):
    """SSE replay window has expired (410 Gone)."""

    pass
