"""Tests for CLI error handling."""

from __future__ import annotations

import pytest
import typer
from dataing_cli.errors import CLIError, cli_error_handler, handle_sdk_error
from dataing_sdk.exceptions import (
    AmbiguousAssetError,
    AuthError,
    DataingError,
    NotFoundError,
    RateLimitError,
    ServerError,
    StreamError,
    ValidationError,
)


class TestCLIError:
    """Tests for CLIError class."""

    def test_cli_error_defaults(self) -> None:
        """Test CLIError with default exit code."""
        error = CLIError("Test error")
        assert error.message == "Test error"
        assert error.exit_code == 1

    def test_cli_error_custom_exit_code(self) -> None:
        """Test CLIError with custom exit code."""
        error = CLIError("Validation failed", exit_code=2)
        assert error.message == "Validation failed"
        assert error.exit_code == 2


class TestHandleSDKError:
    """Tests for handle_sdk_error function."""

    def test_auth_error_exits_1(self) -> None:
        """Test AuthError exits with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(AuthError("Invalid API key"))
        assert exc_info.value.exit_code == 1

    def test_not_found_error_exits_1(self) -> None:
        """Test NotFoundError exits with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(NotFoundError("Resource not found"))
        assert exc_info.value.exit_code == 1

    def test_rate_limit_error_exits_1(self) -> None:
        """Test RateLimitError exits with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(RateLimitError("Rate limited", retry_after=30))
        assert exc_info.value.exit_code == 1

    def test_validation_error_exits_2(self) -> None:
        """Test ValidationError exits with code 2."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(ValidationError("Invalid input"))
        assert exc_info.value.exit_code == 2

    def test_ambiguous_asset_error_exits_1(self) -> None:
        """Test AmbiguousAssetError exits with code 1."""
        candidates = [
            {"id": "ds-1", "name": "prod-db"},
            {"id": "ds-2", "name": "staging-db"},
        ]
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(AmbiguousAssetError("Multiple matches", candidates))
        assert exc_info.value.exit_code == 1

    def test_server_error_exits_1(self) -> None:
        """Test ServerError exits with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(ServerError("Internal server error"))
        assert exc_info.value.exit_code == 1

    def test_stream_error_exits_1(self) -> None:
        """Test StreamError exits with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(StreamError("Stream interrupted"))
        assert exc_info.value.exit_code == 1

    def test_generic_dataing_error_exits_1(self) -> None:
        """Test generic DataingError exits with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            handle_sdk_error(DataingError("Something went wrong"))
        assert exc_info.value.exit_code == 1


class TestCLIErrorHandler:
    """Tests for cli_error_handler decorator."""

    def test_successful_function_returns_normally(self) -> None:
        """Test decorated function returns normally on success."""

        @cli_error_handler
        def success_func() -> str:
            return "success"

        assert success_func() == "success"

    def test_dataing_error_is_handled(self) -> None:
        """Test DataingError is caught and handled."""

        @cli_error_handler
        def error_func() -> None:
            raise AuthError("Bad key")

        with pytest.raises(typer.Exit) as exc_info:
            error_func()
        assert exc_info.value.exit_code == 1

    def test_cli_error_is_handled(self) -> None:
        """Test CLIError is caught and handled."""

        @cli_error_handler
        def cli_error_func() -> None:
            raise CLIError("Custom error", exit_code=3)

        with pytest.raises(typer.Exit) as exc_info:
            cli_error_func()
        assert exc_info.value.exit_code == 3

    def test_connection_error_is_handled(self) -> None:
        """Test ConnectionError is caught and handled."""

        @cli_error_handler
        def connection_error_func() -> None:
            raise ConnectionError("Connection refused")

        with pytest.raises(typer.Exit) as exc_info:
            connection_error_func()
        assert exc_info.value.exit_code == 1

    def test_keyboard_interrupt_is_handled(self) -> None:
        """Test KeyboardInterrupt is caught and handled."""

        @cli_error_handler
        def interrupt_func() -> None:
            raise KeyboardInterrupt()

        with pytest.raises(typer.Exit) as exc_info:
            interrupt_func()
        assert exc_info.value.exit_code == 130

    def test_unhandled_exception_propagates(self) -> None:
        """Test unhandled exceptions propagate."""

        @cli_error_handler
        def unhandled_func() -> None:
            raise ValueError("This should propagate")

        with pytest.raises(ValueError):
            unhandled_func()
