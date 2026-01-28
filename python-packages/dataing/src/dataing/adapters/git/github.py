"""GitHub provider implementation."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

import httpx
import structlog

from dataing.adapters.git.provider import GitCommit

logger = structlog.get_logger()

# GitHub API base URL
GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_URL = "https://github.com/login/oauth/access_token"

# Rate limit thresholds for warnings
RATE_LIMIT_WARNING_THRESHOLD = 100


class GitHubProvider:
    """GitHub API client for fetching commits and OAuth.

    Implements the GitProvider protocol for GitHub repositories.
    Uses the GitHub REST API for fetching commits and OAuth token exchange.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        """Initialize the GitHub provider.

        Args:
            client_id: GitHub OAuth App client ID.
            client_secret: GitHub OAuth App client secret.
        """
        self.client_id = client_id
        self.client_secret = client_secret

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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GITHUB_OAUTH_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )

            if response.status_code != 200:
                logger.error(
                    "github_oauth_exchange_failed",
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise ValueError(f"OAuth exchange failed: {response.status_code}")

            data = response.json()

            if "error" in data:
                logger.error(
                    "github_oauth_error",
                    error=data.get("error"),
                    description=data.get("error_description"),
                )
                raise ValueError(f"OAuth error: {data.get('error_description', data['error'])}")

            access_token = data.get("access_token")
            if not access_token:
                raise ValueError("No access token in OAuth response")

            logger.info("github_oauth_exchange_success")
            token: str = access_token
            return token

    async def fetch_commits(
        self,
        repo_url: str,
        access_token: str,
        since_hash: str | None = None,
        branch: str = "main",
        tracked_paths: list[str] | None = None,
        max_commits: int = 1000,
    ) -> list[GitCommit]:
        """Fetch commits from a GitHub repository.

        Uses the GitHub REST API to fetch commits with pagination.
        Supports incremental sync via since_hash parameter.

        Args:
            repo_url: The repository URL (e.g., https://github.com/owner/repo).
            access_token: OAuth access token for authentication.
            since_hash: Only return commits after this hash (for incremental sync).
            branch: Branch to fetch commits from.
            tracked_paths: Only include commits affecting these paths.
            max_commits: Maximum number of commits to fetch.

        Returns:
            List of commits, newest first.
        """
        owner, repo = self._parse_repo_url(repo_url)
        commits: list[GitCommit] = []
        page = 1
        per_page = 100  # GitHub max

        async with httpx.AsyncClient() as client:
            while len(commits) < max_commits:
                # Fetch commit list
                params: dict[str, str | int] = {
                    "sha": branch,
                    "per_page": per_page,
                    "page": page,
                }

                # Note: GitHub API doesn't support path filtering on /commits endpoint
                # We'll filter after fetching
                if tracked_paths and len(tracked_paths) == 1:
                    params["path"] = tracked_paths[0]

                response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits",
                    params=params,
                    headers=self._get_headers(access_token),
                )

                self._check_rate_limit(response)

                if response.status_code != 200:
                    logger.error(
                        "github_fetch_commits_failed",
                        status=response.status_code,
                        owner=owner,
                        repo=repo,
                    )
                    break

                commit_list = response.json()
                if not commit_list:
                    break  # No more commits

                for commit_data in commit_list:
                    sha = commit_data["sha"]

                    # Stop if we've reached the since_hash (incremental sync)
                    if since_hash and sha == since_hash:
                        logger.info(
                            "github_incremental_sync_stop",
                            since_hash=since_hash,
                            commits_fetched=len(commits),
                        )
                        return commits

                    # Fetch detailed commit info to get files_changed
                    commit_detail = await self._fetch_commit_detail(
                        client, owner, repo, sha, access_token
                    )

                    if commit_detail is None:
                        continue

                    # Filter by tracked_paths if multiple paths specified
                    if tracked_paths and len(tracked_paths) > 1:
                        if not self._matches_tracked_paths(
                            commit_detail.files_changed, tracked_paths
                        ):
                            continue

                    commits.append(commit_detail)

                    if len(commits) >= max_commits:
                        break

                page += 1

                # Safety check: stop if response had fewer than per_page items
                if len(commit_list) < per_page:
                    break

        logger.info(
            "github_fetch_commits_complete",
            owner=owner,
            repo=repo,
            branch=branch,
            commits_fetched=len(commits),
        )
        return commits

    async def _fetch_commit_detail(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        sha: str,
        access_token: str,
    ) -> GitCommit | None:
        """Fetch detailed commit information including files changed.

        Args:
            client: HTTP client to use.
            owner: Repository owner.
            repo: Repository name.
            sha: Commit SHA.
            access_token: OAuth access token.

        Returns:
            GitCommit with full details, or None if fetch failed.
        """
        response = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{sha}",
            headers=self._get_headers(access_token),
        )

        self._check_rate_limit(response)

        if response.status_code != 200:
            logger.warning(
                "github_fetch_commit_detail_failed",
                status=response.status_code,
                sha=sha,
            )
            return None

        data = response.json()
        commit_info = data.get("commit", {})
        author_info = commit_info.get("author", {})

        # Parse committed_at timestamp
        committed_at = None
        date_str = author_info.get("date")
        if date_str:
            try:
                committed_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Extract files changed
        files = data.get("files", [])
        files_changed = [f.get("filename", "") for f in files if f.get("filename")]

        return GitCommit(
            hash=sha,
            author_name=author_info.get("name"),
            author_email=author_info.get("email"),
            message=commit_info.get("message"),
            committed_at=committed_at,
            files_changed=files_changed,
            raw_diff=None,  # Skip raw diff to save space; can fetch on demand
        )

    async def validate_token(self, access_token: str) -> bool:
        """Check if the access token is still valid.

        Args:
            access_token: The OAuth access token to validate.

        Returns:
            True if the token is valid, False otherwise.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_BASE}/user",
                headers=self._get_headers(access_token),
            )

            self._check_rate_limit(response)

            if response.status_code == 200:
                logger.info("github_token_valid")
                return True
            elif response.status_code == 401:
                logger.warning("github_token_invalid")
                return False
            else:
                logger.error(
                    "github_token_validation_unexpected",
                    status=response.status_code,
                )
                return False

    def _parse_repo_url(self, repo_url: str) -> tuple[str, str]:
        """Parse owner and repo name from a GitHub URL.

        Args:
            repo_url: GitHub repository URL.

        Returns:
            Tuple of (owner, repo).

        Raises:
            ValueError: If URL format is invalid.
        """
        # Handle HTTPS URLs: https://github.com/owner/repo
        parsed = urlparse(repo_url)
        if parsed.netloc in ("github.com", "www.github.com"):
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                owner = path_parts[0]
                repo = path_parts[1].removesuffix(".git")
                return owner, repo

        # Handle SSH URLs: git@github.com:owner/repo.git
        ssh_match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", repo_url)
        if ssh_match:
            return ssh_match.group(1), ssh_match.group(2)

        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    def _get_headers(self, access_token: str) -> dict[str, str]:
        """Build request headers for GitHub API.

        Args:
            access_token: OAuth access token.

        Returns:
            Headers dictionary.
        """
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """Check GitHub rate limit headers and log warnings.

        Args:
            response: HTTP response to check.
        """
        remaining = response.headers.get("X-RateLimit-Remaining")
        limit = response.headers.get("X-RateLimit-Limit")

        if remaining is not None:
            remaining_int = int(remaining)
            if remaining_int < RATE_LIMIT_WARNING_THRESHOLD:
                logger.warning(
                    "github_rate_limit_low",
                    remaining=remaining_int,
                    limit=limit,
                )

    def _matches_tracked_paths(self, files_changed: list[str], tracked_paths: list[str]) -> bool:
        """Check if any changed files match the tracked paths.

        Args:
            files_changed: List of changed file paths.
            tracked_paths: List of path prefixes to match.

        Returns:
            True if any file matches a tracked path.
        """
        for file_path in files_changed:
            for tracked_path in tracked_paths:
                if file_path.startswith(tracked_path):
                    return True
        return False
