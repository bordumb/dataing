"""Unit tests for GitSyncService."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from dataing.adapters.git.provider import GitCommit
from dataing.adapters.git.sync import GitSyncService, _extract_commit_assets


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock AppDatabase."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_provider() -> AsyncMock:
    """Create a mock GitProvider."""
    provider = AsyncMock()
    return provider


@pytest.fixture
def sync_service(mock_db: AsyncMock, mock_provider: AsyncMock) -> GitSyncService:
    """Create a GitSyncService with mocked dependencies."""
    return GitSyncService(db=mock_db, providers={"github": mock_provider})


@pytest.fixture
def sample_repo() -> dict[str, Any]:
    """Create a sample repository record."""
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "name": "test-repo",
        "url": "https://github.com/owner/repo",
        "provider": "github",
        "access_token_encrypted": "test_token",
        "tracked_paths": None,
        "default_branch": "main",
        "sync_status": "pending",
    }


@pytest.fixture
def sample_commit() -> GitCommit:
    """Create a sample GitCommit."""
    return GitCommit(
        hash="abc123",
        author_name="Test Author",
        author_email="test@example.com",
        message="Test commit",
        committed_at=datetime.now(UTC),
        files_changed=["models/test.sql"],
        raw_diff="+SELECT * FROM {{ ref('orders') }}",
    )


class TestSyncRepository:
    """Tests for sync_repository method."""

    async def test_first_sync(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        mock_provider: AsyncMock,
        sample_repo: dict[str, Any],
        sample_commit: GitCommit,
    ) -> None:
        """Test first-time sync with no existing commits."""
        repo_id = sample_repo["id"]
        tenant_id = sample_repo["tenant_id"]

        # Setup mocks
        mock_db.get_git_repository.return_value = sample_repo
        mock_db.get_latest_commit_hash.return_value = None
        mock_db.bulk_create_code_changes.return_value = 1
        mock_provider.fetch_commits.return_value = [sample_commit]

        # Execute
        result = await sync_service.sync_repository(repo_id, tenant_id)

        # Verify
        assert result == 1
        mock_db.update_git_repo_sync_status.assert_any_call(repo_id, "syncing")
        mock_db.bulk_create_code_changes.assert_called_once()
        mock_provider.fetch_commits.assert_called_once_with(
            repo_url=sample_repo["url"],
            access_token=sample_repo["access_token_encrypted"],
            since_hash=None,
            branch="main",
            tracked_paths=None,
        )

    async def test_incremental_sync(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        mock_provider: AsyncMock,
        sample_repo: dict[str, Any],
        sample_commit: GitCommit,
    ) -> None:
        """Test incremental sync with existing commits."""
        repo_id = sample_repo["id"]
        tenant_id = sample_repo["tenant_id"]

        # Setup mocks - existing commit hash
        mock_db.get_git_repository.return_value = sample_repo
        mock_db.get_latest_commit_hash.return_value = "existing_hash"
        mock_db.bulk_create_code_changes.return_value = 1
        mock_provider.fetch_commits.return_value = [sample_commit]

        # Execute
        await sync_service.sync_repository(repo_id, tenant_id)

        # Verify incremental sync was used
        mock_provider.fetch_commits.assert_called_once()
        call_kwargs = mock_provider.fetch_commits.call_args[1]
        assert call_kwargs["since_hash"] == "existing_hash"

    async def test_updates_status_to_syncing(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        mock_provider: AsyncMock,
        sample_repo: dict[str, Any],
    ) -> None:
        """Test that status is set to 'syncing' at start."""
        repo_id = sample_repo["id"]
        tenant_id = sample_repo["tenant_id"]

        mock_db.get_git_repository.return_value = sample_repo
        mock_db.get_latest_commit_hash.return_value = None
        mock_provider.fetch_commits.return_value = []

        await sync_service.sync_repository(repo_id, tenant_id)

        # First call should be 'syncing'
        first_call = mock_db.update_git_repo_sync_status.call_args_list[0]
        assert first_call[0] == (repo_id, "syncing")

    async def test_updates_status_to_synced(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        mock_provider: AsyncMock,
        sample_repo: dict[str, Any],
        sample_commit: GitCommit,
    ) -> None:
        """Test that status is set to 'synced' on success."""
        repo_id = sample_repo["id"]
        tenant_id = sample_repo["tenant_id"]

        mock_db.get_git_repository.return_value = sample_repo
        mock_db.get_latest_commit_hash.return_value = None
        mock_db.bulk_create_code_changes.return_value = 1
        mock_provider.fetch_commits.return_value = [sample_commit]

        await sync_service.sync_repository(repo_id, tenant_id)

        # Last call should be 'synced' with timestamp
        last_call = mock_db.update_git_repo_sync_status.call_args_list[-1]
        assert last_call[0][0] == repo_id
        assert last_call[0][1] == "synced"
        assert "last_sync_at" in last_call[1]

    async def test_updates_status_to_error_on_failure(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        mock_provider: AsyncMock,
        sample_repo: dict[str, Any],
    ) -> None:
        """Test that status is set to 'error' on failure."""
        repo_id = sample_repo["id"]
        tenant_id = sample_repo["tenant_id"]

        mock_db.get_git_repository.return_value = sample_repo
        mock_db.get_latest_commit_hash.return_value = None
        mock_provider.fetch_commits.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await sync_service.sync_repository(repo_id, tenant_id)

        # Should have updated to error status
        last_call = mock_db.update_git_repo_sync_status.call_args_list[-1]
        assert last_call[0][0] == repo_id
        assert last_call[0][1] == "error"
        assert "error" in last_call[1]
        assert "API error" in last_call[1]["error"]

    async def test_sets_last_sync_at(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        mock_provider: AsyncMock,
        sample_repo: dict[str, Any],
    ) -> None:
        """Test that last_sync_at is set on success."""
        repo_id = sample_repo["id"]
        tenant_id = sample_repo["tenant_id"]

        mock_db.get_git_repository.return_value = sample_repo
        mock_db.get_latest_commit_hash.return_value = None
        mock_provider.fetch_commits.return_value = []

        await sync_service.sync_repository(repo_id, tenant_id)

        # Should have set last_sync_at
        last_call = mock_db.update_git_repo_sync_status.call_args_list[-1]
        assert "last_sync_at" in last_call[1]
        assert isinstance(last_call[1]["last_sync_at"], datetime)

    async def test_repo_not_found(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
    ) -> None:
        """Test error when repository not found."""
        mock_db.get_git_repository.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await sync_service.sync_repository(uuid4(), uuid4())

    async def test_populates_affected_assets(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        mock_provider: AsyncMock,
        sample_repo: dict[str, Any],
    ) -> None:
        """Test that affected_assets are extracted and stored."""
        repo_id = sample_repo["id"]
        tenant_id = sample_repo["tenant_id"]

        commit = GitCommit(
            hash="abc123",
            author_name="Test",
            message="Add dbt model",
            files_changed=["models/orders.sql"],
            raw_diff="+SELECT * FROM {{ ref('customers') }}",
        )

        mock_db.get_git_repository.return_value = sample_repo
        mock_db.get_latest_commit_hash.return_value = None
        mock_db.bulk_create_code_changes.return_value = 1
        mock_provider.fetch_commits.return_value = [commit]

        await sync_service.sync_repository(repo_id, tenant_id)

        # Check that affected_assets were passed to bulk_create
        call_args = mock_db.bulk_create_code_changes.call_args[0][0]
        assert len(call_args) == 1
        assert "affected_assets" in call_args[0]
        # Should have extracted the dbt ref
        assets = call_args[0]["affected_assets"]
        assert any(a["name"] == "customers" for a in assets)

    async def test_unsupported_provider(
        self,
        sync_service: GitSyncService,
        mock_db: AsyncMock,
        sample_repo: dict[str, Any],
    ) -> None:
        """Test error for unsupported provider."""
        sample_repo["provider"] = "unsupported_provider"
        mock_db.get_git_repository.return_value = sample_repo

        with pytest.raises(ValueError, match="Unsupported git provider"):
            await sync_service.sync_repository(sample_repo["id"], sample_repo["tenant_id"])


class TestExtractCommitAssets:
    """Tests for _extract_commit_assets helper."""

    def test_extracts_from_sql_file(self) -> None:
        """Test asset extraction from SQL file."""
        commit = GitCommit(
            hash="abc123",
            files_changed=["models/staging/stg_orders.sql"],
            raw_diff="+SELECT * FROM {{ ref('orders') }}",
        )

        assets = _extract_commit_assets(commit)
        assert any(a["name"] == "orders" for a in assets)

    def test_deduplicates_assets(self) -> None:
        """Test that duplicate assets are removed."""
        commit = GitCommit(
            hash="abc123",
            files_changed=["a.sql", "b.sql"],
            raw_diff="+SELECT * FROM orders\n+SELECT * FROM orders",
        )

        assets = _extract_commit_assets(commit)
        names = [a["name"] for a in assets]
        assert names.count("orders") == 1

    def test_handles_none_diff(self) -> None:
        """Test handling of commits with no diff."""
        commit = GitCommit(
            hash="abc123",
            files_changed=["file.sql"],
            raw_diff=None,
        )

        assets = _extract_commit_assets(commit)
        assert assets == []
