"""Local file log provider.

Reads logs from local files with automatic rotation detection.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from dataing.agents.tools.log_providers.base import (
    BaseLogProvider,
    LogEntry,
    LogProviderConfig,
    LogResult,
    LogSource,
)
from dataing.core.parsing.log_parser import LogLevel, LogParser

logger = logging.getLogger(__name__)


class LocalFileLogProvider(BaseLogProvider):
    """Log provider for local files.

    Reads logs from local filesystem with support for:
    - Single files and directories
    - Log rotation (*.log, *.log.1, etc.)
    - Multiple log formats
    """

    def __init__(
        self,
        config: LogProviderConfig,
        log_directories: list[Path] | None = None,
        log_patterns: list[str] | None = None,
    ) -> None:
        """Initialize the local file log provider.

        Args:
            config: Provider configuration.
            log_directories: Directories to scan for logs.
            log_patterns: Glob patterns for log files.
        """
        super().__init__(config)
        self._log_dirs = log_directories or []
        self._log_patterns = log_patterns or ["*.log", "*.log.*"]
        self._parser = LogParser()

    @property
    def source_type(self) -> LogSource:
        """Get the source type."""
        return LogSource.LOCAL_FILE

    def add_log_directory(self, directory: Path) -> None:
        """Add a directory to scan for logs.

        Args:
            directory: Directory path.
        """
        if directory not in self._log_dirs:
            self._log_dirs.append(directory)

    async def list_sources(self) -> list[str]:
        """List available log files.

        Returns:
            List of log file paths.
        """
        sources: list[str] = []

        for log_dir in self._log_dirs:
            if not log_dir.exists():
                continue

            for pattern in self._log_patterns:
                for path in log_dir.glob(pattern):
                    if path.is_file():
                        sources.append(str(path))

        # Sort by modification time (newest first)
        sources.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)

        return sources

    async def get_logs(
        self,
        source_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_entries: int = 100,
        filter_pattern: str | None = None,
        next_token: str | None = None,
    ) -> LogResult:
        """Get logs from a file.

        Args:
            source_id: Path to the log file.
            start_time: Start of time range.
            end_time: End of time range.
            max_entries: Maximum entries to return.
            filter_pattern: Pattern to filter logs.
            next_token: Line number to start from.

        Returns:
            LogResult with entries.
        """
        path = Path(source_id)

        if not path.exists():
            return LogResult(
                entries=[],
                source=source_id,
                error=f"Log file not found: {source_id}",
            )

        if not path.is_file():
            return LogResult(
                entries=[],
                source=source_id,
                error=f"Not a file: {source_id}",
            )

        try:
            # Determine start line from token
            start_line = int(next_token) if next_token else 1

            # Parse the log file
            parsed_entries = self._parser.parse_file(
                path,
                max_entries=max_entries * 2,  # Get extra for filtering
                start_line=start_line,
            )

            # Convert to LogEntry and filter
            entries: list[LogEntry] = []
            last_processed_line = start_line

            for entry in parsed_entries:
                # Track every line we process (for truncation logic)
                last_processed_line = entry.line_number

                # Apply time filters
                if start_time and entry.timestamp and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp and entry.timestamp > end_time:
                    continue

                # Apply pattern filter (check both message and raw line)
                if filter_pattern:
                    pattern_lower = filter_pattern.lower()
                    if (
                        pattern_lower not in entry.message.lower()
                        and pattern_lower not in entry.raw.lower()
                    ):
                        continue

                entries.append(
                    LogEntry(
                        timestamp=entry.timestamp,
                        message=entry.message,
                        level=entry.level.value if entry.level != LogLevel.UNKNOWN else None,
                        source=source_id,
                        metadata={
                            "line_number": entry.line_number,
                            "raw": entry.raw,
                        },
                    )
                )

                if len(entries) >= max_entries:
                    break

            # Determine if there are more entries
            total_lines = self._parser.get_summary(path).get("total_lines", 0)
            hit_max_entries = len(entries) >= max_entries
            reached_eof = last_processed_line >= total_lines
            truncated = hit_max_entries or not reached_eof

            return LogResult(
                entries=entries,
                source=source_id,
                truncated=truncated,
                next_token=str(last_processed_line + 1) if truncated else None,
            )

        except Exception as e:
            logger.exception(f"Error reading log file: {source_id}")
            return LogResult(
                entries=[],
                source=source_id,
                error=f"Error reading log file: {e}",
            )

    async def get_recent_errors(
        self,
        source_id: str,
        max_entries: int = 50,
        context_lines: int = 2,
    ) -> LogResult:
        """Get recent errors from a log file with context.

        Args:
            source_id: Path to the log file.
            max_entries: Maximum errors to return.
            context_lines: Lines of context around each error.

        Returns:
            LogResult with error entries and context.
        """
        path = Path(source_id)

        if not path.exists():
            return LogResult(
                entries=[],
                source=source_id,
                error=f"Log file not found: {source_id}",
            )

        try:
            errors = self._parser.find_errors(
                path,
                max_results=max_entries,
                context_lines=context_lines,
            )

            entries: list[LogEntry] = []
            for error_data in errors:
                entry = error_data["entry"]
                entries.append(
                    LogEntry(
                        timestamp=entry.timestamp,
                        message=entry.message,
                        level=entry.level.value,
                        source=source_id,
                        metadata={
                            "line_number": entry.line_number,
                            "context_before": error_data["context_before"],
                            "context_after": error_data["context_after"],
                        },
                    )
                )

            return LogResult(
                entries=entries,
                source=source_id,
            )

        except Exception as e:
            logger.exception(f"Error finding errors in: {source_id}")
            return LogResult(
                entries=[],
                source=source_id,
                error=f"Error finding errors: {e}",
            )


def create_local_provider(
    name: str = "Local Files",
    directories: list[str] | None = None,
    patterns: list[str] | None = None,
) -> LocalFileLogProvider:
    """Create a local file log provider.

    Args:
        name: Provider name.
        directories: Directories to scan.
        patterns: Glob patterns for log files.

    Returns:
        Configured LocalFileLogProvider.
    """
    config = LogProviderConfig(
        source=LogSource.LOCAL_FILE,
        name=name,
        settings={
            "directories": directories or [],
            "patterns": patterns or ["*.log", "*.log.*"],
        },
    )

    return LocalFileLogProvider(
        config=config,
        log_directories=[Path(d) for d in (directories or [])],
        log_patterns=patterns,
    )
