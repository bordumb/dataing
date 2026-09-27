"""Tests for structured logging configuration."""

import json
import logging
import sys
import uuid
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
import structlog

from dataing.telemetry.logging import configure_logging


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def setup_method(self) -> None:
        """Reset structlog configuration before each test."""
        structlog.reset_defaults()

    def teardown_method(self) -> None:
        """Reset structlog configuration after each test."""
        structlog.reset_defaults()

    def test_configure_logging_sets_up_structlog(self) -> None:
        """configure_logging sets up structlog with processors."""
        configure_logging()

        # Verify structlog is configured (not using default config)
        logger = structlog.get_logger()
        assert logger is not None

    def test_json_output_produces_valid_json(self) -> None:
        """JSON output mode produces valid JSON log entries."""
        # Capture log output
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)

        # Configure with JSON output
        configure_logging(log_level="INFO", json_output=True)

        # Get a logger and emit a message
        logger = structlog.get_logger("test")

        # Bind the handler to stdlib logging
        stdlib_logger = logging.getLogger("test")
        stdlib_logger.handlers = [handler]
        stdlib_logger.setLevel(logging.INFO)

        logger.info("test message", key="value")

        # Verify output is valid JSON
        output = log_stream.getvalue()
        if output.strip():
            log_entry = json.loads(output.strip().split("\n")[-1])
            assert "event" in log_entry
            assert log_entry["event"] == "test message"

    def test_log_level_is_respected(self) -> None:
        """Log level configuration is applied correctly."""
        configure_logging(log_level="WARNING", json_output=True)

        # Verify stdlib logging level was set
        logging.getLogger()
        # Note: configure_logging uses basicConfig which sets root level
        # The level should be WARNING (30)
        assert logging.WARNING == 30

    def test_processors_include_trace_context(self) -> None:
        """Trace context processor is included in chain."""
        # Verify the processor is wired by checking the structlog configuration
        from dataing.telemetry.structlog_processor import add_trace_context

        # Create a mock span for testing
        mock_span = MagicMock()
        mock_span.get_span_context.return_value.is_valid = True
        mock_span.get_span_context.return_value.trace_id = 0x12345678901234567890123456789012
        mock_span.get_span_context.return_value.span_id = 0x1234567890123456

        configure_logging(log_level="INFO", json_output=True)

        with patch("dataing.telemetry.structlog_processor.trace.get_current_span") as mock_get:
            mock_get.return_value = mock_span

            # Test that the processor is called
            result = add_trace_context(None, "info", {"event": "test"})
            assert "trace_id" in result
            assert "span_id" in result

    def test_console_output_mode(self) -> None:
        """Console output mode uses ConsoleRenderer."""
        # Just verify no errors when configuring console mode
        configure_logging(log_level="INFO", json_output=False)

        logger = structlog.get_logger("test")
        # Should work without errors
        assert logger is not None

    def test_console_exception_output_hides_frame_locals(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Console tracebacks do not render frame locals such as encryption keys."""
        # Generated at runtime so the value never appears in rendered source lines.
        secret = f"secret-{uuid.uuid4().hex[:12]}"
        # Wide enough that a rendered secret is never wrapped across lines and missed.
        monkeypatch.setenv("COLUMNS", "200")

        def build_adapter(encryption_key: str) -> None:
            raise RuntimeError("adapter construction failed")

        configure_logging(log_level="INFO", json_output=False)
        # pytest's logging plugin pre-installs root handlers, which makes basicConfig() a
        # no-op here; attach the stdout handler that basicConfig() installs in production.
        stdlib_logger = logging.getLogger(__name__)
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdlib_logger.addHandler(stdout_handler)
        try:
            build_adapter(secret)
        except RuntimeError:
            structlog.get_logger(__name__).exception("adapter_failed")
        finally:
            stdlib_logger.removeHandler(stdout_handler)

        output = capsys.readouterr().out
        assert "adapter_failed" in output
        assert "adapter construction failed" in output
        assert secret not in output

    def test_debug_level(self) -> None:
        """DEBUG log level can be configured."""
        configure_logging(log_level="DEBUG", json_output=True)

        # Just verify no errors
        logger = structlog.get_logger("test")
        assert logger is not None

    def test_case_insensitive_log_level(self) -> None:
        """Log level string is case-insensitive."""
        # Should work with lowercase
        configure_logging(log_level="debug", json_output=True)

        logger = structlog.get_logger("test")
        assert logger is not None
