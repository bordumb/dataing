"""Unit tests for exceptions."""

from __future__ import annotations

import pytest

from dataing.core.exceptions import (
    CircuitBreakerTripped,
    DataingError,
    LLMError,
    QueryValidationError,
    SchemaDiscoveryError,
    TimeoutError,
)


class TestDataingError:
    """Tests for DataingError."""

    def test_is_exception(self) -> None:
        """Test that DataingError is an Exception."""
        assert issubclass(DataingError, Exception)

    def test_can_raise(self) -> None:
        """Test that DataingError can be raised."""
        with pytest.raises(DataingError):
            raise DataingError("Test error")


class TestSchemaDiscoveryError:
    """Tests for SchemaDiscoveryError."""

    def test_inherits_from_dataing_error(self) -> None:
        """Test that SchemaDiscoveryError inherits from DataingError."""
        assert issubclass(SchemaDiscoveryError, DataingError)

    def test_can_be_caught_as_dataing_error(self) -> None:
        """Test that SchemaDiscoveryError can be caught as DataingError."""
        with pytest.raises(DataingError):
            raise SchemaDiscoveryError("Schema not found")


class TestCircuitBreakerTripped:
    """Tests for CircuitBreakerTripped."""

    def test_inherits_from_dataing_error(self) -> None:
        """Test that CircuitBreakerTripped inherits from DataingError."""
        assert issubclass(CircuitBreakerTripped, DataingError)

    def test_can_raise_with_message(self) -> None:
        """Test raising with a message."""
        with pytest.raises(CircuitBreakerTripped) as exc_info:
            raise CircuitBreakerTripped("Query limit exceeded")

        assert "Query limit exceeded" in str(exc_info.value)


class TestQueryValidationError:
    """Tests for QueryValidationError."""

    def test_inherits_from_dataing_error(self) -> None:
        """Test that QueryValidationError inherits from DataingError."""
        assert issubclass(QueryValidationError, DataingError)


class TestLLMError:
    """Tests for LLMError."""

    def test_inherits_from_dataing_error(self) -> None:
        """Test that LLMError inherits from DataingError."""
        assert issubclass(LLMError, DataingError)

    def test_default_retryable(self) -> None:
        """Test that LLMError is retryable by default."""
        error = LLMError("API error")
        assert error.retryable is True

    def test_non_retryable(self) -> None:
        """Test creating a non-retryable LLMError."""
        error = LLMError("Invalid response", retryable=False)
        assert error.retryable is False

    def test_message_preserved(self) -> None:
        """Test that message is preserved."""
        error = LLMError("Custom error message")
        assert str(error) == "Custom error message"


class TestTimeoutError:
    """Tests for TimeoutError."""

    def test_inherits_from_dataing_error(self) -> None:
        """Test that TimeoutError inherits from DataingError."""
        assert issubclass(TimeoutError, DataingError)
