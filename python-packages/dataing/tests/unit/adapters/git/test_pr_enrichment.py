"""Unit tests for PR enrichment service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dataing.adapters.git.pr_enrichment import PREnrichmentService, PRMetadata


class TestPREnrichmentService:
    """Tests for PREnrichmentService."""

    @pytest.fixture
    def repo_path(self, tmp_path: Path) -> Path:
        """Create a mock repo path."""
        return tmp_path / "repo"

    @pytest.fixture
    def service(self, repo_path: Path) -> PREnrichmentService:
        """Create a service instance with mocked adapters."""
        return PREnrichmentService(repo_path=repo_path, github_token="test-token")

    async def test_get_pr_for_commit_no_repo_path(self) -> None:
        """Should return None when no repo_path is configured."""
        service = PREnrichmentService(repo_path=None)
        result = await service.get_pr_for_commit("abc123")
        assert result is None

    async def test_get_pr_for_commit_not_found(self, service: PREnrichmentService) -> None:
        """Should return None when no PR is found for commit."""
        mock_githunter = MagicMock()
        mock_githunter.find_pr_discussion.return_value = None

        with patch.object(service, "_githunter", mock_githunter):
            result = await service.get_pr_for_commit("abc123")

        assert result is None
        mock_githunter.find_pr_discussion.assert_called_once()

    async def test_get_pr_for_commit_found_local_only(self, service: PREnrichmentService) -> None:
        """Should return PR metadata from local git when GitHub API not used."""
        mock_pr_discussion = MagicMock()
        mock_pr_discussion.number = 42
        mock_pr_discussion.url = "https://github.com/owner/repo/pull/42"
        mock_pr_discussion.title = "Fix null handling"

        mock_githunter = MagicMock()
        mock_githunter.find_pr_discussion.return_value = mock_pr_discussion

        # No owner/repo provided, so GitHub API won't be called
        service_no_token = PREnrichmentService(repo_path=service.repo_path, github_token=None)

        with patch.object(service_no_token, "_githunter", mock_githunter):
            result = await service_no_token.get_pr_for_commit("abc123")

        assert result is not None
        assert result.pr_number == 42
        assert result.pr_url == "https://github.com/owner/repo/pull/42"
        assert result.pr_title == "Fix null handling"
        assert result.pr_author == ""  # Not available from git alone
        assert result.pr_merged_at is None

    async def test_get_pr_for_commit_with_github_api(self, service: PREnrichmentService) -> None:
        """Should return full PR metadata when GitHub API is available."""
        mock_pr_discussion = MagicMock()
        mock_pr_discussion.number = 42

        mock_githunter = MagicMock()
        mock_githunter.find_pr_discussion.return_value = mock_pr_discussion

        merged_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_pr = MagicMock()
        mock_pr.number = 42
        mock_pr.url = "https://github.com/owner/repo/pull/42"
        mock_pr.title = "Fix null handling in orders"
        mock_pr.author = MagicMock()
        mock_pr.author.login = "developer123"
        mock_pr.merged_at = merged_at

        mock_github = MagicMock()
        mock_github.get_pr.return_value = mock_pr

        with (
            patch.object(service, "_githunter", mock_githunter),
            patch.object(service, "_github", mock_github),
        ):
            result = await service.get_pr_for_commit("abc123", owner="owner", repo="repo")

        assert result is not None
        assert result.pr_number == 42
        assert result.pr_url == "https://github.com/owner/repo/pull/42"
        assert result.pr_title == "Fix null handling in orders"
        assert result.pr_author == "developer123"
        assert result.pr_merged_at == merged_at

        mock_github.get_pr.assert_called_once_with(owner="owner", repo="repo", number=42)

    async def test_get_pr_for_commit_github_api_fails_gracefully(
        self, service: PREnrichmentService
    ) -> None:
        """Should fall back to local data when GitHub API fails."""
        mock_pr_discussion = MagicMock()
        mock_pr_discussion.number = 42
        mock_pr_discussion.url = "https://github.com/owner/repo/pull/42"
        mock_pr_discussion.title = "Fix null handling"

        mock_githunter = MagicMock()
        mock_githunter.find_pr_discussion.return_value = mock_pr_discussion

        mock_github = MagicMock()
        mock_github.get_pr.side_effect = Exception("API rate limited")

        with (
            patch.object(service, "_githunter", mock_githunter),
            patch.object(service, "_github", mock_github),
        ):
            result = await service.get_pr_for_commit("abc123", owner="owner", repo="repo")

        # Should fall back to local data
        assert result is not None
        assert result.pr_number == 42
        assert result.pr_title == "Fix null handling"
        assert result.pr_author == ""  # GitHub API failed

    async def test_enrich_commits_batch(self, service: PREnrichmentService) -> None:
        """Should enrich multiple commits in batch."""
        mock_pr_discussion_1 = MagicMock()
        mock_pr_discussion_1.number = 42
        mock_pr_discussion_1.url = "https://github.com/owner/repo/pull/42"
        mock_pr_discussion_1.title = "PR 42"

        mock_pr_discussion_2 = MagicMock()
        mock_pr_discussion_2.number = 43
        mock_pr_discussion_2.url = "https://github.com/owner/repo/pull/43"
        mock_pr_discussion_2.title = "PR 43"

        mock_githunter = MagicMock()
        # First commit has PR, second doesn't, third has PR
        mock_githunter.find_pr_discussion.side_effect = [
            mock_pr_discussion_1,
            None,
            mock_pr_discussion_2,
        ]

        service_no_token = PREnrichmentService(repo_path=service.repo_path, github_token=None)

        with patch.object(service_no_token, "_githunter", mock_githunter):
            results = await service_no_token.enrich_commits(["commit1", "commit2", "commit3"])

        assert len(results) == 2
        assert "commit1" in results
        assert "commit2" not in results
        assert "commit3" in results
        assert results["commit1"].pr_number == 42
        assert results["commit3"].pr_number == 43

    async def test_enrich_commits_handles_errors(self, service: PREnrichmentService) -> None:
        """Should continue processing when individual commits fail."""
        mock_pr_discussion = MagicMock()
        mock_pr_discussion.number = 42
        mock_pr_discussion.url = "https://github.com/owner/repo/pull/42"
        mock_pr_discussion.title = "PR 42"

        mock_githunter = MagicMock()
        # First commit raises, second succeeds
        mock_githunter.find_pr_discussion.side_effect = [
            Exception("Git error"),
            mock_pr_discussion,
        ]

        service_no_token = PREnrichmentService(repo_path=service.repo_path, github_token=None)

        with patch.object(service_no_token, "_githunter", mock_githunter):
            results = await service_no_token.enrich_commits(["commit1", "commit2"])

        # First commit failed, but second should still succeed
        assert len(results) == 1
        assert "commit2" in results
        assert results["commit2"].pr_number == 42


class TestPRMetadata:
    """Tests for PRMetadata dataclass."""

    def test_pr_metadata_creation(self) -> None:
        """Should create PRMetadata with all fields."""
        merged_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        metadata = PRMetadata(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_title="Fix null handling",
            pr_author="developer123",
            pr_merged_at=merged_at,
        )

        assert metadata.pr_number == 42
        assert metadata.pr_url == "https://github.com/owner/repo/pull/42"
        assert metadata.pr_title == "Fix null handling"
        assert metadata.pr_author == "developer123"
        assert metadata.pr_merged_at == merged_at

    def test_pr_metadata_optional_merged_at(self) -> None:
        """Should allow None for pr_merged_at."""
        metadata = PRMetadata(
            pr_number=42,
            pr_url="https://github.com/owner/repo/pull/42",
            pr_title="Fix null handling",
            pr_author="developer123",
            pr_merged_at=None,
        )

        assert metadata.pr_merged_at is None
