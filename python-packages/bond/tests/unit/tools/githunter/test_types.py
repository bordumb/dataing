"""Tests for GitHunter types."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from bond.tools.githunter._types import (
    AuthorProfile,
    BlameResult,
    FileExpert,
    PRDiscussion,
)


class TestAuthorProfile:
    """Tests for AuthorProfile dataclass."""

    def test_author_profile_creation(self) -> None:
        """Test AuthorProfile can be created with required fields."""
        author = AuthorProfile(
            git_email="test@example.com",
            git_name="Test User",
        )
        assert author.git_email == "test@example.com"
        assert author.git_name == "Test User"
        assert author.github_username is None
        assert author.github_avatar_url is None

    def test_author_profile_with_github_data(self) -> None:
        """Test AuthorProfile with GitHub enrichment data."""
        author = AuthorProfile(
            git_email="test@example.com",
            git_name="Test User",
            github_username="testuser",
            github_avatar_url="https://github.com/testuser.png",
        )
        assert author.github_username == "testuser"
        assert author.github_avatar_url == "https://github.com/testuser.png"

    def test_author_profile_is_frozen(self) -> None:
        """Test AuthorProfile is immutable."""
        author = AuthorProfile(
            git_email="test@example.com",
            git_name="Test User",
        )
        with pytest.raises(FrozenInstanceError):
            author.git_email = "new@example.com"


class TestBlameResult:
    """Tests for BlameResult dataclass."""

    def test_blame_result_creation(self) -> None:
        """Test BlameResult can be created with required fields."""
        author = AuthorProfile(git_email="test@example.com", git_name="Test")
        result = BlameResult(
            line_no=42,
            content="  some code here",
            author=author,
            commit_hash="abc123",
            commit_date=datetime(2024, 1, 15, tzinfo=UTC),
            commit_message="Fix bug",
        )
        assert result.line_no == 42
        assert result.content == "  some code here"
        assert result.author == author
        assert result.commit_hash == "abc123"
        assert result.is_boundary is False

    def test_blame_result_with_boundary(self) -> None:
        """Test BlameResult with boundary commit (shallow clone)."""
        author = AuthorProfile(git_email="test@example.com", git_name="Test")
        result = BlameResult(
            line_no=1,
            content="first line",
            author=author,
            commit_hash="def456",
            commit_date=datetime(2023, 6, 1, tzinfo=UTC),
            commit_message="Initial commit",
            is_boundary=True,
        )
        assert result.is_boundary is True

    def test_blame_result_is_frozen(self) -> None:
        """Test BlameResult is immutable."""
        author = AuthorProfile(git_email="test@example.com", git_name="Test")
        result = BlameResult(
            line_no=1,
            content="code",
            author=author,
            commit_hash="abc",
            commit_date=datetime.now(tz=UTC),
            commit_message="msg",
        )
        with pytest.raises(FrozenInstanceError):
            result.line_no = 99


class TestFileExpert:
    """Tests for FileExpert dataclass."""

    def test_file_expert_creation(self) -> None:
        """Test FileExpert can be created."""
        author = AuthorProfile(git_email="expert@example.com", git_name="Expert")
        expert = FileExpert(
            author=author,
            commit_count=25,
            last_commit_date=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert expert.author == author
        assert expert.commit_count == 25
        assert expert.last_commit_date == datetime(2024, 1, 1, tzinfo=UTC)

    def test_file_expert_is_frozen(self) -> None:
        """Test FileExpert is immutable."""
        author = AuthorProfile(git_email="test@example.com", git_name="Test")
        expert = FileExpert(
            author=author,
            commit_count=10,
            last_commit_date=datetime.now(tz=UTC),
        )
        with pytest.raises(FrozenInstanceError):
            expert.commit_count = 100


class TestPRDiscussion:
    """Tests for PRDiscussion dataclass."""

    def test_pr_discussion_creation(self) -> None:
        """Test PRDiscussion can be created."""
        pr = PRDiscussion(
            pr_number=123,
            title="Add new feature",
            body="This PR adds...",
            url="https://github.com/owner/repo/pull/123",
            issue_comments=("LGTM", "Please add tests"),
        )
        assert pr.pr_number == 123
        assert pr.title == "Add new feature"
        assert pr.body == "This PR adds..."
        assert pr.url == "https://github.com/owner/repo/pull/123"
        assert pr.issue_comments == ("LGTM", "Please add tests")

    def test_pr_discussion_empty_comments(self) -> None:
        """Test PRDiscussion with no comments."""
        pr = PRDiscussion(
            pr_number=1,
            title="Title",
            body="Body",
            url="https://github.com/owner/repo/pull/1",
            issue_comments=(),
        )
        assert pr.issue_comments == ()

    def test_pr_discussion_is_frozen(self) -> None:
        """Test PRDiscussion is immutable."""
        pr = PRDiscussion(
            pr_number=1,
            title="Title",
            body="Body",
            url="https://github.com/owner/repo/pull/1",
            issue_comments=(),
        )
        with pytest.raises(FrozenInstanceError):
            pr.pr_number = 999
