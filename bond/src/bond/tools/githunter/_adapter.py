"""GitHunter adapter implementation.

Provides git forensics capabilities via subprocess calls to git CLI
and httpx calls to GitHub API.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ._exceptions import (
    BinaryFileError,
    FileNotFoundInRepoError,
    LineOutOfRangeError,
    RepoNotFoundError,
)
from ._types import AuthorProfile, BlameResult, FileExpert, PRDiscussion

if TYPE_CHECKING:
    pass


class GitHunterAdapter:
    """Git Hunter adapter for forensic code ownership analysis.

    Uses git CLI via async subprocess for blame and log operations.
    Optionally uses GitHub API for PR lookup and author enrichment.
    """

    def __init__(self, timeout: int = 30) -> None:
        """Initialize adapter.

        Args:
            timeout: Timeout in seconds for git commands.
        """
        self._timeout = timeout
        self._head_cache: dict[str, str] = {}

    async def _run_git(
        self,
        repo_path: Path,
        *args: str,
    ) -> tuple[str, str, int]:
        """Run a git command asynchronously.

        Args:
            repo_path: Path to git repository.
            *args: Git command arguments.

        Returns:
            Tuple of (stdout, stderr, return_code).

        Raises:
            RepoNotFoundError: If repo_path is not a git repository.
        """
        cmd = ["git", "-C", str(repo_path), *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
            return (
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
                proc.returncode or 0,
            )
        except FileNotFoundError as e:
            raise RepoNotFoundError(str(repo_path)) from e

    async def _get_head_sha(self, repo_path: Path) -> str:
        """Get current HEAD SHA for cache invalidation.

        Args:
            repo_path: Path to git repository.

        Returns:
            HEAD commit SHA.
        """
        cache_key = str(repo_path.resolve())
        if cache_key in self._head_cache:
            return self._head_cache[cache_key]

        stdout, stderr, code = await self._run_git(repo_path, "rev-parse", "HEAD")
        if code != 0:
            raise RepoNotFoundError(str(repo_path))

        sha = stdout.strip()
        self._head_cache[cache_key] = sha
        return sha

    def _parse_porcelain_blame(self, output: str) -> dict[str, str]:
        """Parse git blame --porcelain output.

        Args:
            output: Raw porcelain output from git blame.

        Returns:
            Dict with parsed fields: commit, author, author-mail,
            author-time, summary, content.
        """
        result: dict[str, str] = {}
        lines = output.strip().split("\n")

        if not lines:
            return result

        # First line is: <sha> <orig_line> <final_line> [<num_lines>]
        first_line = lines[0]
        parts = first_line.split()
        if parts:
            result["commit"] = parts[0]

        # Parse header lines
        for line in lines[1:]:
            if line.startswith("\t"):
                # Content line (starts with tab)
                result["content"] = line[1:]
            elif " " in line:
                key, _, value = line.partition(" ")
                result[key] = value

        return result

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
        if line_no < 1:
            raise LineOutOfRangeError(line_no)

        # Check if repo is valid
        await self._get_head_sha(repo_path)

        # Run git blame
        stdout, stderr, code = await self._run_git(
            repo_path,
            "blame",
            "--porcelain",
            "-L",
            f"{line_no},{line_no}",
            "--",
            file_path,
        )

        if code != 0:
            stderr_lower = stderr.lower()
            if "no such path" in stderr_lower or "does not exist" in stderr_lower:
                raise FileNotFoundInRepoError(file_path, str(repo_path))
            if "invalid line" in stderr_lower or "no lines to blame" in stderr_lower:
                raise LineOutOfRangeError(line_no)
            if "binary file" in stderr_lower:
                raise BinaryFileError(file_path)
            if "fatal: not a git repository" in stderr_lower:
                raise RepoNotFoundError(str(repo_path))
            # Generic error
            raise RepoNotFoundError(str(repo_path))

        # Parse output
        parsed = self._parse_porcelain_blame(stdout)

        if not parsed.get("commit"):
            raise LineOutOfRangeError(line_no)

        commit_hash = parsed["commit"]
        is_boundary = commit_hash.startswith("^") or parsed.get("boundary") == "1"

        # Clean up boundary marker from hash
        if commit_hash.startswith("^"):
            commit_hash = commit_hash[1:]

        # Parse author time
        author_time_str = parsed.get("author-time", "0")
        try:
            author_time = int(author_time_str)
            commit_date = datetime.fromtimestamp(author_time, tz=UTC)
        except (ValueError, OSError):
            commit_date = datetime.now(tz=UTC)

        # Build author profile
        author = AuthorProfile(
            git_email=parsed.get("author-mail", "").strip("<>"),
            git_name=parsed.get("author", "Unknown"),
        )

        return BlameResult(
            line_no=line_no,
            content=parsed.get("content", ""),
            author=author,
            commit_hash=commit_hash,
            commit_date=commit_date,
            commit_message=parsed.get("summary", ""),
            is_boundary=is_boundary,
        )

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
        """
        # TODO: Implement in fn-3.3
        return None

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
            window_days: Time window for commit history (0 for all time).
            limit: Maximum number of experts to return.

        Returns:
            List of FileExpert sorted by commit count (descending).
        """
        # TODO: Implement in fn-3.4
        return []
