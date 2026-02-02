"""Tests for log_parser module."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dataing.core.parsing.log_parser import LogEntry, LogLevel, LogParser


@pytest.fixture
def log_parser() -> LogParser:
    """Create a log parser instance."""
    return LogParser()


@pytest.fixture
def sample_log_file(tmp_path: Path) -> Path:
    """Create a sample log file."""
    content = """2024-01-15 10:30:45 INFO Starting application
2024-01-15 10:30:46 DEBUG Loading configuration
2024-01-15 10:30:47 WARNING Config file not found, using defaults
2024-01-15 10:30:48 ERROR Failed to connect to database
2024-01-15 10:30:49 INFO Application started successfully
"""
    file_path = tmp_path / "app.log"
    file_path.write_text(content)
    return file_path


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_levels_exist(self) -> None:
        """Test all expected levels exist."""
        assert LogLevel.DEBUG.value == "debug"
        assert LogLevel.INFO.value == "info"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.ERROR.value == "error"
        assert LogLevel.CRITICAL.value == "critical"
        assert LogLevel.UNKNOWN.value == "unknown"


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_entry_creation(self) -> None:
        """Test creating a log entry."""
        entry = LogEntry(
            timestamp=datetime(2024, 1, 15, 10, 30, 45),
            level=LogLevel.INFO,
            message="Test message",
            source="test_module",
            line_number=1,
            raw="2024-01-15 10:30:45 INFO test_module: Test message",
        )

        assert entry.timestamp.year == 2024
        assert entry.level == LogLevel.INFO
        assert entry.message == "Test message"
        assert entry.source == "test_module"


class TestLogParser:
    """Tests for LogParser class."""

    def test_parse_file(self, log_parser: LogParser, sample_log_file: Path) -> None:
        """Test parsing a log file."""
        entries = log_parser.parse_file(sample_log_file)

        assert len(entries) == 5
        assert entries[0].level == LogLevel.INFO
        assert entries[2].level == LogLevel.WARNING
        assert entries[3].level == LogLevel.ERROR

    def test_parse_with_max_entries(self, log_parser: LogParser, sample_log_file: Path) -> None:
        """Test parsing with entry limit."""
        entries = log_parser.parse_file(sample_log_file, max_entries=2)

        assert len(entries) == 2

    def test_parse_with_level_filter(self, log_parser: LogParser, sample_log_file: Path) -> None:
        """Test parsing with level filter."""
        entries = log_parser.parse_file(sample_log_file, level_filter=LogLevel.WARNING)

        # Should only get WARNING and ERROR
        assert len(entries) == 2
        assert all(
            e.level in (LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL) for e in entries
        )

    def test_parse_iso_timestamp(self, log_parser: LogParser, tmp_path: Path) -> None:
        """Test parsing ISO 8601 timestamps."""
        file_path = tmp_path / "iso.log"
        file_path.write_text("2024-01-15T10:30:45.123Z INFO Message")

        entries = log_parser.parse_file(file_path)

        assert len(entries) == 1
        assert entries[0].timestamp is not None
        assert entries[0].timestamp.year == 2024

    def test_parse_json_log(self, log_parser: LogParser, tmp_path: Path) -> None:
        """Test parsing JSON-formatted log lines."""
        content = '{"timestamp": "2024-01-15T10:30:45", "level": "INFO", "message": "Test"}\n'
        file_path = tmp_path / "json.log"
        file_path.write_text(content)

        entries = log_parser.parse_file(file_path)

        assert len(entries) == 1
        assert entries[0].level == LogLevel.INFO
        assert entries[0].message == "Test"

    def test_find_errors(self, log_parser: LogParser, sample_log_file: Path) -> None:
        """Test finding errors with context."""
        errors = log_parser.find_errors(sample_log_file, context_lines=1)

        assert len(errors) == 1
        assert errors[0]["entry"].level == LogLevel.ERROR
        assert len(errors[0]["context_before"]) == 1
        assert len(errors[0]["context_after"]) == 1

    def test_get_summary(self, log_parser: LogParser, sample_log_file: Path) -> None:
        """Test log file summary."""
        summary = log_parser.get_summary(sample_log_file)

        assert summary["total_lines"] == 5
        assert summary["level_counts"]["info"] == 2
        assert summary["level_counts"]["debug"] == 1
        assert summary["level_counts"]["warning"] == 1
        assert summary["level_counts"]["error"] == 1
        assert len(summary["sample_errors"]) == 1

    def test_parse_lines_directly(self, log_parser: LogParser) -> None:
        """Test parsing lines without file."""
        lines = [
            "2024-01-15 10:30:45 INFO First message",
            "2024-01-15 10:30:46 ERROR Second message",
        ]

        entries = log_parser.parse_lines(lines)

        assert len(entries) == 2
        assert entries[0].level == LogLevel.INFO
        assert entries[1].level == LogLevel.ERROR

    def test_file_not_found(self, log_parser: LogParser) -> None:
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            log_parser.parse_file("/nonexistent/file.log")

    def test_file_size_limit(self, log_parser: LogParser, tmp_path: Path) -> None:
        """Test file size limit."""
        parser = LogParser(max_file_size=100)
        file_path = tmp_path / "large.log"
        file_path.write_text("x" * 200)

        with pytest.raises(ValueError, match="exceeds size limit"):
            parser.parse_file(file_path)

    def test_unknown_level(self, log_parser: LogParser) -> None:
        """Test handling of unknown log level."""
        entries = log_parser.parse_lines(["Some message without level"])

        assert len(entries) == 1
        assert entries[0].level == LogLevel.UNKNOWN

    def test_multiline_support(self, log_parser: LogParser, tmp_path: Path) -> None:
        """Test that each line is parsed independently."""
        content = """2024-01-15 10:30:45 ERROR Exception occurred
java.lang.NullPointerException
    at com.example.Main.run(Main.java:42)
2024-01-15 10:30:46 INFO Continuing execution
"""
        file_path = tmp_path / "multi.log"
        file_path.write_text(content)

        entries = log_parser.parse_file(file_path)

        # Each line is a separate entry
        assert len(entries) == 4
