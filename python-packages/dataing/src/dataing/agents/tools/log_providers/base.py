"""Base log provider protocol and types.

Defines the interface for log providers and common types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class LogSource(str, Enum):
    """Types of log sources."""

    LOCAL_FILE = "local_file"
    DOCKER = "docker"
    CLOUDWATCH = "cloudwatch"
    KUBERNETES = "kubernetes"


@dataclass
class LogProviderConfig:
    """Configuration for a log provider.

    Attributes:
        source: The type of log source.
        name: Human-readable name for this provider.
        enabled: Whether the provider is enabled.
        settings: Provider-specific settings.
    """

    source: LogSource
    name: str
    enabled: bool = True
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class LogEntry:
    """A single log entry.

    Attributes:
        timestamp: When the log was produced.
        message: The log message content.
        level: Log level (INFO, ERROR, etc.) if detected.
        source: Where the log came from.
        metadata: Additional metadata.
    """

    timestamp: datetime | None
    message: str
    level: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LogResult:
    """Result of fetching logs.

    Attributes:
        entries: Log entries retrieved.
        source: The source of these logs.
        truncated: Whether results were truncated.
        next_token: Token for pagination if available.
        error: Error message if fetch failed.
    """

    entries: list[LogEntry]
    source: str
    truncated: bool = False
    next_token: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if the log fetch was successful."""
        return self.error is None


@runtime_checkable
class LogProvider(Protocol):
    """Protocol for log providers.

    All log providers must implement this interface.
    """

    @property
    def source_type(self) -> LogSource:
        """Get the type of log source."""
        ...

    @property
    def name(self) -> str:
        """Get the provider name."""
        ...

    async def list_sources(self) -> list[str]:
        """List available log sources.

        Returns:
            List of source identifiers (file paths, container names, etc.).
        """
        ...

    async def get_logs(
        self,
        source_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_entries: int = 100,
        filter_pattern: str | None = None,
        next_token: str | None = None,
    ) -> LogResult:
        """Get logs from a source.

        Args:
            source_id: The source identifier.
            start_time: Start of time range.
            end_time: End of time range.
            max_entries: Maximum entries to return.
            filter_pattern: Pattern to filter logs.
            next_token: Token for pagination.

        Returns:
            LogResult with entries or error.
        """
        ...

    async def search_logs(
        self,
        pattern: str,
        source_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_entries: int = 50,
    ) -> LogResult:
        """Search logs for a pattern.

        Args:
            pattern: Search pattern.
            source_id: Optional source to search in.
            start_time: Start of time range.
            end_time: End of time range.
            max_entries: Maximum entries to return.

        Returns:
            LogResult with matching entries.
        """
        ...


class BaseLogProvider(ABC):
    """Base class for log providers.

    Provides common functionality for log providers.
    """

    def __init__(self, config: LogProviderConfig) -> None:
        """Initialize the provider.

        Args:
            config: Provider configuration.
        """
        self._config = config

    @property
    @abstractmethod
    def source_type(self) -> LogSource:
        """Get the type of log source."""
        ...

    @property
    def name(self) -> str:
        """Get the provider name."""
        return self._config.name

    @property
    def enabled(self) -> bool:
        """Check if the provider is enabled."""
        return self._config.enabled

    @abstractmethod
    async def list_sources(self) -> list[str]:
        """List available log sources."""
        ...

    @abstractmethod
    async def get_logs(
        self,
        source_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_entries: int = 100,
        filter_pattern: str | None = None,
        next_token: str | None = None,
    ) -> LogResult:
        """Get logs from a source."""
        ...

    async def search_logs(
        self,
        pattern: str,
        source_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_entries: int = 50,
    ) -> LogResult:
        """Search logs for a pattern.

        Default implementation fetches logs and filters.
        Subclasses can override for more efficient search.
        """
        # If source specified, search in it
        if source_id:
            result = await self.get_logs(
                source_id,
                start_time=start_time,
                end_time=end_time,
                max_entries=max_entries * 10,  # Fetch more to filter
                filter_pattern=pattern,
            )
            # Filter client-side if provider doesn't support filter
            if pattern and result.success:
                pattern_lower = pattern.lower()
                result.entries = [
                    e for e in result.entries if self._matches_pattern(e, pattern_lower)
                ][:max_entries]
            return result

        # Search across all sources
        sources = await self.list_sources()
        all_entries: list[LogEntry] = []

        for src in sources:
            if len(all_entries) >= max_entries:
                break

            result = await self.get_logs(
                src,
                start_time=start_time,
                end_time=end_time,
                max_entries=max_entries - len(all_entries),
                filter_pattern=pattern,
            )

            if result.success:
                # Filter client-side
                pattern_lower = pattern.lower()
                matching = [e for e in result.entries if self._matches_pattern(e, pattern_lower)]
                all_entries.extend(matching)

        return LogResult(
            entries=all_entries[:max_entries],
            source="multiple",
            truncated=len(all_entries) > max_entries,
        )

    def _matches_pattern(self, entry: LogEntry, pattern_lower: str) -> bool:
        """Check if entry matches a search pattern.

        Checks message, level, and raw line in metadata.

        Args:
            entry: Log entry to check.
            pattern_lower: Lowercase search pattern.

        Returns:
            True if pattern found in entry.
        """
        # Check message
        if pattern_lower in entry.message.lower():
            return True

        # Check level
        if entry.level and pattern_lower in entry.level.lower():
            return True

        # Check raw line in metadata
        raw = entry.metadata.get("raw", "")
        if raw and pattern_lower in raw.lower():
            return True

        return False
