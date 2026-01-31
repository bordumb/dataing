"""URL templates for git provider deep links.

This module provides URL template rendering for commit and PR links across
GitHub, GitLab, and Bitbucket. Each provider has different URL patterns,
and self-hosted instances use custom base URLs.
"""

from enum import Enum


class GitProvider(str, Enum):
    """Supported git providers."""

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"


# Default base URLs (overridden for self-hosted instances)
DEFAULT_BASE_URLS: dict[GitProvider, str] = {
    GitProvider.GITHUB: "https://github.com",
    GitProvider.GITLAB: "https://gitlab.com",
    GitProvider.BITBUCKET: "https://bitbucket.org",
}

# URL patterns per provider
COMMIT_URL_TEMPLATES: dict[GitProvider, str] = {
    GitProvider.GITHUB: "{base_url}/{owner}/{repo}/commit/{commit_hash}",
    GitProvider.GITLAB: "{base_url}/{owner}/{repo}/-/commit/{commit_hash}",
    GitProvider.BITBUCKET: "{base_url}/{owner}/{repo}/commits/{commit_hash}",
}

PR_URL_TEMPLATES: dict[GitProvider, str] = {
    GitProvider.GITHUB: "{base_url}/{owner}/{repo}/pull/{pr_number}",
    GitProvider.GITLAB: "{base_url}/{owner}/{repo}/-/merge_requests/{pr_number}",
    GitProvider.BITBUCKET: "{base_url}/{owner}/{repo}/pull-requests/{pr_number}",
}


def build_commit_url(
    provider: GitProvider | str,
    owner: str,
    repo: str,
    commit_hash: str,
    base_url: str | None = None,
) -> str:
    """Build a commit URL for the given provider.

    Args:
        provider: The git provider (github, gitlab, bitbucket).
        owner: Repository owner or organization.
        repo: Repository name.
        commit_hash: The git commit SHA.
        base_url: Optional custom base URL for self-hosted instances.

    Returns:
        The full commit URL.
    """
    if isinstance(provider, str):
        provider = GitProvider(provider)
    base = (base_url or DEFAULT_BASE_URLS[provider]).rstrip("/")
    template = COMMIT_URL_TEMPLATES[provider]
    return template.format(
        base_url=base,
        owner=owner,
        repo=repo,
        commit_hash=commit_hash,
    )


def build_pr_url(
    provider: GitProvider | str,
    owner: str,
    repo: str,
    pr_number: int,
    base_url: str | None = None,
) -> str:
    """Build a PR/MR URL for the given provider.

    Args:
        provider: The git provider (github, gitlab, bitbucket).
        owner: Repository owner or organization.
        repo: Repository name.
        pr_number: The PR/MR number.
        base_url: Optional custom base URL for self-hosted instances.

    Returns:
        The full PR/MR URL.
    """
    if isinstance(provider, str):
        provider = GitProvider(provider)
    base = (base_url or DEFAULT_BASE_URLS[provider]).rstrip("/")
    template = PR_URL_TEMPLATES[provider]
    return template.format(
        base_url=base,
        owner=owner,
        repo=repo,
        pr_number=pr_number,
    )


def build_best_link(
    provider: GitProvider | str,
    owner: str,
    repo: str,
    commit_hash: str,
    pr_number: int | None = None,
    base_url: str | None = None,
) -> str:
    """Return PR URL if available, otherwise commit URL.

    This is a convenience function that prefers linking to the PR when
    available, as PRs typically provide more context than individual commits.

    Args:
        provider: The git provider (github, gitlab, bitbucket).
        owner: Repository owner or organization.
        repo: Repository name.
        commit_hash: The git commit SHA.
        pr_number: Optional PR/MR number (if available).
        base_url: Optional custom base URL for self-hosted instances.

    Returns:
        The PR URL if pr_number is provided, otherwise the commit URL.
    """
    if pr_number is not None:
        return build_pr_url(provider, owner, repo, pr_number, base_url)
    return build_commit_url(provider, owner, repo, commit_hash, base_url)
