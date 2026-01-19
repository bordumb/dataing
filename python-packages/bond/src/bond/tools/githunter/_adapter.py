"""GitHunter adapter implementation.

Provides git forensics capabilities via subprocess calls to git CLI
and httpx calls to GitHub API.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ._exceptions import (
    BinaryFileError,
    FileNotFoundInRepoError,
    GitHubUnavailableError,
    LineOutOfRangeError,
    RateLimitedError,
    RepoNotFoundError,
)
from ._types import AuthorProfile, BlameResult, FileExpert, PRDiscussion

logger = logging.getLogger(__name__)

# Regex patterns for parsing git remote URLs
SSH_REMOTE_PATTERN = re.compile(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$")
HTTPS_REMOTE_PATTERN = re.compile(r"https://github\.com/([^/]+)/(.+?)(?:\.git)?$")


class GitHunterAdapter:
    """Git Hunter adapter for forensic code ownership analysis.

    Uses git CLI via async subprocess for blame and log operations.
    Optionally uses GitHub API for PR lookup and author enrichment.
    """

    def __init__(self, timeout: int = 30) -> None:
        """Initialize adapter.

        Args:
            timeout: Timeout in seconds for git/HTTP operations.
        """
        self._timeout = timeout
        self._head_cache: dict[str, str] = {}
        self._github_token = os.environ.get("GITHUB_TOKEN")
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for GitHub API.

        Returns:
            Configured httpx.AsyncClient.
        """
        if self._http_client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self._github_token:
                headers["Authorization"] = f"Bearer {self._github_token}"
            self._http_client = httpx.AsyncClient(
                base_url="https://api.github.com",
                headers=headers,
                timeout=self._timeout,
            )
        return self._http_client

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

    async def _get_github_repo(self, repo_path: Path) -> tuple[str, str] | None:
        """Get GitHub owner/repo from git remote URL.

        Args:
            repo_path: Path to git repository.

        Returns:
            Tuple of (owner, repo) or None if not a GitHub repo.
        """
        stdout, stderr, code = await self._run_git(repo_path, "remote", "get-url", "origin")
        if code != 0:
            return None

        remote_url = stdout.strip()

        # Try SSH format: git@github.com:owner/repo.git
        match = SSH_REMOTE_PATTERN.match(remote_url)
        if match:
            return (match.group(1), match.group(2))

        # Try HTTPS format: https://github.com/owner/repo.git
        match = HTTPS_REMOTE_PATTERN.match(remote_url)
        if match:
            return (match.group(1), match.group(2))

        return None

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """Check GitHub rate limit headers and warn/raise as needed.

        Args:
            response: HTTP response from GitHub API.

        Raises:
            RateLimitedError: If rate limit is exceeded.
        """
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_at = response.headers.get("X-RateLimit-Reset")

        if remaining is not None:
            remaining_int = int(remaining)
            if remaining_int < 100:
                logger.warning("GitHub API rate limit low: %d requests remaining", remaining_int)

        if response.status_code == 403:
            # Check if it's a rate limit error
            if "rate limit" in response.text.lower():
                reset_timestamp = int(reset_at) if reset_at else 0
                reset_datetime = datetime.fromtimestamp(reset_timestamp, tz=UTC)
                retry_after = max(0, reset_timestamp - int(datetime.now(tz=UTC).timestamp()))
                raise RateLimitedError(retry_after, reset_datetime)

    def _parse_porcelain_blame(self, output: str) -> dict[str, str]:
        """Parse git blame --porcelain output.

        Args:
            output: Raw porcelain output from git blame.

        Returns:
            Dict with parsed fields.
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

        # Build author profile (enrichment happens separately if needed)
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

        Raises:
            RateLimitedError: If GitHub rate limit exceeded.
            GitHubUnavailableError: If GitHub API is unavailable.
        """
        if not self._github_token:
            logger.debug("No GITHUB_TOKEN set, skipping PR lookup")
            return None

        # Get owner/repo from remote
        github_repo = await self._get_github_repo(repo_path)
        if not github_repo:
            logger.debug("Not a GitHub repository, skipping PR lookup")
            return None

        owner, repo = github_repo
        client = await self._get_http_client()

        try:
            # Find PRs associated with this commit
            response = await client.get(f"/repos/{owner}/{repo}/commits/{commit_hash}/pulls")
            self._check_rate_limit(response)

            if response.status_code == 404:
                return None
            if response.status_code != 200:
                logger.warning(
                    "GitHub API error %d for commit %s", response.status_code, commit_hash
                )
                return None

            prs = response.json()
            if not prs:
                return None

            # Get the first (most recent) PR
            pr_data = prs[0]
            pr_number = pr_data["number"]

            # Fetch issue comments (top-level PR comments)
            comments_response = await client.get(
                f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
                params={"per_page": 100},
            )
            self._check_rate_limit(comments_response)

            comments: list[str] = []
            if comments_response.status_code == 200:
                for comment in comments_response.json():
                    body = comment.get("body", "")
                    if body:
                        comments.append(body)

            return PRDiscussion(
                pr_number=pr_number,
                title=pr_data.get("title", ""),
                body=pr_data.get("body", "") or "",
                url=pr_data.get("html_url", ""),
                issue_comments=tuple(comments),
            )

        except httpx.TimeoutException as e:
            raise GitHubUnavailableError("GitHub API timeout") from e
        except httpx.RequestError as e:
            raise GitHubUnavailableError(f"GitHub API error: {e}") from e

    async def enrich_author(self, author: AuthorProfile) -> AuthorProfile:
        """Enrich author profile with GitHub data.

        Args:
            author: Author profile with git_email.

        Returns:
            Author profile with github_username and avatar_url if found.
        """
        if not self._github_token or not author.git_email:
            return author

        client = await self._get_http_client()

        try:
            # Search for user by email
            response = await client.get(
                "/search/users",
                params={"q": f"{author.git_email} in:email"},
            )
            self._check_rate_limit(response)

            if response.status_code != 200:
                return author

            data = response.json()
            if data.get("total_count", 0) > 0 and data.get("items"):
                user = data["items"][0]
                return AuthorProfile(
                    git_email=author.git_email,
                    git_name=author.git_name,
                    github_username=user.get("login"),
                    github_avatar_url=user.get("avatar_url"),
                )

        except (httpx.TimeoutException, httpx.RequestError):
            # Graceful degradation - return unenriched author
            pass

        return author

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

        Raises:
            RepoNotFoundError: If repo_path is not a git repository.
            FileNotFoundInRepoError: If file doesn't exist in repo.
        """
        # Build git log command
        # Format: email|name|hash|timestamp
        args = [
            "log",
            "--format=%aE|%aN|%H|%at",
            "--follow",
            "--no-merges",
        ]

        # Add time window if specified
        if window_days and window_days > 0:
            args.append(f"--since={window_days} days ago")

        args.extend(["--", file_path])

        stdout, stderr, code = await self._run_git(repo_path, *args)

        if code != 0:
            stderr_lower = stderr.lower()
            if "fatal: not a git repository" in stderr_lower:
                raise RepoNotFoundError(str(repo_path))
            # Empty output for non-existent files is handled below
            return []

        # Parse output and group by author email (case-insensitive)
        author_stats: dict[str, dict[str, str | int | datetime]] = {}

        for line in stdout.strip().split("\n"):
            if not line or "|" not in line:
                continue

            parts = line.split("|")
            if len(parts) < 4:
                continue

            email = parts[0].lower()  # Case-insensitive grouping
            name = parts[1]
            # commit_hash = parts[2]  # Not needed for stats
            try:
                timestamp = int(parts[3])
                commit_date = datetime.fromtimestamp(timestamp, tz=UTC)
            except (ValueError, OSError):
                commit_date = datetime.now(tz=UTC)

            if email not in author_stats:
                author_stats[email] = {
                    "name": name,
                    "email": email,
                    "commit_count": 0,
                    "last_commit_date": commit_date,
                }

            current_count = author_stats[email]["commit_count"]
            if isinstance(current_count, int):
                author_stats[email]["commit_count"] = current_count + 1

            # Track most recent commit
            current_last = author_stats[email]["last_commit_date"]
            if isinstance(current_last, datetime) and commit_date > current_last:
                author_stats[email]["last_commit_date"] = commit_date

        # Sort by commit count descending and take top N
        sorted_authors = sorted(
            author_stats.values(),
            key=lambda x: x["commit_count"] if isinstance(x["commit_count"], int) else 0,
            reverse=True,
        )[:limit]

        # Build FileExpert results
        experts: list[FileExpert] = []
        for stats in sorted_authors:
            author = AuthorProfile(
                git_email=str(stats["email"]),
                git_name=str(stats["name"]),
            )
            commit_count = stats["commit_count"]
            last_date = stats["last_commit_date"]
            last_commit = last_date if isinstance(last_date, datetime) else datetime.now(tz=UTC)
            experts.append(
                FileExpert(
                    author=author,
                    commit_count=commit_count if isinstance(commit_count, int) else 0,
                    last_commit_date=last_commit,
                )
            )

        return experts

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
