"""Tests for structured logging configuration."""

import json
import logging
import re
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import structlog
from opentelemetry.sdk.trace import TracerProvider

from dataing.telemetry.logging import configure_logging

# SGR color codes that ConsoleRenderer and Rich put around each field.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def build_adapter(encryption_key: str) -> None:
    """Fail with a secret held in a frame local, like adapter construction does."""
    raise RuntimeError("adapter construction failed")


def get_logger(kind: str) -> Any:
    """Return a structlog or a stdlib logger for this module."""
    if kind == "structlog":
        return structlog.get_logger(__name__)
    return logging.getLogger(__name__)


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

    def test_json_output_produces_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output mode produces valid JSON log entries."""
        configure_logging(log_level="INFO", json_output=True)

        structlog.get_logger("test").info("test message", key="value")

        entry = json.loads(capsys.readouterr().out)
        assert entry["event"] == "test message"
        assert entry["key"] == "value"
        assert entry["level"] == "info"
        assert entry["logger"] == "test"

    def test_json_output_renders_stdlib_records_with_shared_processors(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Records from stdlib loggers get the shared processors and the JSON renderer."""
        configure_logging(log_level="INFO", json_output=True)
        tracer = TracerProvider().get_tracer(__name__)

        with (
            tracer.start_as_current_span("activity") as span,
            structlog.contextvars.bound_contextvars(investigation_id="inv-123"),
        ):
            logging.getLogger("temporalio.worker").warning("poll failed: %s", "timeout")

        entry = json.loads(capsys.readouterr().out)
        assert entry["event"] == "poll failed: timeout"
        assert entry["level"] == "warning"
        assert entry["logger"] == "temporalio.worker"
        assert "timestamp" in entry
        assert entry["investigation_id"] == "inv-123"
        assert entry["trace_id"] == format(span.get_span_context().trace_id, "032x")

    def test_console_output_formats_stdlib_records(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Console stdlib lines show a timestamp, level, and logger name, like structlog's."""
        configure_logging(log_level="INFO", json_output=False)

        logging.getLogger("temporalio.worker").warning("poll failed: %s", "timeout")

        line = ANSI_ESCAPE.sub("", capsys.readouterr().out).rstrip("\n")
        timestamp = r"\d{4}-\d{2}-\d{2}T[\d:.]+Z"
        assert re.fullmatch(
            rf"{timestamp} \[warning\s*\] poll failed: timeout\s+\[temporalio\.worker\]", line
        ), line

    def test_log_level_is_respected(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Records below the configured level are dropped, from structlog and stdlib alike."""
        configure_logging(log_level="WARNING", json_output=True)

        logging.getLogger("svc").info("stdlib_info")
        structlog.get_logger("svc").info("structlog_info")
        logging.getLogger("svc").warning("stdlib_warning")
        structlog.get_logger("svc").warning("structlog_warning")

        lines = capsys.readouterr().out.splitlines()
        assert [json.loads(line)["event"] for line in lines] == [
            "stdlib_warning",
            "structlog_warning",
        ]

    def test_repeat_calls_write_each_record_once(
        self, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Repeat calls (create_app() runs again) replace the handler and keep pytest's."""
        configure_logging(log_level="INFO", json_output=False)
        configure_logging(log_level="INFO", json_output=True)
        configure_logging(log_level="INFO", json_output=True)

        logging.getLogger("svc").warning("once")

        lines = capsys.readouterr().out.splitlines()
        assert [json.loads(line)["event"] for line in lines] == ["once"]
        assert [record.getMessage() for record in caplog.records] == ["once"]

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

    @pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
    @pytest.mark.parametrize("logger_kind", ["structlog", "stdlib"])
    def test_exception_output_hides_frame_locals(
        self,
        json_output: bool,
        logger_kind: str,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Tracebacks do not render frame locals such as encryption keys."""
        # Generated at runtime so the value never appears in rendered source lines.
        secret = f"secret-{uuid.uuid4().hex[:12]}"
        # Wide enough that a rendered secret is never wrapped across lines and missed.
        monkeypatch.setenv("COLUMNS", "200")
        configure_logging(log_level="INFO", json_output=json_output)

        try:
            build_adapter(secret)
        except RuntimeError:
            get_logger(logger_kind).exception("adapter_failed")

        output = capsys.readouterr().out
        assert "adapter_failed" in output
        assert "adapter construction failed" in output
        assert secret not in output

    @pytest.mark.parametrize("logger_kind", ["structlog", "stdlib"])
    def test_json_exception_is_a_single_json_line(
        self, logger_kind: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The traceback goes in the entry's "exception" key, not after it as plain text."""
        configure_logging(log_level="INFO", json_output=True)

        try:
            build_adapter("key")
        except RuntimeError:
            get_logger(logger_kind).exception("adapter_failed")

        entry = json.loads(capsys.readouterr().out)
        assert entry["event"] == "adapter_failed"
        assert entry["level"] == "error"
        assert entry["exception"].startswith("Traceback (most recent call last):")
        assert entry["exception"].endswith("RuntimeError: adapter construction failed")

    @pytest.mark.parametrize("logger_kind", ["structlog", "stdlib"])
    def test_console_exception_traceback_is_rendered_once(
        self, logger_kind: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Only the renderer prints the traceback; logging does not append a plain copy."""
        configure_logging(log_level="INFO", json_output=False)

        try:
            build_adapter("key")
        except RuntimeError:
            get_logger(logger_kind).exception("adapter_failed")

        output = ANSI_ESCAPE.sub("", capsys.readouterr().out)
        assert output.count("Traceback (most recent call last)") == 1

    def test_stdlib_stack_info_shows_the_callers_stack(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """stack_info on a stdlib record renders the caller's stack, not logging internals."""
        configure_logging(log_level="INFO", json_output=True)

        logging.getLogger("svc").info("where", stack_info=True)

        stack = json.loads(capsys.readouterr().out)["stack"]
        assert "test_stdlib_stack_info_shows_the_callers_stack" in stack
        assert logging.__file__ not in stack

    def test_debug_level(self) -> None:
        """DEBUG log level can be configured."""
        configure_logging(log_level="DEBUG", json_output=True)

        # Just verify no errors
        logger = structlog.get_logger("test")
        assert logger is not None

    def test_case_insensitive_log_level(self) -> None:
        """Log level string is case-insensitive."""
        configure_logging(log_level="debug", json_output=True)

        assert logging.getLogger().level == logging.DEBUG
