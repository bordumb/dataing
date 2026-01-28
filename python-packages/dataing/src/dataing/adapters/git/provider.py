"""Git provider protocol and data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class GitCommit:
    """Parsed commit data from a git provider."""

    hash: str
    author_name: str | None = None
    author_email: str | None = None
    message: str | None = None
    committed_at: datetime | None = None
    files_changed: list[str] = field(default_factory=list)
    raw_diff: str | None = None


class GitProvider(Protocol):
    """Protocol for git provider implementations.

    Implementations include GitHub, GitLab, and Bitbucket.
    Each provider handles OAuth token exchange and commit fetching
    via their respective APIs.
    """

    async def exchange_oauth_code(self, code: str, redirect_uri: str) -> str:
        """Exchange an OAuth authorization code for an access token.

        Args:
            code: The authorization code from OAuth callback.
            redirect_uri: The redirect URI used in the authorization request.

        Returns:
            The access token.

        Raises:
            ValueError: If the code is invalid or exchange fails.
        """
        ...

    async def fetch_commits(
        self,
        repo_url: str,
        access_token: str,
        since_hash: str | None = None,
        branch: str = "main",
        tracked_paths: list[str] | None = None,
        max_commits: int = 1000,
    ) -> list[GitCommit]:
        """Fetch commits from a remote repository.

        Supports incremental sync via since_hash - fetches only commits
        after the specified commit hash.

        Args:
            repo_url: The repository URL (e.g., https://github.com/owner/repo).
            access_token: OAuth access token for authentication.
            since_hash: Only return commits after this hash (for incremental sync).
            branch: Branch to fetch commits from.
            tracked_paths: Only include commits affecting these paths (monorepo support).
            max_commits: Maximum number of commits to fetch.

        Returns:
            List of commits, newest first.
        """
        ...

    async def validate_token(self, access_token: str) -> bool:
        """Check if the access token is still valid.

        Args:
            access_token: The OAuth access token to validate.

        Returns:
            True if the token is valid, False otherwise.
        """
        ...
