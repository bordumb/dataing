"""Tests for log provider base classes."""

from __future__ import annotations

from datetime import datetime

from dataing.agents.tools.log_providers.base import (
    LogEntry,
    LogProviderConfig,
    LogResult,
    LogSource,
)


class TestLogSource:
    """Tests for LogSource enum."""

    def test_values(self) -> None:
        """Test all enum values exist."""
        assert LogSource.LOCAL_FILE == "local_file"
        assert LogSource.DOCKER == "docker"
        assert LogSource.CLOUDWATCH == "cloudwatch"
        assert LogSource.KUBERNETES == "kubernetes"


class TestLogProviderConfig:
    """Tests for LogProviderConfig."""

    def test_create_config(self) -> None:
        """Test creating a config."""
        config = LogProviderConfig(
            source=LogSource.LOCAL_FILE,
            name="Test Provider",
        )

        assert config.source == LogSource.LOCAL_FILE
        assert config.name == "Test Provider"
        assert config.enabled is True
        assert config.settings == {}

    def test_create_with_settings(self) -> None:
        """Test creating with settings."""
        config = LogProviderConfig(
            source=LogSource.DOCKER,
            name="Docker Logs",
            enabled=False,
            settings={"host": "tcp://localhost:2375"},
        )

        assert config.enabled is False
        assert config.settings["host"] == "tcp://localhost:2375"


class TestLogEntry:
    """Tests for LogEntry."""

    def test_create_entry(self) -> None:
        """Test creating a log entry."""
        now = datetime.now()
        entry = LogEntry(
            timestamp=now,
            message="Test message",
            level="info",
            source="app.log",
        )

        assert entry.timestamp == now
        assert entry.message == "Test message"
        assert entry.level == "info"
        assert entry.source == "app.log"
        assert entry.metadata == {}

    def test_create_minimal_entry(self) -> None:
        """Test creating with minimal fields."""
        entry = LogEntry(
            timestamp=None,
            message="Just a message",
        )

        assert entry.timestamp is None
        assert entry.message == "Just a message"
        assert entry.level is None
        assert entry.source is None

    def test_entry_with_metadata(self) -> None:
        """Test entry with metadata."""
        entry = LogEntry(
            timestamp=None,
            message="Test",
            metadata={"line": 42, "container": "app-1"},
        )

        assert entry.metadata["line"] == 42
        assert entry.metadata["container"] == "app-1"


class TestLogResult:
    """Tests for LogResult."""

    def test_successful_result(self) -> None:
        """Test successful result."""
        entries = [
            LogEntry(timestamp=None, message="Entry 1"),
            LogEntry(timestamp=None, message="Entry 2"),
        ]

        result = LogResult(
            entries=entries,
            source="test.log",
        )

        assert result.success
        assert len(result.entries) == 2
        assert result.source == "test.log"
        assert not result.truncated
        assert result.next_token is None
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test failed result."""
        result = LogResult(
            entries=[],
            source="test.log",
            error="File not found",
        )

        assert not result.success
        assert len(result.entries) == 0
        assert result.error == "File not found"

    def test_truncated_result(self) -> None:
        """Test truncated result with pagination."""
        result = LogResult(
            entries=[LogEntry(timestamp=None, message="Entry 1")],
            source="test.log",
            truncated=True,
            next_token="line:100",
        )

        assert result.success
        assert result.truncated
        assert result.next_token == "line:100"

    def test_empty_result(self) -> None:
        """Test empty but successful result."""
        result = LogResult(
            entries=[],
            source="test.log",
        )

        assert result.success
        assert len(result.entries) == 0
