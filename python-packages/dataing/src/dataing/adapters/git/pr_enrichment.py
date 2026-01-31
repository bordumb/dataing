"""PR metadata enrichment using bond-agent tools.

This module provides a service for enriching commits with PR metadata
using bond-agent's githunter and github toolsets rather than building
custom API clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from bond.tools.github import GitHubAdapter
    from bond.tools.githunter import GitHunterAdapter

logger = structlog.get_logger()


@dataclass
class PRMetadata:
    """PR metadata extracted from bond-agent tools."""

    pr_number: int
    pr_url: str
    pr_title: str
    pr_author: str
    pr_merged_at: datetime | None


class PREnrichmentService:
    """Enriches commits with PR metadata using bond-agent.

    This service wraps bond-agent's githunter and github tools to provide
    a simple interface for looking up PR metadata for commits. It uses:

    - githunter.find_pr_discussion: Local git-based PR lookup (no API calls)
    - github.get_pr: Full PR details from GitHub API (when token available)

    The service gracefully falls back when GitHub API is not configured,
    returning partial metadata from the local git lookup.
    """

    def __init__(
        self,
        repo_path: Path | None = None,
        github_token: str | None = None,
    ) -> None:
        """Initialize the enrichment service.

        Args:
            repo_path: Path to the local git repository (for githunter).
            github_token: Optional GitHub API token for full PR details.
        """
        self.repo_path = repo_path
        self._githunter: GitHunterAdapter | None = None
        self._github: GitHubAdapter | None = None
        self._github_token = github_token

    @property
    def githunter(self) -> GitHunterAdapter:
        """Lazy-load the GitHunter adapter."""
        if self._githunter is None:
            from bond.tools.githunter import GitHunterAdapter

            self._githunter = GitHunterAdapter()
        return self._githunter

    @property
    def github(self) -> GitHubAdapter | None:
        """Lazy-load the GitHub adapter (if token available)."""
        if self._github is None and self._github_token:
            from bond.tools.github import GitHubAdapter

            self._github = GitHubAdapter(token=self._github_token)
        return self._github

    async def get_pr_for_commit(
        self,
        commit_hash: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> PRMetadata | None:
        """Find PR metadata for a commit.

        Uses githunter.find_pr_discussion for local git lookup,
        optionally falls back to github.get_pr for full metadata.

        Args:
            commit_hash: The git commit SHA to look up.
            owner: Repository owner (for GitHub API fallback).
            repo: Repository name (for GitHub API fallback).

        Returns:
            PRMetadata if a PR is found, None otherwise.
        """
        if not self.repo_path:
            logger.debug("pr_enrichment_no_repo_path", commit_hash=commit_hash)
            return None

        try:
            # Try local git first (no API calls)
            pr_discussion = self.githunter.find_pr_discussion(
                repo_path=self.repo_path,
                commit_hash=commit_hash,
            )

            if pr_discussion is None:
                return None

            # If we have GitHub API access, get full PR details
            if self.github and owner and repo:
                try:
                    pr = self.github.get_pr(
                        owner=owner,
                        repo=repo,
                        number=pr_discussion.number,
                    )
                    return PRMetadata(
                        pr_number=pr.number,
                        pr_url=pr.url,
                        pr_title=pr.title,
                        pr_author=pr.author.login if pr.author else "",
                        pr_merged_at=pr.merged_at,
                    )
                except Exception as e:
                    logger.warning(
                        "pr_enrichment_github_api_failed",
                        commit_hash=commit_hash,
                        pr_number=pr_discussion.number,
                        error=str(e),
                    )
                    # Fall through to use local data

            # Fallback: use what we got from git
            return PRMetadata(
                pr_number=pr_discussion.number,
                pr_url=pr_discussion.url or "",
                pr_title=pr_discussion.title,
                pr_author="",  # Not available from git alone
                pr_merged_at=None,
            )

        except Exception as e:
            logger.warning(
                "pr_enrichment_failed",
                commit_hash=commit_hash,
                error=str(e),
            )
            return None

    async def enrich_commits(
        self,
        commit_hashes: list[str],
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, PRMetadata]:
        """Batch enrich multiple commits with PR metadata.

        Args:
            commit_hashes: List of commit SHAs to enrich.
            owner: Repository owner (for GitHub API fallback).
            repo: Repository name (for GitHub API fallback).

        Returns:
            Dictionary mapping commit_hash to PRMetadata for commits that have PRs.
        """
        results: dict[str, PRMetadata] = {}
        for commit_hash in commit_hashes:
            pr = await self.get_pr_for_commit(commit_hash, owner, repo)
            if pr:
                results[commit_hash] = pr
        return results

    async def close(self) -> None:
        """Close any open connections."""
        if self._githunter:
            await self._githunter.close()
        if self._github:
            await self._github.close()
