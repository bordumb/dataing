"""Protocol definition for Git Hunter tool.

Defines the interface that GitHunterAdapter must implement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ._types import BlameResult, FileExpert, PRDiscussion


@runtime_checkable
class GitHunterProtocol(Protocol):
    """Protocol for Git Hunter forensic code ownership tool.

    Provides methods to:
    - Blame individual lines to find who last modified them
    - Find PR discussions for commits
    - Determine file experts based on commit frequency
    """

    async def blame_line(
        self,
        repo_path: Path,
        file_path: str,
        line_no: int,
    ) -> BlameResult:
        """Get blame information for a specific line.

        Args:
            repo_path: Path to the git repository root.
            file_path: Path to file relative to repo root.
            line_no: Line number to blame (1-indexed).

        Returns:
            BlameResult with author, commit, and line information.

        Raises:
            RepoNotFoundError: If repo_path is not a git repository.
            FileNotFoundInRepoError: If file doesn't exist in repo.
            LineOutOfRangeError: If line_no is invalid.
            BinaryFileError: If file is binary.
        """
        ...

    async def find_pr_discussion(
        self,
        repo_path: Path,
        commit_hash: str,
    ) -> PRDiscussion | None:
        """Find the PR discussion for a commit.

        Args:
            repo_path: Path to the git repository root.
            commit_hash: Full or abbreviated commit SHA.

        Returns:
            PRDiscussion if commit is associated with a PR, None otherwise.

        Raises:
            RepoNotFoundError: If repo_path is not a git repository.
            RateLimitedError: If GitHub rate limit exceeded.
            GitHubUnavailableError: If GitHub API is unavailable.
        """
        ...

    async def get_expert_for_file(
        self,
        repo_path: Path,
        file_path: str,
        window_days: int = 90,
        limit: int = 3,
    ) -> list[FileExpert]:
        """Get experts for a file based on commit frequency.

        Args:
            repo_path: Path to the git repository root.
            file_path: Path to file relative to repo root.
            window_days: Time window for commit history (0 or None for all time).
            limit: Maximum number of experts to return.

        Returns:
            List of FileExpert sorted by commit count (descending).

        Raises:
            RepoNotFoundError: If repo_path is not a git repository.
            FileNotFoundInRepoError: If file doesn't exist in repo.
        """
        ...
