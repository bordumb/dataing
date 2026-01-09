"""Error definitions for the adapter layer.

This module defines all adapter-specific exceptions with consistent
error codes that can be mapped across all source types.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Standardized error codes for all adapters."""

    # Connection errors
    CONNECTION_FAILED = "CONNECTION_FAILED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    SSL_ERROR = "SSL_ERROR"

    # Permission errors
    ACCESS_DENIED = "ACCESS_DENIED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"

    # Query errors
    QUERY_SYNTAX_ERROR = "QUERY_SYNTAX_ERROR"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    QUERY_CANCELLED = "QUERY_CANCELLED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"

    # Rate limiting
    RATE_LIMITED = "RATE_LIMITED"

    # Schema errors
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"
    SCHEMA_FETCH_FAILED = "SCHEMA_FETCH_FAILED"

    # Configuration errors
    INVALID_CONFIG = "INVALID_CONFIG"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class AdapterError(Exception):
    """Base exception for all adapter errors.

    Attributes:
        code: Standardized error code.
        message: Human-readable error message.
        details: Additional error details.
        retryable: Whether the operation can be retried.
        retry_after_seconds: Suggested wait time before retry.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        """Initialize the adapter error."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for API response."""
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details if self.details else None,
                "retryable": self.retryable,
                "retry_after_seconds": self.retry_after_seconds,
            }
        }


class ConnectionFailedError(AdapterError):
    """Failed to establish connection to data source."""

    def __init__(
        self,
        message: str = "Failed to connect to data source",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize connection failed error."""
        super().__init__(
            code=ErrorCode.CONNECTION_FAILED,
            message=message,
            details=details,
            retryable=True,
        )


class ConnectionTimeoutError(AdapterError):
    """Connection attempt timed out."""

    def __init__(
        self,
        message: str = "Connection timed out",
        timeout_seconds: int | None = None,
    ) -> None:
        """Initialize connection timeout error."""
        super().__init__(
            code=ErrorCode.CONNECTION_TIMEOUT,
            message=message,
            details={"timeout_seconds": timeout_seconds} if timeout_seconds else None,
            retryable=True,
        )


class AuthenticationFailedError(AdapterError):
    """Authentication credentials were rejected."""

    def __init__(
        self,
        message: str = "Authentication failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize authentication failed error."""
        super().__init__(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message=message,
            details=details,
            retryable=False,
        )


class SSLError(AdapterError):
    """SSL/TLS connection error."""

    def __init__(
        self,
        message: str = "SSL connection error",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize SSL error."""
        super().__init__(
            code=ErrorCode.SSL_ERROR,
            message=message,
            details=details,
            retryable=False,
        )


class AccessDeniedError(AdapterError):
    """Access to resource was denied."""

    def __init__(
        self,
        message: str = "Access denied",
        resource: str | None = None,
    ) -> None:
        """Initialize access denied error."""
        super().__init__(
            code=ErrorCode.ACCESS_DENIED,
            message=message,
            details={"resource": resource} if resource else None,
            retryable=False,
        )


class InsufficientPermissionsError(AdapterError):
    """User lacks required permissions."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        required_permission: str | None = None,
    ) -> None:
        """Initialize insufficient permissions error."""
        super().__init__(
            code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            message=message,
            details={"required_permission": required_permission} if required_permission else None,
            retryable=False,
        )


class QuerySyntaxError(AdapterError):
    """Query syntax is invalid."""

    def __init__(
        self,
        message: str = "Query syntax error",
        query: str | None = None,
        position: int | None = None,
    ) -> None:
        """Initialize query syntax error."""
        details: dict[str, Any] = {}
        if query:
            details["query_preview"] = query[:200] if len(query) > 200 else query
        if position:
            details["position"] = position
        super().__init__(
            code=ErrorCode.QUERY_SYNTAX_ERROR,
            message=message,
            details=details if details else None,
            retryable=False,
        )


class QueryTimeoutError(AdapterError):
    """Query execution timed out."""

    def __init__(
        self,
        message: str = "Query timed out",
        timeout_seconds: int | None = None,
    ) -> None:
        """Initialize query timeout error."""
        super().__init__(
            code=ErrorCode.QUERY_TIMEOUT,
            message=message,
            details={"timeout_seconds": timeout_seconds} if timeout_seconds else None,
            retryable=True,
        )


class QueryCancelledError(AdapterError):
    """Query was cancelled."""

    def __init__(
        self,
        message: str = "Query was cancelled",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize query cancelled error."""
        super().__init__(
            code=ErrorCode.QUERY_CANCELLED,
            message=message,
            details=details,
            retryable=True,
        )


class ResourceExhaustedError(AdapterError):
    """Resource limits exceeded."""

    def __init__(
        self,
        message: str = "Resource limits exceeded",
        resource_type: str | None = None,
    ) -> None:
        """Initialize resource exhausted error."""
        super().__init__(
            code=ErrorCode.RESOURCE_EXHAUSTED,
            message=message,
            details={"resource_type": resource_type} if resource_type else None,
            retryable=True,
            retry_after_seconds=60,
        )


class RateLimitedError(AdapterError):
    """Request was rate limited."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_seconds: int = 60,
    ) -> None:
        """Initialize rate limited error."""
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=message,
            retryable=True,
            retry_after_seconds=retry_after_seconds,
        )


class TableNotFoundError(AdapterError):
    """Table or collection not found."""

    def __init__(
        self,
        table_name: str,
        message: str | None = None,
    ) -> None:
        """Initialize table not found error."""
        super().__init__(
            code=ErrorCode.TABLE_NOT_FOUND,
            message=message or f"Table not found: {table_name}",
            details={"table_name": table_name},
            retryable=False,
        )


class ColumnNotFoundError(AdapterError):
    """Column not found in table."""

    def __init__(
        self,
        column_name: str,
        table_name: str | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize column not found error."""
        details: dict[str, Any] = {"column_name": column_name}
        if table_name:
            details["table_name"] = table_name
        super().__init__(
            code=ErrorCode.COLUMN_NOT_FOUND,
            message=message or f"Column not found: {column_name}",
            details=details,
            retryable=False,
        )


class SchemaFetchFailedError(AdapterError):
    """Failed to fetch schema from data source."""

    def __init__(
        self,
        message: str = "Failed to fetch schema",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize schema fetch failed error."""
        super().__init__(
            code=ErrorCode.SCHEMA_FETCH_FAILED,
            message=message,
            details=details,
            retryable=True,
        )


class InvalidConfigError(AdapterError):
    """Configuration is invalid."""

    def __init__(
        self,
        message: str = "Invalid configuration",
        field: str | None = None,
    ) -> None:
        """Initialize invalid config error."""
        super().__init__(
            code=ErrorCode.INVALID_CONFIG,
            message=message,
            details={"field": field} if field else None,
            retryable=False,
        )


class MissingRequiredFieldError(AdapterError):
    """Required configuration field is missing."""

    def __init__(
        self,
        field: str,
        message: str | None = None,
    ) -> None:
        """Initialize missing required field error."""
        super().__init__(
            code=ErrorCode.MISSING_REQUIRED_FIELD,
            message=message or f"Missing required field: {field}",
            details={"field": field},
            retryable=False,
        )


class NotImplementedError(AdapterError):
    """Feature is not implemented for this adapter."""

    def __init__(
        self,
        feature: str,
        adapter_type: str | None = None,
    ) -> None:
        """Initialize not implemented error."""
        message = f"Feature not implemented: {feature}"
        if adapter_type:
            message = f"Feature not implemented for {adapter_type}: {feature}"
        super().__init__(
            code=ErrorCode.NOT_IMPLEMENTED,
            message=message,
            details={"feature": feature, "adapter_type": adapter_type},
            retryable=False,
        )


class InternalError(AdapterError):
    """Internal adapter error."""

    def __init__(
        self,
        message: str = "Internal error",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize internal error."""
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            message=message,
            details=details,
            retryable=False,
        )
