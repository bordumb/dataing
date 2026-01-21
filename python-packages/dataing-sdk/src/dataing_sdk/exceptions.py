"""SDK exceptions for the Dataing API client.

This module defines the exception hierarchy for the Dataing SDK. All exceptions
inherit from `DataingError` for easy catch-all handling.

Exception Hierarchy::

    DataingError
    ├── AuthError          # 401/403 authentication/authorization failures
    ├── NotFoundError      # 404 resource not found
    ├── ValidationError    # 422 request validation failures
    ├── RateLimitError     # 429 rate limit exceeded (has retry_after)
    ├── ServerError        # 5xx server-side errors
    ├── TimeoutError       # Request timed out
    ├── AmbiguousAssetError  # 409 multiple datasources match
    └── StreamError        # SSE streaming errors
        └── ReplayWindowExpiredError  # 410 replay window expired

Example:
    ```python
    from dataing_sdk import DataingClient
    from dataing_sdk.exceptions import (
        DataingError,
        AuthError,
        RateLimitError,
        ValidationError,
    )

    client = DataingClient(api_key="your-key")

    try:
        run = client.run(assets=[...], goal="Investigate nulls")
    except AuthError:
        print("Invalid or expired API key")
    except RateLimitError as e:
        print(f"Rate limited. Retry after {e.retry_after} seconds")
    except ValidationError as e:
        print(f"Invalid request: {e}")
    except DataingError as e:
        print(f"API error: {e}")
    ```
"""

from __future__ import annotations


class DataingError(Exception):
    """Base exception for all Dataing SDK errors.

    All SDK exceptions inherit from this class, allowing catch-all handling:

    Example:
        ```python
        try:
            result = client.run(...)
        except DataingError as e:
            logger.error(f"Dataing API error: {e}")
        ```
    """

    pass


class AuthError(DataingError):
    """Authentication or authorization failed (HTTP 401/403).

    Raised when:
        - API key is missing or invalid (401)
        - API key lacks required permissions (403)
        - Token has expired (401)

    Example:
        ```python
        try:
            client = DataingClient(api_key="invalid-key")
            client.health()
        except AuthError:
            print("Check your API key at https://app.dataing.io/settings/api-keys")
        ```
    """

    pass


class RateLimitError(DataingError):
    """API rate limit exceeded (HTTP 429).

    The ``retry_after`` attribute indicates how long to wait before retrying.

    Attributes:
        retry_after: Seconds to wait before retrying (from Retry-After header).

    Example:
        ```python
        import time

        try:
            result = client.run(...)
        except RateLimitError as e:
            if e.retry_after:
                print(f"Rate limited. Waiting {e.retry_after}s...")
                time.sleep(e.retry_after)
                result = client.run(...)  # Retry
        ```
    """

    retry_after: float | None

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Initialize rate limit error.

        Args:
            message: Error message describing the rate limit.
            retry_after: Seconds to wait before retrying (from Retry-After header).
        """
        super().__init__(message)
        self.retry_after = retry_after


class AmbiguousAssetError(DataingError):
    """Asset reference matched multiple datasources (HTTP 409).

    Raised when an asset URN could belong to multiple configured datasources
    and no explicit ``datasource_id`` was provided to disambiguate.

    Attributes:
        candidates: List of possible datasource matches with id and name.

    Example:
        ```python
        try:
            ctx = client.context("postgres://db.schema.orders")
        except AmbiguousAssetError as e:
            print("Multiple datasources match. Please specify one:")
            for ds in e.candidates:
                print(f"  - {ds['name']} (ID: {ds['id']})")
            # Retry with explicit datasource
            ctx = client.context(
                assets=[AssetRef(..., datasource_id=e.candidates[0]['id'])]
            )
        ```

    See Also:
        - :doc:`/concepts/datasource-resolution`: How datasources are resolved
    """

    candidates: list[dict]

    def __init__(self, message: str, candidates: list[dict] | None = None) -> None:
        """Initialize ambiguous asset error.

        Args:
            message: Error message with disambiguation hint.
            candidates: List of possible datasource matches with id and name.
        """
        super().__init__(message)
        self.candidates = candidates or []


class NotFoundError(DataingError):
    """Requested resource not found (HTTP 404).

    Raised when:
        - Run ID doesn't exist
        - Bundle ID doesn't exist
        - Datasource ID doesn't exist

    Example:
        ```python
        try:
            run = client.get_run("nonexistent-run-id")
        except NotFoundError:
            print("Run not found. It may have been deleted or expired.")
        ```
    """

    pass


class ValidationError(DataingError):
    """Request validation failed (HTTP 422).

    Raised when:
        - Required fields are missing
        - Field values are invalid (wrong type, out of range)
        - URN format is invalid

    Example:
        ```python
        try:
            # Missing required 'goal' parameter
            run = client.run(assets=[...], goal="")
        except ValidationError as e:
            print(f"Invalid request: {e}")
        ```
    """

    pass


class ServerError(DataingError):
    """Server-side error occurred (HTTP 5xx).

    Raised when the Dataing API encounters an internal error. These are
    typically transient and can be retried.

    Example:
        ```python
        import time

        for attempt in range(3):
            try:
                result = client.run(...)
                break
            except ServerError:
                if attempt < 2:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise
        ```
    """

    pass


class TimeoutError(DataingError):
    """Request timed out.

    Raised when an API request exceeds the configured timeout. Increase the
    ``timeout`` parameter when creating the client for long-running operations.

    Example:
        ```python
        # Increase timeout for large context bundles
        client = DataingClient(api_key="...", timeout=60.0)
        ```
    """

    pass


class StreamError(DataingError):
    """Error during SSE streaming.

    Base class for errors that occur during `DataingClient.stream_run`.

    Example:
        ```python
        try:
            for event in client.stream_run(run.run_id):
                process(event)
        except StreamError as e:
            print(f"Stream interrupted: {e}")
            # Events can be resumed from last seq
        ```
    """

    pass


class ReplayWindowExpiredError(StreamError):
    """SSE replay window has expired (HTTP 410 Gone).

    Raised when attempting to resume a stream from a sequence number that
    is no longer available. The server only keeps events for a limited time
    (typically 30 seconds) for replay.

    Example:
        ```python
        try:
            # Attempting to resume from old sequence
            for event in client.stream_run(run.run_id, last_seq=old_seq):
                process(event)
        except ReplayWindowExpiredError:
            print("Replay window expired. Starting from beginning.")
            for event in client.stream_run(run.run_id):
                process(event)
        ```
    """

    pass
