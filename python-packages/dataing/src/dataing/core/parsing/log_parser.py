"""Log file parser with pattern detection.

Provides utilities for parsing log files, detecting common formats,
and extracting structured log entries.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LogLevel(str, Enum):
    """Standard log levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class LogEntry:
    """A parsed log entry.

    Attributes:
        timestamp: Parsed timestamp if detected.
        level: Log level if detected.
        message: The log message content.
        source: Source/logger name if detected.
        line_number: Original line number in file.
        raw: The raw log line.
        metadata: Additional parsed fields.
    """

    timestamp: datetime | None
    level: LogLevel
    message: str
    source: str | None
    line_number: int
    raw: str
    metadata: dict[str, Any] = field(default_factory=dict)


class LogParser:
    """Parser for log files with format detection.

    Supports common log formats including:
    - Standard Python logging
    - Docker container logs
    - Nginx/Apache access logs
    - JSON-formatted logs (structured logging)
    """

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB for logs

    # Common timestamp patterns
    TIMESTAMP_PATTERNS = [
        # ISO 8601: 2024-01-15T10:30:45.123Z
        (
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)",
            "%Y-%m-%dT%H:%M:%S",
        ),
        # Standard datetime: 2024-01-15 10:30:45
        (r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", "%Y-%m-%d %H:%M:%S"),
        # Compact: 20240115T103045
        (r"(\d{8}T\d{6})", "%Y%m%dT%H%M%S"),
        # Unix timestamp with brackets: [1705315845]
        (r"\[(\d{10})\]", "epoch"),
    ]

    # Log level patterns (case-insensitive)
    LEVEL_PATTERNS = [
        (r"\b(DEBUG)\b", LogLevel.DEBUG),
        (r"\b(INFO)\b", LogLevel.INFO),
        (r"\b(WARN(?:ING)?)\b", LogLevel.WARNING),
        (r"\b(ERROR)\b", LogLevel.ERROR),
        (r"\b(CRIT(?:ICAL)?|FATAL)\b", LogLevel.CRITICAL),
    ]

    def __init__(self, max_file_size: int = MAX_FILE_SIZE) -> None:
        """Initialize the log parser.

        Args:
            max_file_size: Maximum file size in bytes.
        """
        self.max_file_size = max_file_size

    def parse_file(
        self,
        path: Path | str,
        max_entries: int | None = None,
        level_filter: LogLevel | None = None,
        start_line: int = 1,
    ) -> list[LogEntry]:
        """Parse a log file into structured entries.

        Args:
            path: Path to the log file.
            max_entries: Maximum entries to return.
            level_filter: Only return entries of this level or higher.
            start_line: 1-indexed line to start from.

        Returns:
            List of LogEntry objects.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file exceeds size limit.
        """
        path = Path(path)

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(
                f"Log file exceeds size limit: {file_size:,} > {self.max_file_size:,} bytes"
            )

        content = path.read_text(encoding="utf-8", errors="replace")
        return self.parse_lines(
            content.splitlines(),
            max_entries=max_entries,
            level_filter=level_filter,
            start_line=start_line,
        )

    def parse_lines(
        self,
        lines: list[str],
        max_entries: int | None = None,
        level_filter: LogLevel | None = None,
        start_line: int = 1,
    ) -> list[LogEntry]:
        """Parse log lines into structured entries.

        Args:
            lines: List of log lines.
            max_entries: Maximum entries to return.
            level_filter: Only return entries of this level or higher.
            start_line: Starting line number for numbering.

        Returns:
            List of LogEntry objects.
        """
        entries = []
        level_priority = self._get_level_priority(level_filter) if level_filter else 0

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            entry = self._parse_line(line, line_number=start_line + i)

            # Apply level filter
            if level_filter:
                entry_priority = self._get_level_priority(entry.level)
                if entry_priority < level_priority:
                    continue

            entries.append(entry)

            if max_entries and len(entries) >= max_entries:
                break

        return entries

    def find_errors(
        self,
        path: Path | str,
        max_results: int = 50,
        context_lines: int = 2,
    ) -> list[dict[str, Any]]:
        """Find error entries with surrounding context.

        Args:
            path: Path to the log file.
            max_results: Maximum errors to return.
            context_lines: Number of lines before/after each error.

        Returns:
            List of error dicts with context.
        """
        path = Path(path)
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        errors = []
        for i, line in enumerate(lines):
            entry = self._parse_line(line, line_number=i + 1)
            if entry.level in (LogLevel.ERROR, LogLevel.CRITICAL):
                # Get context
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)

                errors.append(
                    {
                        "entry": entry,
                        "context_before": lines[start:i],
                        "context_after": lines[i + 1 : end],
                    }
                )

                if len(errors) >= max_results:
                    break

        return errors

    def get_summary(self, path: Path | str) -> dict[str, Any]:
        """Get a summary of a log file.

        Args:
            path: Path to the log file.

        Returns:
            Summary dict with counts and samples.
        """
        path = Path(path)
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        level_counts: dict[str, int] = {}
        first_timestamp: datetime | None = None
        last_timestamp: datetime | None = None
        sample_errors: list[str] = []

        for i, line in enumerate(lines):
            entry = self._parse_line(line, line_number=i + 1)

            # Count levels
            level_counts[entry.level.value] = level_counts.get(entry.level.value, 0) + 1

            # Track timestamps
            if entry.timestamp:
                if first_timestamp is None:
                    first_timestamp = entry.timestamp
                last_timestamp = entry.timestamp

            # Sample errors
            if entry.level in (LogLevel.ERROR, LogLevel.CRITICAL) and len(sample_errors) < 5:
                sample_errors.append(entry.message[:200])

        return {
            "total_lines": len(lines),
            "level_counts": level_counts,
            "first_timestamp": first_timestamp.isoformat() if first_timestamp else None,
            "last_timestamp": last_timestamp.isoformat() if last_timestamp else None,
            "sample_errors": sample_errors,
        }

    def _parse_line(self, line: str, line_number: int) -> LogEntry:
        """Parse a single log line.

        Args:
            line: The log line.
            line_number: Line number in file.

        Returns:
            LogEntry object.
        """
        # Try JSON first
        if line.strip().startswith("{"):
            entry = self._parse_json_log(line, line_number)
            if entry:
                return entry

        # Parse standard format
        timestamp = self._extract_timestamp(line)
        level = self._extract_level(line)
        source = self._extract_source(line)
        message = self._extract_message(line, timestamp, level, source)

        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=message,
            source=source,
            line_number=line_number,
            raw=line,
        )

    def _parse_json_log(self, line: str, line_number: int) -> LogEntry | None:
        """Try to parse a JSON-formatted log line.

        Args:
            line: The log line.
            line_number: Line number.

        Returns:
            LogEntry if valid JSON log, None otherwise.
        """
        import json

        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None

            # Extract common fields
            timestamp = None
            for ts_field in ["timestamp", "time", "@timestamp", "ts"]:
                if ts_field in data:
                    timestamp = self._parse_timestamp_string(str(data[ts_field]))
                    break

            level = LogLevel.UNKNOWN
            for level_field in ["level", "severity", "lvl"]:
                if level_field in data:
                    level = self._string_to_level(str(data[level_field]))
                    break

            message = data.get("message", data.get("msg", str(data)))
            source = data.get("logger", data.get("source", data.get("name")))

            return LogEntry(
                timestamp=timestamp,
                level=level,
                message=str(message),
                source=str(source) if source else None,
                line_number=line_number,
                raw=line,
                metadata=data,
            )
        except (json.JSONDecodeError, ValueError):
            return None

    def _extract_timestamp(self, line: str) -> datetime | None:
        """Extract timestamp from a log line.

        Args:
            line: The log line.

        Returns:
            Parsed datetime or None.
        """
        for pattern, fmt in self.TIMESTAMP_PATTERNS:
            match = re.search(pattern, line)
            if match:
                ts_str = match.group(1)
                return self._parse_timestamp_string(ts_str, fmt)
        return None

    def _parse_timestamp_string(self, ts_str: str, fmt: str | None = None) -> datetime | None:
        """Parse a timestamp string.

        Args:
            ts_str: Timestamp string.
            fmt: Expected format.

        Returns:
            Parsed datetime or None.
        """
        if fmt == "epoch":
            try:
                return datetime.fromtimestamp(int(ts_str))
            except (ValueError, OSError):
                return None

        # Try ISO format first
        try:
            # Handle timezone suffix
            ts_str = ts_str.replace("Z", "+00:00")
            return datetime.fromisoformat(ts_str)
        except ValueError:
            pass

        # Try standard formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%dT%H%M%S"]:
            try:
                return datetime.strptime(ts_str[:19], fmt)
            except ValueError:
                continue

        return None

    def _extract_level(self, line: str) -> LogLevel:
        """Extract log level from a line.

        Args:
            line: The log line.

        Returns:
            LogLevel enum value.
        """
        upper_line = line.upper()
        for pattern, level in self.LEVEL_PATTERNS:
            if re.search(pattern, upper_line):
                return level
        return LogLevel.UNKNOWN

    def _string_to_level(self, level_str: str) -> LogLevel:
        """Convert a string to LogLevel.

        Args:
            level_str: Level string.

        Returns:
            LogLevel enum value.
        """
        level_str = level_str.upper()
        if "DEBUG" in level_str:
            return LogLevel.DEBUG
        elif "INFO" in level_str:
            return LogLevel.INFO
        elif "WARN" in level_str:
            return LogLevel.WARNING
        elif "ERROR" in level_str:
            return LogLevel.ERROR
        elif "CRIT" in level_str or "FATAL" in level_str:
            return LogLevel.CRITICAL
        return LogLevel.UNKNOWN

    def _extract_source(self, line: str) -> str | None:
        """Extract source/logger name from a line.

        Args:
            line: The log line.

        Returns:
            Source name or None.
        """
        # Common patterns: [source], <source>, source:
        patterns = [
            r"\[([a-zA-Z0-9_.]+)\]",  # [source]
            r"<([a-zA-Z0-9_.]+)>",  # <source>
            r"^\S+\s+\S+\s+([a-zA-Z0-9_.]+):",  # timestamp level source:
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(1)

        return None

    def _extract_message(
        self,
        line: str,
        timestamp: datetime | None,
        level: LogLevel,
        source: str | None,
    ) -> str:
        """Extract the message portion of a log line.

        Args:
            line: The log line.
            timestamp: Parsed timestamp.
            level: Parsed level.
            source: Parsed source.

        Returns:
            The message content.
        """
        # Simple heuristic: take everything after level indicator
        for pattern, _ in self.LEVEL_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                # Return everything after the level
                return line[match.end() :].strip(" -:")

        # Fallback: return the whole line
        return line.strip()

    def _get_level_priority(self, level: LogLevel) -> int:
        """Get priority number for a log level.

        Args:
            level: Log level.

        Returns:
            Priority (higher = more severe).
        """
        priorities = {
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50,
            LogLevel.UNKNOWN: 0,
        }
        return priorities.get(level, 0)
