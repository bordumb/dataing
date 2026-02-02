"""Local file reader tool with safety features.

Provides safe read access to local files with:
- Directory allowlist enforcement
- Path traversal prevention
- Sensitive file blocking
- Size limits
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.tools import Tool

from dataing.agents.tools.registry import ToolCategory, get_default_registry
from dataing.core.parsing import (
    DataParser,
    JsonParser,
    LogParser,
    TextParser,
    YamlParser,
)

logger = logging.getLogger(__name__)

# Maximum file size to read (100KB)
MAX_FILE_SIZE = 100 * 1024

# Allowed directories (relative to repo root)
ALLOWED_DIRS = [
    "python-packages/",
    "frontend/",
    "demo/",
    "docs/",
]

# Allowed file patterns in root directory
ALLOWED_ROOT_PATTERNS = [
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "*.md",
    "justfile",
    "pyproject.toml",
    "package.json",
    "Makefile",
    ".gitignore",
]

# Blocked patterns (always rejected)
BLOCKED_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.crt",
    "*secret*",
    "*credential*",
    "*password*",
    "*token*",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "*.sqlite",
    "*.db",
]


@dataclass
class FileReadResult:
    """Result of reading a file.

    Attributes:
        success: Whether the read succeeded.
        content: File content if successful.
        error: Error message if failed.
        truncated: Whether content was truncated due to size.
        file_type: Detected file type.
        line_count: Number of lines in file.
    """

    success: bool
    content: str | None
    error: str | None = None
    truncated: bool = False
    file_type: str | None = None
    line_count: int | None = None


class LocalFileReader:
    """Safe local file reader with security features.

    Enforces directory allowlists, blocks sensitive files,
    and prevents path traversal attacks.
    """

    def __init__(
        self,
        repo_root: Path,
        allowed_dirs: list[str] | None = None,
        allowed_root_patterns: list[str] | None = None,
        blocked_patterns: list[str] | None = None,
        max_file_size: int = MAX_FILE_SIZE,
    ) -> None:
        """Initialize the file reader.

        Args:
            repo_root: Repository root directory.
            allowed_dirs: Allowed subdirectories (default: ALLOWED_DIRS).
            allowed_root_patterns: Allowed patterns in root (default: ALLOWED_ROOT_PATTERNS).
            blocked_patterns: Blocked file patterns (default: BLOCKED_PATTERNS).
            max_file_size: Maximum file size in bytes.
        """
        self.repo_root = repo_root.resolve()
        self.allowed_dirs = allowed_dirs or ALLOWED_DIRS
        self.allowed_root_patterns = allowed_root_patterns or ALLOWED_ROOT_PATTERNS
        self.blocked_patterns = blocked_patterns or BLOCKED_PATTERNS
        self.max_file_size = max_file_size

        # Initialize parsers
        self._text_parser = TextParser(max_file_size=max_file_size)
        self._yaml_parser = YamlParser(max_file_size=max_file_size)
        self._json_parser = JsonParser(max_file_size=max_file_size)
        self._log_parser = LogParser(max_file_size=max_file_size)
        self._data_parser = DataParser(max_file_size=max_file_size)

    def is_path_allowed(self, file_path: str) -> tuple[bool, str | None]:
        """Check if a path is allowed to be read.

        Args:
            file_path: Relative or absolute path.

        Returns:
            Tuple of (is_allowed, error_message).
        """
        try:
            resolved = self._resolve_path(file_path)
        except ValueError as e:
            return False, str(e)

        # Check if blocked by pattern
        filename = resolved.name
        for pattern in self.blocked_patterns:
            if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                alternative = self._suggest_alternative(resolved)
                msg = f"Cannot read '{filename}' - blocked for security"
                if alternative:
                    msg += f". Try: {alternative}"
                return False, msg

        # Check if within allowed directory
        rel_path = self._get_relative_path(resolved)
        if rel_path is None:
            return False, f"Path '{file_path}' is outside the repository"

        # Check if in allowed subdirectory
        for allowed_dir in self.allowed_dirs:
            # Handle both "python-packages" and "python-packages/" matching
            normalized_allowed = allowed_dir.rstrip("/")
            if rel_path == normalized_allowed or rel_path.startswith(normalized_allowed + "/"):
                return True, None

        # Check if matches allowed root pattern
        if "/" not in rel_path:
            for pattern in self.allowed_root_patterns:
                if fnmatch.fnmatch(rel_path, pattern):
                    return True, None

        return False, (f"Path '{rel_path}' is not in allowed directories: {self.allowed_dirs}")

    def read_file(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> FileReadResult:
        """Read a file safely.

        Args:
            file_path: Relative or absolute path to the file.
            start_line: Optional 1-indexed start line.
            end_line: Optional 1-indexed end line.

        Returns:
            FileReadResult with content or error.
        """
        # Validate path
        is_allowed, error = self.is_path_allowed(file_path)
        if not is_allowed:
            logger.warning(f"Blocked file access: {file_path} - {error}")
            return FileReadResult(success=False, content=None, error=error)

        try:
            resolved = self._resolve_path(file_path)
        except ValueError as e:
            return FileReadResult(success=False, content=None, error=str(e))

        # Check if file exists
        if not resolved.exists():
            return FileReadResult(success=False, content=None, error=f"File not found: {file_path}")

        if not resolved.is_file():
            return FileReadResult(success=False, content=None, error=f"Not a file: {file_path}")

        # Check if symlink points outside allowed area
        if resolved.is_symlink():
            real_path = resolved.resolve()
            is_target_allowed, _ = self.is_path_allowed(str(real_path))
            if not is_target_allowed:
                return FileReadResult(
                    success=False,
                    content=None,
                    error="Symlink target is outside allowed directories",
                )

        # Check file size
        file_size = resolved.stat().st_size
        if file_size > self.max_file_size:
            return FileReadResult(
                success=False,
                content=None,
                error=(
                    f"File too large ({file_size:,} bytes). "
                    f"Max size: {self.max_file_size:,} bytes. "
                    f"Try requesting specific line ranges."
                ),
            )

        # Detect file type and parse
        file_type = self._detect_file_type(resolved)

        try:
            if start_line or end_line:
                # Line-range read
                chunk = self._text_parser.read_file(
                    resolved,
                    start_line=start_line or 1,
                    end_line=end_line,
                )
                return FileReadResult(
                    success=True,
                    content=chunk.content,
                    truncated=chunk.truncated,
                    file_type=file_type,
                    line_count=chunk.total_lines,
                )
            else:
                # Full file read
                content = resolved.read_text(encoding="utf-8", errors="replace")
                line_count = len(content.splitlines())

                return FileReadResult(
                    success=True,
                    content=content,
                    truncated=False,
                    file_type=file_type,
                    line_count=line_count,
                )

        except Exception as e:
            logger.exception(f"Error reading file: {file_path}")
            return FileReadResult(success=False, content=None, error=f"Error reading file: {e}")

    def search_files(
        self,
        pattern: str,
        directory: str | None = None,
        max_results: int = 100,
    ) -> list[tuple[str, int, str]]:
        """Search for pattern in files.

        Args:
            pattern: Search pattern (plain text).
            directory: Optional subdirectory to search.
            max_results: Maximum results to return.

        Returns:
            List of (file_path, line_number, line_content) tuples.
        """
        results: list[tuple[str, int, str]] = []

        # Determine search root
        if directory:
            is_allowed, error = self.is_path_allowed(directory)
            if not is_allowed:
                logger.warning(f"Blocked directory search: {directory} - {error}")
                return []
            search_root = self._resolve_path(directory)
        else:
            search_root = self.repo_root

        # Search files
        for path in search_root.rglob("*"):
            if len(results) >= max_results:
                break

            if not path.is_file():
                continue

            # Check if allowed
            rel_path = self._get_relative_path(path)
            if rel_path is None:
                continue

            is_allowed, _ = self.is_path_allowed(str(path))
            if not is_allowed:
                continue

            # Skip binary files
            if self._is_binary(path):
                continue

            # Search in file
            try:
                matches = self._text_parser.search_lines(
                    path,
                    pattern,
                    max_results=max_results - len(results),
                )
                for line_num, line_content in matches:
                    results.append((rel_path, line_num, line_content))
            except Exception:
                continue

        return results

    def list_files(
        self,
        directory: str,
        pattern: str = "*",
        max_results: int = 100,
    ) -> list[str]:
        """List files in a directory.

        Args:
            directory: Directory to list.
            pattern: Glob pattern (default: all files).
            max_results: Maximum results to return.

        Returns:
            List of relative file paths.
        """
        is_allowed, error = self.is_path_allowed(directory)
        if not is_allowed:
            logger.warning(f"Blocked directory listing: {directory} - {error}")
            return []

        try:
            resolved = self._resolve_path(directory)
        except ValueError:
            return []

        if not resolved.is_dir():
            return []

        results: list[str] = []
        for path in resolved.glob(pattern):
            if len(results) >= max_results:
                break

            rel_path = self._get_relative_path(path)
            if rel_path is None:
                continue

            # Check if allowed
            is_allowed, _ = self.is_path_allowed(str(path))
            if not is_allowed:
                continue

            results.append(rel_path)

        return results

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve a path safely.

        Args:
            file_path: Relative or absolute path.

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If path escapes repository.
        """
        path = Path(file_path)

        # If absolute, use directly
        if path.is_absolute():
            resolved = path.resolve()
        else:
            resolved = (self.repo_root / path).resolve()

        # Check for path traversal
        try:
            resolved.relative_to(self.repo_root)
        except ValueError:
            raise ValueError(f"Path traversal detected: {file_path}") from None

        return resolved

    def _get_relative_path(self, path: Path) -> str | None:
        """Get path relative to repo root.

        Args:
            path: Absolute path.

        Returns:
            Relative path string, or None if outside repo.
        """
        try:
            return str(path.relative_to(self.repo_root))
        except ValueError:
            return None

    def _detect_file_type(self, path: Path) -> str:
        """Detect file type from extension.

        Args:
            path: File path.

        Returns:
            File type string.
        """
        suffix = path.suffix.lower()
        name = path.name.lower()

        if suffix in (".yml", ".yaml"):
            return "yaml"
        elif suffix == ".json":
            return "json"
        elif suffix in (".py", ".pyi"):
            return "python"
        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            return "typescript"
        elif suffix == ".md":
            return "markdown"
        elif suffix == ".sql":
            return "sql"
        elif suffix in (".csv", ".tsv"):
            return "csv"
        elif suffix == ".parquet":
            return "parquet"
        elif suffix == ".log" or "log" in name:
            return "log"
        elif suffix == ".toml":
            return "toml"
        elif suffix in (".sh", ".bash"):
            return "shell"
        elif suffix == ".dockerfile" or name == "dockerfile":
            return "dockerfile"
        else:
            return "text"

    def _is_binary(self, path: Path) -> bool:
        """Check if a file is binary.

        Args:
            path: File path.

        Returns:
            True if binary file.
        """
        binary_extensions = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            ".svg",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".pyc",
            ".pyo",
            ".class",
            ".o",
            ".a",
            ".parquet",
        }
        return path.suffix.lower() in binary_extensions

    def _suggest_alternative(self, path: Path) -> str | None:
        """Suggest an alternative to a blocked file.

        Args:
            path: Blocked file path.

        Returns:
            Alternative suggestion or None.
        """
        name = path.name.lower()

        if name == ".env":
            # Check for .env.example
            example = path.parent / ".env.example"
            if example.exists():
                return str(example.relative_to(self.repo_root))

        return None


# Create singleton reader (initialized lazily)
_reader: LocalFileReader | None = None


def get_file_reader(repo_root: Path | None = None) -> LocalFileReader:
    """Get the file reader singleton.

    Args:
        repo_root: Repository root (auto-detected if not provided).

    Returns:
        LocalFileReader instance.
    """
    global _reader
    if _reader is None:
        if repo_root is None:
            # Auto-detect from current file location
            repo_root = Path(__file__).resolve().parents[5]
        _reader = LocalFileReader(repo_root)
    return _reader


def reset_file_reader() -> None:
    """Reset the file reader singleton (for testing)."""
    global _reader
    _reader = None


# Tool function for agent
async def read_local_file(
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Read a file from the repository.

    Args:
        file_path: Path relative to repository root.
        start_line: Optional 1-indexed start line for partial reads.
        end_line: Optional 1-indexed end line for partial reads.

    Returns:
        File contents or error message.
    """
    reader = get_file_reader()
    result = reader.read_file(file_path, start_line, end_line)

    if result.success:
        header = f"[{result.file_type}] {file_path}"
        if result.line_count:
            header += f" ({result.line_count} lines)"
        if result.truncated:
            header += " [TRUNCATED]"
        return f"{header}\n\n{result.content}"
    else:
        return f"Error: {result.error}"


async def search_in_files(
    pattern: str,
    directory: str | None = None,
    max_results: int = 50,
) -> str:
    """Search for a pattern in repository files.

    Args:
        pattern: Text pattern to search for.
        directory: Optional subdirectory to search in.
        max_results: Maximum results to return (default: 50).

    Returns:
        Search results or error message.
    """
    reader = get_file_reader()
    results = reader.search_files(pattern, directory, max_results)

    if not results:
        return f"No matches found for '{pattern}'"

    lines = [f"Found {len(results)} matches for '{pattern}':\n"]
    current_file = None

    for file_path, line_num, content in results:
        if file_path != current_file:
            current_file = file_path
            lines.append(f"\n{file_path}:")
        lines.append(f"  {line_num}: {content[:100]}")

    return "\n".join(lines)


async def list_directory(
    directory: str,
    pattern: str = "*",
) -> str:
    """List files in a directory.

    Args:
        directory: Directory path relative to repository root.
        pattern: Optional glob pattern (default: all files).

    Returns:
        File listing or error message.
    """
    reader = get_file_reader()
    files = reader.list_files(directory, pattern)

    if not files:
        return f"No files found in '{directory}' matching '{pattern}'"

    return f"Files in {directory}:\n" + "\n".join(f"  {f}" for f in files)


# Create tool instances
read_file_tool = Tool(read_local_file)
search_files_tool = Tool(search_in_files)
list_dir_tool = Tool(list_directory)


def register_local_file_tools() -> None:
    """Register local file tools with the default registry."""
    registry = get_default_registry()

    registry.register_tool(
        name="read_local_file",
        category=ToolCategory.FILES,
        description="Read a file from the repository with safety checks",
        func=read_local_file,
        priority=10,
    )

    registry.register_tool(
        name="search_in_files",
        category=ToolCategory.FILES,
        description="Search for a pattern across repository files",
        func=search_in_files,
        priority=20,
    )

    registry.register_tool(
        name="list_directory",
        category=ToolCategory.FILES,
        description="List files in a repository directory",
        func=list_directory,
        priority=30,
    )


# Toolset for direct use
local_files_toolset = [read_file_tool, search_files_tool, list_dir_tool]
