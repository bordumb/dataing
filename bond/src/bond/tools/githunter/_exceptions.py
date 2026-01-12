"""Exception hierarchy for Git Hunter tool.

All exceptions inherit from GitHunterError for easy catching.
"""

from __future__ import annotations

from datetime import datetime


class GitHunterError(Exception):
    """Base exception for all Git Hunter errors."""

    pass


class RepoNotFoundError(GitHunterError):
    """Raised when path is not inside a git repository."""

    def __init__(self, path: str) -> None:
        """Initialize with the invalid path.

        Args:
            path: The path that is not in a git repository.
        """
        self.path = path
        super().__init__(f"Path is not inside a git repository: {path}")


class FileNotFoundInRepoError(GitHunterError):
    """Raised when file does not exist in the repository."""

    def __init__(self, file_path: str, repo_path: str) -> None:
        """Initialize with file and repo paths.

        Args:
            file_path: The file that was not found.
            repo_path: The repository path.
        """
        self.file_path = file_path
        self.repo_path = repo_path
        super().__init__(f"File not found in repository: {file_path} (repo: {repo_path})")


class LineOutOfRangeError(GitHunterError):
    """Raised when line number is invalid for the file."""

    def __init__(self, line_no: int, max_lines: int | None = None) -> None:
        """Initialize with line number and optional max.

        Args:
            line_no: The invalid line number.
            max_lines: Maximum valid line number if known.
        """
        self.line_no = line_no
        self.max_lines = max_lines
        if max_lines is not None:
            msg = f"Line {line_no} out of range (file has {max_lines} lines)"
        else:
            msg = f"Line {line_no} out of range"
        super().__init__(msg)


class BinaryFileError(GitHunterError):
    """Raised when attempting to blame a binary file."""

    def __init__(self, file_path: str) -> None:
        """Initialize with file path.

        Args:
            file_path: The binary file path.
        """
        self.file_path = file_path
        super().__init__(f"Cannot blame binary file: {file_path}")


class ShallowCloneError(GitHunterError):
    """Raised when shallow clone prevents full history access."""

    def __init__(self, message: str = "Repository is a shallow clone") -> None:
        """Initialize with message.

        Args:
            message: Description of the shallow clone issue.
        """
        super().__init__(message)


class RateLimitedError(GitHunterError):
    """Raised when GitHub API rate limit is exceeded."""

    def __init__(
        self,
        retry_after_seconds: int,
        reset_at: datetime,
        message: str | None = None,
    ) -> None:
        """Initialize with rate limit details.

        Args:
            retry_after_seconds: Seconds until rate limit resets.
            reset_at: UTC datetime when rate limit resets.
            message: Optional custom message.
        """
        self.retry_after_seconds = retry_after_seconds
        self.reset_at = reset_at
        msg = message or f"GitHub rate limit exceeded. Retry after {retry_after_seconds}s"
        super().__init__(msg)


class GitHubUnavailableError(GitHunterError):
    """Raised when GitHub API is unavailable."""

    def __init__(self, message: str = "GitHub API is unavailable") -> None:
        """Initialize with message.

        Args:
            message: Description of the unavailability.
        """
        super().__init__(message)
