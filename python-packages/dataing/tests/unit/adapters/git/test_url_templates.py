"""Unit tests for URL template rendering."""

from __future__ import annotations

import pytest

from dataing.adapters.git.url_templates import (
    GitProvider,
    build_best_link,
    build_commit_url,
    build_pr_url,
)


class TestBuildCommitUrl:
    """Tests for build_commit_url function."""

    def test_github_commit_url(self) -> None:
        """Should generate correct GitHub commit URL."""
        url = build_commit_url(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
        )
        assert url == "https://github.com/acme/data-pipeline/commit/abc123def456"

    def test_gitlab_commit_url(self) -> None:
        """Should generate correct GitLab commit URL."""
        url = build_commit_url(
            provider=GitProvider.GITLAB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
        )
        assert url == "https://gitlab.com/acme/data-pipeline/-/commit/abc123def456"

    def test_bitbucket_commit_url(self) -> None:
        """Should generate correct Bitbucket commit URL."""
        url = build_commit_url(
            provider=GitProvider.BITBUCKET,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
        )
        assert url == "https://bitbucket.org/acme/data-pipeline/commits/abc123def456"

    def test_github_commit_url_string_provider(self) -> None:
        """Should accept string provider name."""
        url = build_commit_url(
            provider="github",
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
        )
        assert url == "https://github.com/acme/data-pipeline/commit/abc123def456"

    def test_custom_base_url(self) -> None:
        """Should use custom base URL for self-hosted instances."""
        url = build_commit_url(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
            base_url="https://github.internal.company.com",
        )
        assert url == "https://github.internal.company.com/acme/data-pipeline/commit/abc123def456"

    def test_custom_base_url_trailing_slash(self) -> None:
        """Should handle trailing slash in custom base URL."""
        url = build_commit_url(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
            base_url="https://github.internal.company.com/",
        )
        assert url == "https://github.internal.company.com/acme/data-pipeline/commit/abc123def456"

    def test_invalid_provider_raises(self) -> None:
        """Should raise ValueError for invalid provider string."""
        with pytest.raises(ValueError, match="'invalid' is not a valid GitProvider"):
            build_commit_url(
                provider="invalid",
                owner="acme",
                repo="data-pipeline",
                commit_hash="abc123def456",
            )


class TestBuildPrUrl:
    """Tests for build_pr_url function."""

    def test_github_pr_url(self) -> None:
        """Should generate correct GitHub PR URL."""
        url = build_pr_url(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            pr_number=42,
        )
        assert url == "https://github.com/acme/data-pipeline/pull/42"

    def test_gitlab_mr_url(self) -> None:
        """Should generate correct GitLab merge request URL."""
        url = build_pr_url(
            provider=GitProvider.GITLAB,
            owner="acme",
            repo="data-pipeline",
            pr_number=42,
        )
        assert url == "https://gitlab.com/acme/data-pipeline/-/merge_requests/42"

    def test_bitbucket_pr_url(self) -> None:
        """Should generate correct Bitbucket pull request URL."""
        url = build_pr_url(
            provider=GitProvider.BITBUCKET,
            owner="acme",
            repo="data-pipeline",
            pr_number=42,
        )
        assert url == "https://bitbucket.org/acme/data-pipeline/pull-requests/42"

    def test_gitlab_mr_url_string_provider(self) -> None:
        """Should accept string provider name."""
        url = build_pr_url(
            provider="gitlab",
            owner="acme",
            repo="data-pipeline",
            pr_number=42,
        )
        assert url == "https://gitlab.com/acme/data-pipeline/-/merge_requests/42"

    def test_custom_base_url(self) -> None:
        """Should use custom base URL for self-hosted GitLab."""
        url = build_pr_url(
            provider=GitProvider.GITLAB,
            owner="acme",
            repo="data-pipeline",
            pr_number=42,
            base_url="https://gitlab.internal.company.com",
        )
        assert url == "https://gitlab.internal.company.com/acme/data-pipeline/-/merge_requests/42"


class TestBuildBestLink:
    """Tests for build_best_link function."""

    def test_returns_pr_url_when_pr_number_provided(self) -> None:
        """Should return PR URL when pr_number is provided."""
        url = build_best_link(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
            pr_number=42,
        )
        assert url == "https://github.com/acme/data-pipeline/pull/42"

    def test_returns_commit_url_when_no_pr_number(self) -> None:
        """Should return commit URL when pr_number is None."""
        url = build_best_link(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
            pr_number=None,
        )
        assert url == "https://github.com/acme/data-pipeline/commit/abc123def456"

    def test_returns_commit_url_by_default(self) -> None:
        """Should return commit URL when pr_number not provided."""
        url = build_best_link(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
        )
        assert url == "https://github.com/acme/data-pipeline/commit/abc123def456"

    def test_custom_base_url_with_pr(self) -> None:
        """Should use custom base URL for PR link."""
        url = build_best_link(
            provider=GitProvider.GITHUB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
            pr_number=42,
            base_url="https://github.enterprise.com",
        )
        assert url == "https://github.enterprise.com/acme/data-pipeline/pull/42"

    def test_custom_base_url_with_commit(self) -> None:
        """Should use custom base URL for commit link."""
        url = build_best_link(
            provider=GitProvider.GITLAB,
            owner="acme",
            repo="data-pipeline",
            commit_hash="abc123def456",
            base_url="https://gitlab.enterprise.com",
        )
        assert url == "https://gitlab.enterprise.com/acme/data-pipeline/-/commit/abc123def456"


class TestGitProvider:
    """Tests for GitProvider enum."""

    def test_provider_values(self) -> None:
        """Should have correct string values."""
        assert GitProvider.GITHUB.value == "github"
        assert GitProvider.GITLAB.value == "gitlab"
        assert GitProvider.BITBUCKET.value == "bitbucket"

    def test_provider_from_string(self) -> None:
        """Should create provider from string."""
        assert GitProvider("github") == GitProvider.GITHUB
        assert GitProvider("gitlab") == GitProvider.GITLAB
        assert GitProvider("bitbucket") == GitProvider.BITBUCKET
