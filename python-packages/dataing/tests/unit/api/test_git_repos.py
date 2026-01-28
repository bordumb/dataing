"""Unit tests for Git repository API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from dataing.entrypoints.api.routes.git_repos import (
    CodeChangeListResponse,
    CodeChangeResponse,
    ConnectGitRepoRequest,
    GitRepoListResponse,
    GitRepoResponse,
    SyncTriggerResponse,
    UpdateGitRepoRequest,
    _to_code_change_response,
    _to_repo_response,
)


class TestPydanticSchemas:
    """Test Pydantic request/response schemas."""

    def test_connect_git_repo_request_valid(self) -> None:
        """Test ConnectGitRepoRequest with valid data."""
        data = ConnectGitRepoRequest(
            name="my-repo",
            url="https://github.com/owner/repo",
            provider="github",
            access_token="ghp_test_token",
            default_branch="main",
            tracked_paths=["models/", "dbt/"],
        )
        assert data.name == "my-repo"
        assert data.provider == "github"
        assert data.default_branch == "main"
        assert len(data.tracked_paths) == 2

    def test_connect_git_repo_request_minimal(self) -> None:
        """Test ConnectGitRepoRequest with only required fields."""
        data = ConnectGitRepoRequest(
            name="repo",
            url="https://github.com/owner/repo",
            provider="github",
        )
        assert data.name == "repo"
        assert data.access_token is None
        assert data.tracked_paths is None
        assert data.default_branch == "main"  # Default value

    def test_connect_git_repo_request_invalid_provider(self) -> None:
        """Test ConnectGitRepoRequest rejects invalid provider."""
        with pytest.raises(ValueError):
            ConnectGitRepoRequest(
                name="repo",
                url="https://example.com/repo",
                provider="mercurial",  # Invalid
            )

    def test_connect_git_repo_request_gitlab_provider(self) -> None:
        """Test ConnectGitRepoRequest accepts gitlab provider."""
        data = ConnectGitRepoRequest(
            name="repo",
            url="https://gitlab.com/owner/repo",
            provider="gitlab",
        )
        assert data.provider == "gitlab"

    def test_connect_git_repo_request_bitbucket_provider(self) -> None:
        """Test ConnectGitRepoRequest accepts bitbucket provider."""
        data = ConnectGitRepoRequest(
            name="repo",
            url="https://bitbucket.org/owner/repo",
            provider="bitbucket",
        )
        assert data.provider == "bitbucket"

    def test_update_git_repo_request_valid(self) -> None:
        """Test UpdateGitRepoRequest with valid data."""
        data = UpdateGitRepoRequest(
            name="new-name",
            tracked_paths=["src/"],
            default_branch="develop",
        )
        assert data.name == "new-name"
        assert data.default_branch == "develop"

    def test_update_git_repo_request_all_none(self) -> None:
        """Test UpdateGitRepoRequest with no fields set."""
        data = UpdateGitRepoRequest()
        assert data.name is None
        assert data.tracked_paths is None
        assert data.default_branch is None

    def test_git_repo_response_fields(self) -> None:
        """Test GitRepoResponse has expected fields."""
        data = GitRepoResponse(
            id="123",
            name="test-repo",
            url="https://github.com/owner/repo",
            provider="github",
            tracked_paths=["models/"],
            default_branch="main",
            last_sync_at=datetime.now(UTC),
            sync_status="synced",
            sync_error=None,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        assert data.id == "123"
        assert data.sync_status == "synced"
        assert data.sync_error is None

    def test_git_repo_list_response(self) -> None:
        """Test GitRepoListResponse structure."""
        repos = [
            GitRepoResponse(
                id="1",
                name="repo-1",
                url="https://github.com/owner/repo1",
                provider="github",
                tracked_paths=None,
                default_branch="main",
                last_sync_at=None,
                sync_status="pending",
                sync_error=None,
                created_at=datetime.now(UTC),
                updated_at=None,
            ),
            GitRepoResponse(
                id="2",
                name="repo-2",
                url="https://github.com/owner/repo2",
                provider="github",
                tracked_paths=None,
                default_branch="main",
                last_sync_at=None,
                sync_status="synced",
                sync_error=None,
                created_at=datetime.now(UTC),
                updated_at=None,
            ),
        ]
        data = GitRepoListResponse(items=repos, total=2)
        assert len(data.items) == 2
        assert data.total == 2

    def test_code_change_response_fields(self) -> None:
        """Test CodeChangeResponse has expected fields."""
        data = CodeChangeResponse(
            id="abc123",
            repo_id="repo-1",
            commit_hash="abc123def456",
            author_name="Test Author",
            author_email="test@example.com",
            message="Fix bug",
            committed_at=datetime.now(UTC),
            affected_assets=[{"name": "orders", "type": "table"}],
            files_changed=["file.sql"],
            created_at=datetime.now(UTC),
        )
        assert data.commit_hash == "abc123def456"
        assert len(data.affected_assets) == 1
        assert data.affected_assets[0]["name"] == "orders"

    def test_code_change_list_response(self) -> None:
        """Test CodeChangeListResponse structure."""
        changes = [
            CodeChangeResponse(
                id="1",
                repo_id="repo-1",
                commit_hash="abc123",
                author_name=None,
                author_email=None,
                message="Commit 1",
                committed_at=None,
                affected_assets=[],
                files_changed=None,
                created_at=datetime.now(UTC),
            ),
        ]
        data = CodeChangeListResponse(items=changes, total=1)
        assert len(data.items) == 1
        assert data.total == 1

    def test_sync_trigger_response(self) -> None:
        """Test SyncTriggerResponse structure."""
        data = SyncTriggerResponse(
            message="Sync started",
            sync_status="syncing",
        )
        assert data.message == "Sync started"
        assert data.sync_status == "syncing"


class TestHelperFunctions:
    """Test helper functions for converting database rows to responses."""

    def test_to_repo_response_basic(self) -> None:
        """Test _to_repo_response with basic data."""
        row: dict[str, Any] = {
            "id": uuid4(),
            "name": "test-repo",
            "url": "https://github.com/owner/repo",
            "provider": "github",
            "tracked_paths": ["models/"],
            "default_branch": "main",
            "last_sync_at": datetime.now(UTC),
            "sync_status": "synced",
            "sync_error": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }

        response = _to_repo_response(row)

        assert response.name == "test-repo"
        assert response.provider == "github"
        assert response.tracked_paths == ["models/"]
        assert response.sync_status == "synced"

    def test_to_repo_response_defaults(self) -> None:
        """Test _to_repo_response with missing optional fields."""
        row: dict[str, Any] = {
            "id": uuid4(),
            "name": "test-repo",
            "url": "https://github.com/owner/repo",
            "provider": "github",
            "created_at": datetime.now(UTC),
        }

        response = _to_repo_response(row)

        assert response.default_branch == "main"
        assert response.sync_status == "pending"
        assert response.tracked_paths is None

    def test_to_repo_response_never_contains_access_token(self) -> None:
        """Test that _to_repo_response never includes access_token_encrypted."""
        row: dict[str, Any] = {
            "id": uuid4(),
            "name": "test-repo",
            "url": "https://github.com/owner/repo",
            "provider": "github",
            "access_token_encrypted": "super_secret_token",  # Should not appear in response
            "created_at": datetime.now(UTC),
        }

        response = _to_repo_response(row)

        # Verify response doesn't have access_token field
        response_dict = response.model_dump()
        assert "access_token" not in response_dict
        assert "access_token_encrypted" not in response_dict

    def test_to_code_change_response_basic(self) -> None:
        """Test _to_code_change_response with basic data."""
        row: dict[str, Any] = {
            "id": uuid4(),
            "repo_id": uuid4(),
            "commit_hash": "abc123",
            "author_name": "Test Author",
            "author_email": "test@example.com",
            "message": "Test commit",
            "committed_at": datetime.now(UTC),
            "affected_assets": [{"name": "orders", "type": "table"}],
            "files_changed": ["file.sql"],
            "created_at": datetime.now(UTC),
        }

        response = _to_code_change_response(row)

        assert response.commit_hash == "abc123"
        assert response.author_name == "Test Author"
        assert len(response.affected_assets) == 1

    def test_to_code_change_response_json_string_assets(self) -> None:
        """Test _to_code_change_response with JSON string affected_assets."""
        import json

        assets = [{"name": "orders", "type": "table"}]
        row: dict[str, Any] = {
            "id": uuid4(),
            "repo_id": uuid4(),
            "commit_hash": "abc123",
            "affected_assets": json.dumps(assets),  # JSON string instead of list
            "created_at": datetime.now(UTC),
        }

        response = _to_code_change_response(row)

        # Should parse JSON string correctly
        assert response.affected_assets == assets

    def test_to_code_change_response_empty_assets(self) -> None:
        """Test _to_code_change_response with None/empty affected_assets."""
        row: dict[str, Any] = {
            "id": uuid4(),
            "repo_id": uuid4(),
            "commit_hash": "abc123",
            "affected_assets": None,
            "created_at": datetime.now(UTC),
        }

        response = _to_code_change_response(row)

        assert response.affected_assets == []

    def test_to_code_change_response_defaults(self) -> None:
        """Test _to_code_change_response with missing optional fields."""
        row: dict[str, Any] = {
            "id": uuid4(),
            "repo_id": uuid4(),
            "commit_hash": "abc123",
            "created_at": datetime.now(UTC),
        }

        response = _to_code_change_response(row)

        assert response.author_name is None
        assert response.author_email is None
        assert response.message is None
        assert response.committed_at is None
        assert response.files_changed is None


class TestResponseNeverContainsSecrets:
    """Test that response schemas never expose sensitive data."""

    def test_git_repo_response_schema_excludes_token(self) -> None:
        """Verify GitRepoResponse schema doesn't have token fields."""
        fields = GitRepoResponse.model_fields
        assert "access_token" not in fields
        assert "access_token_encrypted" not in fields

    def test_connect_git_repo_request_has_token(self) -> None:
        """Verify ConnectGitRepoRequest accepts token for input."""
        # This is expected - we accept token in requests but never return it
        fields = ConnectGitRepoRequest.model_fields
        assert "access_token" in fields

    def test_update_git_repo_request_no_token(self) -> None:
        """Verify UpdateGitRepoRequest doesn't allow updating token."""
        # Token updates should require a separate secure endpoint
        fields = UpdateGitRepoRequest.model_fields
        assert "access_token" not in fields


class TestValidation:
    """Test request validation."""

    def test_connect_git_repo_request_name_min_length(self) -> None:
        """Test ConnectGitRepoRequest enforces minimum name length."""
        with pytest.raises(ValueError):
            ConnectGitRepoRequest(
                name="",  # Empty name
                url="https://github.com/owner/repo",
                provider="github",
            )

    def test_connect_git_repo_request_url_min_length(self) -> None:
        """Test ConnectGitRepoRequest enforces minimum URL length."""
        with pytest.raises(ValueError):
            ConnectGitRepoRequest(
                name="repo",
                url="",  # Empty URL
                provider="github",
            )

    def test_update_git_repo_request_name_min_length(self) -> None:
        """Test UpdateGitRepoRequest enforces minimum name length when provided."""
        with pytest.raises(ValueError):
            UpdateGitRepoRequest(name="")  # Empty name
