"""Text file parser with smart chunking support.

Provides utilities for reading text files with line-range chunking
and safe handling of various encodings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """A chunk of text from a file.

    Attributes:
        content: The text content.
        start_line: The 1-indexed start line number.
        end_line: The 1-indexed end line number (inclusive).
        total_lines: Total number of lines in the file.
        truncated: Whether the content was truncated due to limits.
    """

    content: str
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool = False


class TextParser:
    """Parser for plain text files with chunking support.

    Provides safe reading of text files with encoding detection,
    line-range selection, and size limits.
    """

    DEFAULT_ENCODING = "utf-8"
    FALLBACK_ENCODINGS = ["latin-1", "cp1252", "iso-8859-1"]
    MAX_LINE_LENGTH = 10000
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        max_line_length: int = MAX_LINE_LENGTH,
        max_file_size: int = MAX_FILE_SIZE,
    ) -> None:
        """Initialize the text parser.

        Args:
            max_line_length: Maximum characters per line before truncation.
            max_file_size: Maximum file size in bytes.
        """
        self.max_line_length = max_line_length
        self.max_file_size = max_file_size

    def read_file(
        self,
        path: Path | str,
        start_line: int = 1,
        end_line: int | None = None,
        max_lines: int | None = None,
    ) -> TextChunk:
        """Read a text file with optional line-range selection.

        Args:
            path: Path to the file.
            start_line: 1-indexed start line (default: 1).
            end_line: 1-indexed end line (inclusive, default: all).
            max_lines: Maximum lines to return (overrides end_line).

        Returns:
            TextChunk with content and metadata.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file exceeds size limit.
            UnicodeDecodeError: If file cannot be decoded.
        """
        path = Path(path)

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(
                f"File exceeds size limit: {file_size:,} > {self.max_file_size:,} bytes"
            )

        # Read with encoding detection
        content = self._read_with_fallback(path)
        lines = content.splitlines()
        total_lines = len(lines)

        # Validate and adjust line range
        start_line = max(1, start_line)
        if end_line is None:
            end_line = total_lines
        else:
            end_line = min(end_line, total_lines)

        if max_lines is not None:
            end_line = min(start_line + max_lines - 1, end_line)

        # Extract requested lines (convert to 0-indexed)
        selected_lines = lines[start_line - 1 : end_line]

        # Truncate long lines
        truncated = False
        processed_lines = []
        for line in selected_lines:
            if len(line) > self.max_line_length:
                processed_lines.append(line[: self.max_line_length] + "...")
                truncated = True
            else:
                processed_lines.append(line)

        return TextChunk(
            content="\n".join(processed_lines),
            start_line=start_line,
            end_line=end_line,
            total_lines=total_lines,
            truncated=truncated,
        )

    def count_lines(self, path: Path | str) -> int:
        """Count lines in a file without loading it fully.

        Args:
            path: Path to the file.

        Returns:
            Number of lines in the file.
        """
        path = Path(path)
        content = self._read_with_fallback(path)
        return len(content.splitlines())

    def search_lines(
        self,
        path: Path | str,
        pattern: str,
        max_results: int = 100,
        case_sensitive: bool = False,
    ) -> list[tuple[int, str]]:
        """Search for lines containing a pattern.

        Args:
            path: Path to the file.
            pattern: Search pattern (plain text, not regex).
            max_results: Maximum number of results to return.
            case_sensitive: Whether to do case-sensitive matching.

        Returns:
            List of (line_number, line_content) tuples.
        """
        path = Path(path)
        content = self._read_with_fallback(path)
        lines = content.splitlines()

        if not case_sensitive:
            pattern = pattern.lower()

        results: list[tuple[int, str]] = []
        for i, line in enumerate(lines, 1):
            check_line = line if case_sensitive else line.lower()
            if pattern in check_line:
                # Truncate if needed
                if len(line) > self.max_line_length:
                    line = line[: self.max_line_length] + "..."
                results.append((i, line))
                if len(results) >= max_results:
                    break

        return results

    def _read_with_fallback(self, path: Path) -> str:
        """Read file with encoding fallback.

        Args:
            path: Path to the file.

        Returns:
            File content as string.

        Raises:
            UnicodeDecodeError: If all encodings fail.
        """
        # Try default encoding first
        try:
            return path.read_text(encoding=self.DEFAULT_ENCODING)
        except UnicodeDecodeError:
            pass

        # Try fallback encodings
        for encoding in self.FALLBACK_ENCODINGS:
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

        # Last resort: read with errors='replace'
        logger.warning(f"Could not decode {path} cleanly, using replacement characters")
        return path.read_text(encoding=self.DEFAULT_ENCODING, errors="replace")
