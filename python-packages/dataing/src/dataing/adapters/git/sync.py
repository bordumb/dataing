"""Git repository sync service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.git.provider import GitCommit, GitProvider
from dataing.core.git_asset_parser import parse_affected_assets

logger = structlog.get_logger()


class GitSyncService:
    """Orchestrates fetching commits from git providers and storing them.

    This service handles the sync lifecycle:
    1. Fetch repository record from database
    2. Update sync status to 'syncing'
    3. Get latest commit hash for incremental sync
    4. Fetch commits from the appropriate provider
    5. Bulk insert code_changes (asset matching is done in a separate step)
    6. Update sync status to 'synced' or 'error'
    """

    def __init__(self, db: AppDatabase, providers: dict[str, GitProvider]) -> None:
        """Initialize the sync service.

        Args:
            db: Application database for storing sync results.
            providers: Dictionary mapping provider names to implementations.
                       e.g., {"github": GitHubProvider(...), "gitlab": GitLabProvider(...)}
        """
        self.db = db
        self.providers = providers

    async def sync_repository(self, repo_id: UUID, tenant_id: UUID) -> int:
        """Sync a single repository, fetching new commits.

        Args:
            repo_id: The git repository ID.
            tenant_id: The tenant ID (for authorization check).

        Returns:
            Number of new commits synced.

        Raises:
            ValueError: If repository not found or provider not supported.
        """
        # 1. Fetch repo record from DB
        repo = await self.db.get_git_repository(repo_id, tenant_id)
        if not repo:
            raise ValueError(f"Git repository {repo_id} not found for tenant {tenant_id}")

        provider_name = repo["provider"]
        provider = self.providers.get(provider_name)
        if not provider:
            raise ValueError(f"Unsupported git provider: {provider_name}")

        logger.info(
            "git_sync_starting",
            repo_id=str(repo_id),
            provider=provider_name,
            url=repo["url"],
        )

        try:
            # 2. Update sync_status to 'syncing'
            await self.db.update_git_repo_sync_status(repo_id, "syncing")

            # 3. Get latest commit hash for incremental sync
            since_hash = await self.db.get_latest_commit_hash(repo_id)
            logger.info(
                "git_sync_incremental",
                repo_id=str(repo_id),
                since_hash=since_hash,
            )

            # 4. Fetch commits from provider
            access_token = repo.get("access_token_encrypted", "")
            if not access_token:
                raise ValueError("Repository has no access token configured")

            commits = await provider.fetch_commits(
                repo_url=repo["url"],
                access_token=access_token,
                since_hash=since_hash,
                branch=repo.get("default_branch", "main"),
                tracked_paths=repo.get("tracked_paths"),
            )

            if not commits:
                logger.info(
                    "git_sync_no_new_commits",
                    repo_id=str(repo_id),
                )
                await self.db.update_git_repo_sync_status(
                    repo_id, "synced", last_sync_at=datetime.now(UTC)
                )
                return 0

            # 5. Bulk insert code_changes with asset matching
            changes_to_insert: list[dict[str, Any]] = []
            for commit in commits:
                # Extract affected assets from each changed file
                assets = _extract_commit_assets(commit)

                changes_to_insert.append(
                    {
                        "repo_id": repo_id,
                        "commit_hash": commit.hash,
                        "author_name": commit.author_name,
                        "author_email": commit.author_email,
                        "message": commit.message,
                        "committed_at": commit.committed_at,
                        "affected_assets": assets,
                        "raw_diff": commit.raw_diff,
                        "files_changed": commit.files_changed,
                    }
                )

            inserted = await self.db.bulk_create_code_changes(changes_to_insert)

            # 6. Update sync_status to 'synced'
            await self.db.update_git_repo_sync_status(
                repo_id, "synced", last_sync_at=datetime.now(UTC)
            )

            logger.info(
                "git_sync_complete",
                repo_id=str(repo_id),
                commits_fetched=len(commits),
                commits_inserted=inserted,
            )
            return inserted

        except Exception as e:
            # 7. On error: update sync_status to 'error'
            error_msg = str(e)[:500]  # Truncate error message
            await self.db.update_git_repo_sync_status(repo_id, "error", error=error_msg)

            logger.error(
                "git_sync_failed",
                repo_id=str(repo_id),
                error=error_msg,
            )
            raise

    async def sync_all_repositories(self, tenant_id: UUID) -> dict[UUID, int]:
        """Sync all repositories for a tenant.

        Args:
            tenant_id: The tenant ID.

        Returns:
            Dictionary mapping repo_id to number of commits synced.
        """
        repos = await self.db.list_git_repositories(tenant_id)
        results: dict[UUID, int] = {}

        for repo in repos:
            repo_id = repo["id"]
            try:
                count = await self.sync_repository(repo_id, tenant_id)
                results[repo_id] = count
            except Exception as e:
                logger.error(
                    "git_sync_repo_failed",
                    repo_id=str(repo_id),
                    error=str(e),
                )
                results[repo_id] = -1  # Indicates failure

        return results


def _extract_commit_assets(commit: GitCommit) -> list[dict[str, str]]:
    """Extract affected assets from all changed files in a commit.

    Args:
        commit: The parsed git commit.

    Returns:
        Deduplicated list of affected assets.
    """
    all_assets: list[dict[str, str]] = []
    seen_names: set[str] = set()

    for file_path in commit.files_changed:
        # Use raw_diff if available, otherwise pass None
        # Note: Currently raw_diff is per-commit, not per-file
        # For full accuracy, we'd need per-file diffs from the provider
        assets = parse_affected_assets(file_path, commit.raw_diff)
        for asset in assets:
            if asset["name"] not in seen_names:
                seen_names.add(asset["name"])
                all_assets.append(asset)

    return all_assets
