"""Tests for local file log provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataing.agents.tools.log_providers.base import LogProviderConfig, LogSource
from dataing.agents.tools.log_providers.local import (
    LocalFileLogProvider,
    create_local_provider,
)


@pytest.fixture
def sample_log_dir(tmp_path: Path) -> Path:
    """Create sample log files."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Create app.log
    (log_dir / "app.log").write_text(
        """2024-01-15 10:30:45 INFO Starting application
2024-01-15 10:30:46 DEBUG Loading configuration
2024-01-15 10:30:47 WARNING Config file not found, using defaults
2024-01-15 10:30:48 ERROR Failed to connect to database
2024-01-15 10:30:49 INFO Retrying connection
2024-01-15 10:30:50 INFO Application started successfully
"""
    )

    # Create worker.log
    (log_dir / "worker.log").write_text(
        """2024-01-15 11:00:00 INFO Worker started
2024-01-15 11:00:01 INFO Processing job 123
2024-01-15 11:00:02 ERROR Job 123 failed: timeout
2024-01-15 11:00:03 INFO Processing job 124
2024-01-15 11:00:04 INFO Job 124 completed
"""
    )

    return log_dir


@pytest.fixture
def provider(sample_log_dir: Path) -> LocalFileLogProvider:
    """Create a local file log provider."""
    config = LogProviderConfig(
        source=LogSource.LOCAL_FILE,
        name="Test Logs",
    )
    return LocalFileLogProvider(
        config=config,
        log_directories=[sample_log_dir],
    )


class TestLocalFileLogProvider:
    """Tests for LocalFileLogProvider."""

    def test_source_type(self, provider: LocalFileLogProvider) -> None:
        """Test source type property."""
        assert provider.source_type == LogSource.LOCAL_FILE

    def test_name(self, provider: LocalFileLogProvider) -> None:
        """Test name property."""
        assert provider.name == "Test Logs"

    @pytest.mark.asyncio
    async def test_list_sources(self, provider: LocalFileLogProvider, sample_log_dir: Path) -> None:
        """Test listing log sources."""
        sources = await provider.list_sources()

        assert len(sources) == 2
        assert any("app.log" in s for s in sources)
        assert any("worker.log" in s for s in sources)

    @pytest.mark.asyncio
    async def test_get_logs(self, provider: LocalFileLogProvider, sample_log_dir: Path) -> None:
        """Test getting logs from a file."""
        log_path = str(sample_log_dir / "app.log")
        result = await provider.get_logs(log_path)

        assert result.success
        assert len(result.entries) == 6
        assert result.source == log_path

    @pytest.mark.asyncio
    async def test_get_logs_max_entries(
        self, provider: LocalFileLogProvider, sample_log_dir: Path
    ) -> None:
        """Test max entries limit."""
        log_path = str(sample_log_dir / "app.log")
        result = await provider.get_logs(log_path, max_entries=3)

        assert result.success
        assert len(result.entries) == 3
        assert result.truncated

    @pytest.mark.asyncio
    async def test_get_logs_with_filter(
        self, provider: LocalFileLogProvider, sample_log_dir: Path
    ) -> None:
        """Test filtering logs by pattern."""
        log_path = str(sample_log_dir / "app.log")
        result = await provider.get_logs(log_path, filter_pattern="ERROR")

        assert result.success
        assert len(result.entries) == 1
        # The message is the content after the level; check raw line or level
        assert result.entries[0].level == "error"
        assert "ERROR" in result.entries[0].metadata["raw"]

    @pytest.mark.asyncio
    async def test_get_logs_nonexistent(self, provider: LocalFileLogProvider) -> None:
        """Test handling of nonexistent file."""
        result = await provider.get_logs("/nonexistent/file.log")

        assert not result.success
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_recent_errors(
        self, provider: LocalFileLogProvider, sample_log_dir: Path
    ) -> None:
        """Test getting recent errors."""
        log_path = str(sample_log_dir / "app.log")
        result = await provider.get_recent_errors(log_path)

        assert result.success
        assert len(result.entries) == 1
        assert result.entries[0].level == "error"

    @pytest.mark.asyncio
    async def test_search_logs(self, provider: LocalFileLogProvider, sample_log_dir: Path) -> None:
        """Test searching logs."""
        log_path = str(sample_log_dir / "app.log")
        result = await provider.search_logs("database", source_id=log_path)

        assert result.success
        assert len(result.entries) == 1
        assert "database" in result.entries[0].message.lower()

    @pytest.mark.asyncio
    async def test_search_all_sources(self, provider: LocalFileLogProvider) -> None:
        """Test searching across all sources."""
        result = await provider.search_logs("ERROR")

        assert result.success
        # Should find errors in both log files
        assert len(result.entries) >= 2

    def test_add_log_directory(self, provider: LocalFileLogProvider, tmp_path: Path) -> None:
        """Test adding a log directory."""
        new_dir = tmp_path / "new_logs"
        new_dir.mkdir()

        provider.add_log_directory(new_dir)

        assert new_dir in provider._log_dirs


class TestCreateLocalProvider:
    """Tests for create_local_provider helper."""

    def test_create_default(self) -> None:
        """Test creating with defaults."""
        provider = create_local_provider()

        assert provider.name == "Local Files"
        assert provider.source_type == LogSource.LOCAL_FILE

    def test_create_with_directories(self, tmp_path: Path) -> None:
        """Test creating with directories."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        provider = create_local_provider(
            name="Custom Logs",
            directories=[str(log_dir)],
        )

        assert provider.name == "Custom Logs"
        assert Path(log_dir) in provider._log_dirs

    def test_create_with_patterns(self) -> None:
        """Test creating with custom patterns."""
        provider = create_local_provider(
            patterns=["*.txt", "*.out"],
        )

        assert "*.txt" in provider._log_patterns
        assert "*.out" in provider._log_patterns
