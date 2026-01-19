"""Tests for GitHunter adapter."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from bond.tools.githunter._adapter import GitHunterAdapter
from bond.tools.githunter._exceptions import (
    BinaryFileError,
    FileNotFoundInRepoError,
    GitHubUnavailableError,
    LineOutOfRangeError,
    RateLimitedError,
    RepoNotFoundError,
)
from bond.tools.githunter._types import AuthorProfile


class TestBlameLine:
    """Tests for GitHunterAdapter.blame_line()."""

    @pytest.fixture
    def adapter(self) -> GitHunterAdapter:
        """Create adapter for testing."""
        return GitHunterAdapter(timeout=5)

    async def test_blame_line_happy_path(self, adapter: GitHunterAdapter) -> None:
        """Test blame_line returns correct result for valid input."""
        porcelain_output = """abc123def456789012345678901234567890ab12 1 1 1
author John Doe
author-mail <john@example.com>
author-time 1704067200
author-tz +0000
committer John Doe
committer-mail <john@example.com>
committer-time 1704067200
committer-tz +0000
summary Add feature
filename test.py
\tdef hello():
"""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(porcelain_output.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(adapter, "_get_head_sha", return_value="headsha123"):
                result = await adapter.blame_line(Path("/repo"), "test.py", 1)

        assert result.line_no == 1
        assert result.content == "def hello():"
        assert result.author.git_name == "John Doe"
        assert result.author.git_email == "john@example.com"
        assert result.commit_hash == "abc123def456789012345678901234567890ab12"
        assert result.commit_message == "Add feature"
        assert result.is_boundary is False

    async def test_blame_line_boundary_commit(self, adapter: GitHunterAdapter) -> None:
        """Test blame_line detects boundary commits (shallow clone)."""
        porcelain_output = """^abc123def456789012345678901234567890ab12 1 1 1
author John Doe
author-mail <john@example.com>
author-time 1704067200
boundary
summary Initial
filename test.py
\tinitial content
"""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(porcelain_output.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(adapter, "_get_head_sha", return_value="headsha123"):
                result = await adapter.blame_line(Path("/repo"), "test.py", 1)

        assert result.is_boundary is True
        assert result.commit_hash == "abc123def456789012345678901234567890ab12"

    async def test_blame_line_invalid_line_number(self, adapter: GitHunterAdapter) -> None:
        """Test blame_line raises LineOutOfRangeError for line < 1."""
        with pytest.raises(LineOutOfRangeError) as exc_info:
            await adapter.blame_line(Path("/repo"), "test.py", 0)
        assert exc_info.value.line_no == 0

    async def test_blame_line_file_not_found(self, adapter: GitHunterAdapter) -> None:
        """Test blame_line raises FileNotFoundInRepoError."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal: no such path 'missing.py'"))
        mock_proc.returncode = 128

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(adapter, "_get_head_sha", return_value="headsha123"):
                with pytest.raises(FileNotFoundInRepoError) as exc_info:
                    await adapter.blame_line(Path("/repo"), "missing.py", 1)

        assert exc_info.value.file_path == "missing.py"

    async def test_blame_line_out_of_range(self, adapter: GitHunterAdapter) -> None:
        """Test blame_line raises LineOutOfRangeError for invalid line."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal: invalid line 9999"))
        mock_proc.returncode = 128

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(adapter, "_get_head_sha", return_value="headsha123"):
                with pytest.raises(LineOutOfRangeError):
                    await adapter.blame_line(Path("/repo"), "test.py", 9999)

    async def test_blame_line_binary_file(self, adapter: GitHunterAdapter) -> None:
        """Test blame_line raises BinaryFileError for binary files."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"fatal: cannot run blame on binary file")
        )
        mock_proc.returncode = 128

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(adapter, "_get_head_sha", return_value="headsha123"):
                with pytest.raises(BinaryFileError) as exc_info:
                    await adapter.blame_line(Path("/repo"), "image.png", 1)

        assert exc_info.value.file_path == "image.png"

    async def test_blame_line_not_a_git_repo(self, adapter: GitHunterAdapter) -> None:
        """Test blame_line raises RepoNotFoundError for non-git directory."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal: not a git repository"))
        mock_proc.returncode = 128

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(adapter, "_get_head_sha", return_value="headsha123"):
                with pytest.raises(RepoNotFoundError):
                    await adapter.blame_line(Path("/not-a-repo"), "test.py", 1)


class TestFindPRDiscussion:
    """Tests for GitHunterAdapter.find_pr_discussion()."""

    @pytest.fixture
    def adapter(self) -> GitHunterAdapter:
        """Create adapter with mock GitHub token."""
        adapter = GitHunterAdapter(timeout=5)
        adapter._github_token = "fake-token"
        return adapter

    async def test_find_pr_no_token(self) -> None:
        """Test find_pr_discussion returns None without GITHUB_TOKEN."""
        adapter = GitHunterAdapter()
        adapter._github_token = None

        result = await adapter.find_pr_discussion(Path("/repo"), "abc123")

        assert result is None

    async def test_find_pr_not_github_repo(self, adapter: GitHunterAdapter) -> None:
        """Test find_pr_discussion returns None for non-GitHub repo."""
        with patch.object(adapter, "_get_github_repo", return_value=None):
            result = await adapter.find_pr_discussion(Path("/repo"), "abc123")

        assert result is None

    async def test_find_pr_happy_path(self, adapter: GitHunterAdapter) -> None:
        """Test find_pr_discussion returns PR data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-RateLimit-Remaining": "1000"}
        mock_response.json.return_value = [
            {
                "number": 42,
                "title": "Add feature",
                "body": "This PR adds...",
                "html_url": "https://github.com/owner/repo/pull/42",
            }
        ]

        mock_comments_response = MagicMock()
        mock_comments_response.status_code = 200
        mock_comments_response.headers = {"X-RateLimit-Remaining": "999"}
        mock_comments_response.json.return_value = [
            {"body": "LGTM!"},
            {"body": "Looks good"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[mock_response, mock_comments_response])

        with patch.object(adapter, "_get_github_repo", return_value=("owner", "repo")):
            with patch.object(adapter, "_get_http_client", return_value=mock_client):
                result = await adapter.find_pr_discussion(Path("/repo"), "abc123")

        assert result is not None
        assert result.pr_number == 42
        assert result.title == "Add feature"
        assert result.body == "This PR adds..."
        assert result.issue_comments == ("LGTM!", "Looks good")

    async def test_find_pr_no_pr_for_commit(self, adapter: GitHunterAdapter) -> None:
        """Test find_pr_discussion returns None when commit has no PR."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-RateLimit-Remaining": "1000"}
        mock_response.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_github_repo", return_value=("owner", "repo")):
            with patch.object(adapter, "_get_http_client", return_value=mock_client):
                result = await adapter.find_pr_discussion(Path("/repo"), "abc123")

        assert result is None

    async def test_find_pr_rate_limited(self, adapter: GitHunterAdapter) -> None:
        """Test find_pr_discussion raises RateLimitedError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(datetime.now(tz=UTC).timestamp()) + 3600),
        }
        mock_response.text = "API rate limit exceeded"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_github_repo", return_value=("owner", "repo")):
            with patch.object(adapter, "_get_http_client", return_value=mock_client):
                with pytest.raises(RateLimitedError):
                    await adapter.find_pr_discussion(Path("/repo"), "abc123")

    async def test_find_pr_timeout(self, adapter: GitHunterAdapter) -> None:
        """Test find_pr_discussion raises GitHubUnavailableError on timeout."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch.object(adapter, "_get_github_repo", return_value=("owner", "repo")):
            with patch.object(adapter, "_get_http_client", return_value=mock_client):
                with pytest.raises(GitHubUnavailableError):
                    await adapter.find_pr_discussion(Path("/repo"), "abc123")


class TestEnrichAuthor:
    """Tests for GitHunterAdapter.enrich_author()."""

    @pytest.fixture
    def adapter(self) -> GitHunterAdapter:
        """Create adapter with mock GitHub token."""
        adapter = GitHunterAdapter(timeout=5)
        adapter._github_token = "fake-token"
        return adapter

    async def test_enrich_no_token(self) -> None:
        """Test enrich_author returns unchanged author without token."""
        adapter = GitHunterAdapter()
        adapter._github_token = None

        author = AuthorProfile(git_email="test@example.com", git_name="Test")

        result = await adapter.enrich_author(author)

        assert result == author

    async def test_enrich_author_found(self, adapter: GitHunterAdapter) -> None:
        """Test enrich_author adds GitHub data when user found."""
        author = AuthorProfile(git_email="test@example.com", git_name="Test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-RateLimit-Remaining": "1000"}
        mock_response.json.return_value = {
            "total_count": 1,
            "items": [
                {
                    "login": "testuser",
                    "avatar_url": "https://github.com/testuser.png",
                }
            ],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_http_client", return_value=mock_client):
            result = await adapter.enrich_author(author)

        assert result.github_username == "testuser"
        assert result.github_avatar_url == "https://github.com/testuser.png"

    async def test_enrich_author_not_found(self, adapter: GitHunterAdapter) -> None:
        """Test enrich_author returns original when user not found."""
        author = AuthorProfile(git_email="unknown@example.com", git_name="Unknown")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-RateLimit-Remaining": "1000"}
        mock_response.json.return_value = {"total_count": 0, "items": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_http_client", return_value=mock_client):
            result = await adapter.enrich_author(author)

        assert result == author


class TestGetExpertForFile:
    """Tests for GitHunterAdapter.get_expert_for_file()."""

    @pytest.fixture
    def adapter(self) -> GitHunterAdapter:
        """Create adapter for testing."""
        return GitHunterAdapter(timeout=5)

    async def test_get_expert_happy_path(self, adapter: GitHunterAdapter) -> None:
        """Test get_expert_for_file returns ranked experts."""
        git_log_output = """alice@example.com|Alice Smith|aaa111|1704067200
bob@example.com|Bob Jones|bbb222|1704153600
alice@example.com|Alice Smith|ccc333|1704240000
alice@example.com|Alice Smith|ddd444|1704326400
bob@example.com|Bob Jones|eee555|1704412800
"""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(git_log_output.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter.get_expert_for_file(
                Path("/repo"), "test.py", window_days=90, limit=3
            )

        assert len(result) == 2
        # Alice has 3 commits, Bob has 2
        assert result[0].author.git_email == "alice@example.com"
        assert result[0].commit_count == 3
        assert result[1].author.git_email == "bob@example.com"
        assert result[1].commit_count == 2

    async def test_get_expert_respects_limit(self, adapter: GitHunterAdapter) -> None:
        """Test get_expert_for_file respects limit parameter."""
        git_log_output = """a@ex.com|A|aaa|1704067200
b@ex.com|B|bbb|1704067200
c@ex.com|C|ccc|1704067200
d@ex.com|D|ddd|1704067200
"""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(git_log_output.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter.get_expert_for_file(Path("/repo"), "test.py", limit=2)

        assert len(result) == 2

    async def test_get_expert_empty_history(self, adapter: GitHunterAdapter) -> None:
        """Test get_expert_for_file returns empty list for no commits."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter.get_expert_for_file(Path("/repo"), "newfile.py", limit=3)

        assert result == []

    async def test_get_expert_case_insensitive_email(self, adapter: GitHunterAdapter) -> None:
        """Test get_expert_for_file groups emails case-insensitively."""
        git_log_output = """Alice@Example.com|Alice|aaa|1704067200
alice@example.com|Alice Smith|bbb|1704153600
ALICE@EXAMPLE.COM|alice|ccc|1704240000
"""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(git_log_output.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter.get_expert_for_file(Path("/repo"), "test.py", limit=3)

        # All should be grouped as one author
        assert len(result) == 1
        assert result[0].commit_count == 3

    async def test_get_expert_all_time(self, adapter: GitHunterAdapter) -> None:
        """Test get_expert_for_file with window_days=0 uses all history."""
        git_log_output = """a@ex.com|A|aaa|1704067200
"""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(git_log_output.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock:
            await adapter.get_expert_for_file(Path("/repo"), "test.py", window_days=0, limit=3)

        # Check that --since was not added
        call_args = mock.call_args[0]
        assert "--since=" not in " ".join(call_args)


class TestGetGitHubRepo:
    """Tests for GitHunterAdapter._get_github_repo()."""

    @pytest.fixture
    def adapter(self) -> GitHunterAdapter:
        """Create adapter for testing."""
        return GitHunterAdapter()

    async def test_ssh_remote_url(self, adapter: GitHunterAdapter) -> None:
        """Test parsing SSH remote URL."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"git@github.com:owner/repo.git\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter._get_github_repo(Path("/repo"))

        assert result == ("owner", "repo")

    async def test_https_remote_url(self, adapter: GitHunterAdapter) -> None:
        """Test parsing HTTPS remote URL."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"https://github.com/owner/repo.git\n", b"")
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter._get_github_repo(Path("/repo"))

        assert result == ("owner", "repo")

    async def test_ssh_without_git_extension(self, adapter: GitHunterAdapter) -> None:
        """Test parsing SSH URL without .git extension."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"git@github.com:owner/repo\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter._get_github_repo(Path("/repo"))

        assert result == ("owner", "repo")

    async def test_non_github_remote(self, adapter: GitHunterAdapter) -> None:
        """Test non-GitHub remote returns None."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"git@gitlab.com:owner/repo.git\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await adapter._get_github_repo(Path("/repo"))

        assert result is None


class TestClose:
    """Tests for GitHunterAdapter.close()."""

    async def test_close_cleans_up_client(self) -> None:
        """Test close properly cleans up HTTP client."""
        adapter = GitHunterAdapter()
        mock_client = AsyncMock()
        adapter._http_client = mock_client

        await adapter.close()

        mock_client.aclose.assert_called_once()
        assert adapter._http_client is None

    async def test_close_no_client(self) -> None:
        """Test close works when no client exists."""
        adapter = GitHunterAdapter()

        await adapter.close()  # Should not raise
