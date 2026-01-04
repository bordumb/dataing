"""Tests for adapter error classes."""

import pytest
from dataing.adapters.datasource.errors import (
    ErrorCode,
    AdapterError,
    ConnectionFailedError,
    ConnectionTimeoutError,
    AuthenticationFailedError,
    SSLError,
    AccessDeniedError,
    InsufficientPermissionsError,
    QuerySyntaxError,
    QueryTimeoutError,
    QueryCancelledError,
    ResourceExhaustedError,
    RateLimitedError,
    TableNotFoundError,
    ColumnNotFoundError,
    SchemaFetchFailedError,
    InvalidConfigError,
    MissingRequiredFieldError,
    NotImplementedError,
    InternalError,
)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_connection_error_codes(self):
        """Verify connection error codes exist."""
        assert ErrorCode.CONNECTION_FAILED.value == "CONNECTION_FAILED"
        assert ErrorCode.CONNECTION_TIMEOUT.value == "CONNECTION_TIMEOUT"
        assert ErrorCode.AUTHENTICATION_FAILED.value == "AUTHENTICATION_FAILED"
        assert ErrorCode.SSL_ERROR.value == "SSL_ERROR"

    def test_permission_error_codes(self):
        """Verify permission error codes exist."""
        assert ErrorCode.ACCESS_DENIED.value == "ACCESS_DENIED"
        assert ErrorCode.INSUFFICIENT_PERMISSIONS.value == "INSUFFICIENT_PERMISSIONS"

    def test_query_error_codes(self):
        """Verify query error codes exist."""
        assert ErrorCode.QUERY_SYNTAX_ERROR.value == "QUERY_SYNTAX_ERROR"
        assert ErrorCode.QUERY_TIMEOUT.value == "QUERY_TIMEOUT"
        assert ErrorCode.QUERY_CANCELLED.value == "QUERY_CANCELLED"
        assert ErrorCode.RESOURCE_EXHAUSTED.value == "RESOURCE_EXHAUSTED"

    def test_schema_error_codes(self):
        """Verify schema error codes exist."""
        assert ErrorCode.TABLE_NOT_FOUND.value == "TABLE_NOT_FOUND"
        assert ErrorCode.COLUMN_NOT_FOUND.value == "COLUMN_NOT_FOUND"
        assert ErrorCode.SCHEMA_FETCH_FAILED.value == "SCHEMA_FETCH_FAILED"

    def test_config_error_codes(self):
        """Verify config error codes exist."""
        assert ErrorCode.INVALID_CONFIG.value == "INVALID_CONFIG"
        assert ErrorCode.MISSING_REQUIRED_FIELD.value == "MISSING_REQUIRED_FIELD"

    def test_other_error_codes(self):
        """Verify other error codes exist."""
        assert ErrorCode.RATE_LIMITED.value == "RATE_LIMITED"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"
        assert ErrorCode.NOT_IMPLEMENTED.value == "NOT_IMPLEMENTED"


class TestAdapterError:
    """Tests for base AdapterError class."""

    def test_basic_error(self):
        """Test creating a basic adapter error."""
        error = AdapterError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Something went wrong",
        )
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.message == "Something went wrong"
        assert error.details == {}
        assert error.retryable is False
        assert error.retry_after_seconds is None

    def test_error_with_details(self):
        """Test error with details dictionary."""
        error = AdapterError(
            code=ErrorCode.CONNECTION_FAILED,
            message="Failed to connect",
            details={"host": "localhost", "port": 5432},
        )
        assert error.details == {"host": "localhost", "port": 5432}

    def test_retryable_error(self):
        """Test retryable error with retry after."""
        error = AdapterError(
            code=ErrorCode.RATE_LIMITED,
            message="Too many requests",
            retryable=True,
            retry_after_seconds=60,
        )
        assert error.retryable is True
        assert error.retry_after_seconds == 60

    def test_to_dict(self):
        """Test error to_dict conversion."""
        error = AdapterError(
            code=ErrorCode.QUERY_TIMEOUT,
            message="Query timed out",
            details={"timeout": 30},
            retryable=True,
            retry_after_seconds=5,
        )
        result = error.to_dict()
        assert result == {
            "error": {
                "code": "QUERY_TIMEOUT",
                "message": "Query timed out",
                "details": {"timeout": 30},
                "retryable": True,
                "retry_after_seconds": 5,
            }
        }

    def test_to_dict_without_details(self):
        """Test to_dict with no details."""
        error = AdapterError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Error",
        )
        result = error.to_dict()
        assert result["error"]["details"] is None

    def test_error_is_exception(self):
        """Test that AdapterError is an exception."""
        error = AdapterError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Test message",
        )
        assert isinstance(error, Exception)
        assert str(error) == "Test message"


class TestConnectionFailedError:
    """Tests for ConnectionFailedError."""

    def test_default_message(self):
        """Test default error message."""
        error = ConnectionFailedError()
        assert error.code == ErrorCode.CONNECTION_FAILED
        assert error.message == "Failed to connect to data source"
        assert error.retryable is True

    def test_custom_message(self):
        """Test custom error message."""
        error = ConnectionFailedError(
            message="Cannot reach host",
            details={"host": "db.example.com"},
        )
        assert error.message == "Cannot reach host"
        assert error.details == {"host": "db.example.com"}


class TestConnectionTimeoutError:
    """Tests for ConnectionTimeoutError."""

    def test_default_message(self):
        """Test default error message."""
        error = ConnectionTimeoutError()
        assert error.code == ErrorCode.CONNECTION_TIMEOUT
        assert error.message == "Connection timed out"
        assert error.retryable is True

    def test_with_timeout(self):
        """Test with timeout details."""
        error = ConnectionTimeoutError(
            message="Connection took too long",
            timeout_seconds=30,
        )
        assert error.details == {"timeout_seconds": 30}


class TestAuthenticationFailedError:
    """Tests for AuthenticationFailedError."""

    def test_default_message(self):
        """Test default error message."""
        error = AuthenticationFailedError()
        assert error.code == ErrorCode.AUTHENTICATION_FAILED
        assert error.message == "Authentication failed"
        assert error.retryable is False

    def test_with_details(self):
        """Test with custom details."""
        error = AuthenticationFailedError(
            message="Invalid password",
            details={"username": "admin"},
        )
        assert error.message == "Invalid password"
        assert error.details == {"username": "admin"}


class TestSSLError:
    """Tests for SSLError."""

    def test_default_message(self):
        """Test default error message."""
        error = SSLError()
        assert error.code == ErrorCode.SSL_ERROR
        assert error.message == "SSL connection error"
        assert error.retryable is False


class TestAccessDeniedError:
    """Tests for AccessDeniedError."""

    def test_default_message(self):
        """Test default error message."""
        error = AccessDeniedError()
        assert error.code == ErrorCode.ACCESS_DENIED
        assert error.message == "Access denied"
        assert error.retryable is False

    def test_with_resource(self):
        """Test with resource specified."""
        error = AccessDeniedError(
            message="Cannot access table",
            resource="public.users",
        )
        assert error.details == {"resource": "public.users"}


class TestInsufficientPermissionsError:
    """Tests for InsufficientPermissionsError."""

    def test_default_message(self):
        """Test default error message."""
        error = InsufficientPermissionsError()
        assert error.code == ErrorCode.INSUFFICIENT_PERMISSIONS
        assert error.message == "Insufficient permissions"
        assert error.retryable is False

    def test_with_permission(self):
        """Test with required permission specified."""
        error = InsufficientPermissionsError(
            required_permission="SELECT",
        )
        assert error.details == {"required_permission": "SELECT"}


class TestQuerySyntaxError:
    """Tests for QuerySyntaxError."""

    def test_default_message(self):
        """Test default error message."""
        error = QuerySyntaxError()
        assert error.code == ErrorCode.QUERY_SYNTAX_ERROR
        assert error.message == "Query syntax error"
        assert error.retryable is False

    def test_with_query(self):
        """Test with query preview."""
        error = QuerySyntaxError(
            message="Unexpected token",
            query="SELECT * FORM users",
        )
        assert error.details == {"query_preview": "SELECT * FORM users"}

    def test_long_query_truncated(self):
        """Test that long queries are truncated."""
        long_query = "SELECT " + "x, " * 100
        error = QuerySyntaxError(query=long_query)
        assert len(error.details["query_preview"]) == 200

    def test_with_position(self):
        """Test with error position."""
        error = QuerySyntaxError(
            query="SELECT * FROM",
            position=14,
        )
        assert error.details["position"] == 14


class TestQueryTimeoutError:
    """Tests for QueryTimeoutError."""

    def test_default_message(self):
        """Test default error message."""
        error = QueryTimeoutError()
        assert error.code == ErrorCode.QUERY_TIMEOUT
        assert error.message == "Query timed out"
        assert error.retryable is True

    def test_with_timeout(self):
        """Test with timeout specified."""
        error = QueryTimeoutError(timeout_seconds=60)
        assert error.details == {"timeout_seconds": 60}


class TestQueryCancelledError:
    """Tests for QueryCancelledError."""

    def test_default_message(self):
        """Test default error message."""
        error = QueryCancelledError()
        assert error.code == ErrorCode.QUERY_CANCELLED
        assert error.message == "Query was cancelled"
        assert error.retryable is True


class TestResourceExhaustedError:
    """Tests for ResourceExhaustedError."""

    def test_default_message(self):
        """Test default error message."""
        error = ResourceExhaustedError()
        assert error.code == ErrorCode.RESOURCE_EXHAUSTED
        assert error.message == "Resource limits exceeded"
        assert error.retryable is True
        assert error.retry_after_seconds == 60

    def test_with_resource_type(self):
        """Test with resource type specified."""
        error = ResourceExhaustedError(resource_type="memory")
        assert error.details == {"resource_type": "memory"}


class TestRateLimitedError:
    """Tests for RateLimitedError."""

    def test_default_message(self):
        """Test default error message."""
        error = RateLimitedError()
        assert error.code == ErrorCode.RATE_LIMITED
        assert error.message == "Rate limit exceeded"
        assert error.retryable is True
        assert error.retry_after_seconds == 60

    def test_custom_retry_after(self):
        """Test with custom retry after."""
        error = RateLimitedError(retry_after_seconds=120)
        assert error.retry_after_seconds == 120


class TestTableNotFoundError:
    """Tests for TableNotFoundError."""

    def test_with_table_name(self):
        """Test with table name."""
        error = TableNotFoundError(table_name="users")
        assert error.code == ErrorCode.TABLE_NOT_FOUND
        assert error.message == "Table not found: users"
        assert error.details == {"table_name": "users"}
        assert error.retryable is False

    def test_custom_message(self):
        """Test with custom message."""
        error = TableNotFoundError(
            table_name="orders",
            message="The orders table does not exist",
        )
        assert error.message == "The orders table does not exist"


class TestColumnNotFoundError:
    """Tests for ColumnNotFoundError."""

    def test_with_column_name(self):
        """Test with column name."""
        error = ColumnNotFoundError(column_name="email")
        assert error.code == ErrorCode.COLUMN_NOT_FOUND
        assert error.message == "Column not found: email"
        assert error.details == {"column_name": "email"}

    def test_with_table_name(self):
        """Test with table name included."""
        error = ColumnNotFoundError(
            column_name="email",
            table_name="users",
        )
        assert error.details == {"column_name": "email", "table_name": "users"}


class TestSchemaFetchFailedError:
    """Tests for SchemaFetchFailedError."""

    def test_default_message(self):
        """Test default error message."""
        error = SchemaFetchFailedError()
        assert error.code == ErrorCode.SCHEMA_FETCH_FAILED
        assert error.message == "Failed to fetch schema"
        assert error.retryable is True


class TestInvalidConfigError:
    """Tests for InvalidConfigError."""

    def test_default_message(self):
        """Test default error message."""
        error = InvalidConfigError()
        assert error.code == ErrorCode.INVALID_CONFIG
        assert error.message == "Invalid configuration"
        assert error.retryable is False

    def test_with_field(self):
        """Test with field specified."""
        error = InvalidConfigError(
            message="Port must be a number",
            field="port",
        )
        assert error.details == {"field": "port"}


class TestMissingRequiredFieldError:
    """Tests for MissingRequiredFieldError."""

    def test_with_field(self):
        """Test with field name."""
        error = MissingRequiredFieldError(field="host")
        assert error.code == ErrorCode.MISSING_REQUIRED_FIELD
        assert error.message == "Missing required field: host"
        assert error.details == {"field": "host"}

    def test_custom_message(self):
        """Test with custom message."""
        error = MissingRequiredFieldError(
            field="password",
            message="Password is required for authentication",
        )
        assert error.message == "Password is required for authentication"


class TestNotImplementedError:
    """Tests for NotImplementedError (custom)."""

    def test_with_feature(self):
        """Test with feature name."""
        error = NotImplementedError(feature="streaming")
        assert error.code == ErrorCode.NOT_IMPLEMENTED
        assert error.message == "Feature not implemented: streaming"
        assert error.details == {"feature": "streaming", "adapter_type": None}

    def test_with_adapter_type(self):
        """Test with adapter type specified."""
        error = NotImplementedError(
            feature="window functions",
            adapter_type="mongodb",
        )
        assert error.message == "Feature not implemented for mongodb: window functions"
        assert error.details == {"feature": "window functions", "adapter_type": "mongodb"}


class TestInternalError:
    """Tests for InternalError."""

    def test_default_message(self):
        """Test default error message."""
        error = InternalError()
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.message == "Internal error"
        assert error.retryable is False

    def test_with_details(self):
        """Test with details."""
        error = InternalError(
            message="Unexpected null pointer",
            details={"trace": "..."},
        )
        assert error.details == {"trace": "..."}
