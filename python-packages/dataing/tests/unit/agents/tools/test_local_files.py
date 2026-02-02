"""Tests for local_files tool module."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataing.agents.tools.local_files import (
    LocalFileReader,
    get_file_reader,
    read_local_file,
    reset_file_reader,
    search_in_files,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository structure."""
    # Create allowed directories
    (tmp_path / "python-packages" / "dataing" / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "demo").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "secret-dir").mkdir()

    # Create test files
    (tmp_path / "python-packages" / "dataing" / "src" / "main.py").write_text(
        "print('hello')\nprint('world')\n"
    )
    (tmp_path / "frontend" / "src" / "App.tsx").write_text(
        "export const App = () => <div>Hello</div>;"
    )
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    image: test")
    (tmp_path / "README.md").write_text("# Test Repo\n\nThis is a test.")
    (tmp_path / ".env").write_text("SECRET_KEY=super_secret_123")
    (tmp_path / ".env.example").write_text("SECRET_KEY=your_key_here")
    (tmp_path / "secret-dir" / "data.txt").write_text("Not allowed!")

    return tmp_path


@pytest.fixture
def reader(temp_repo: Path) -> LocalFileReader:
    """Create a file reader for the temp repo."""
    return LocalFileReader(temp_repo)


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset singleton before each test."""
    reset_file_reader()


class TestLocalFileReader:
    """Tests for LocalFileReader class."""

    def test_read_allowed_file(self, reader: LocalFileReader) -> None:
        """Test reading an allowed file."""
        result = reader.read_file("python-packages/dataing/src/main.py")

        assert result.success
        assert result.content is not None
        assert "print('hello')" in result.content
        assert result.file_type == "python"
        assert result.line_count == 2

    def test_read_root_allowed_file(self, reader: LocalFileReader) -> None:
        """Test reading an allowed root file."""
        result = reader.read_file("docker-compose.yml")

        assert result.success
        assert "services:" in result.content
        assert result.file_type == "yaml"

    def test_read_markdown_file(self, reader: LocalFileReader) -> None:
        """Test reading a markdown file."""
        result = reader.read_file("README.md")

        assert result.success
        assert "# Test Repo" in result.content
        assert result.file_type == "markdown"

    def test_block_env_file(self, reader: LocalFileReader) -> None:
        """Test that .env files are blocked."""
        result = reader.read_file(".env")

        assert not result.success
        assert result.error is not None
        assert "blocked" in result.error.lower()
        assert ".env.example" in result.error  # Should suggest alternative

    def test_block_outside_allowed_dirs(self, reader: LocalFileReader) -> None:
        """Test that files outside allowed dirs are blocked."""
        result = reader.read_file("secret-dir/data.txt")

        assert not result.success
        assert "not in allowed directories" in result.error

    def test_path_traversal_blocked(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test that path traversal is blocked."""
        # Try to escape using ..
        result = reader.read_file("python-packages/../../../etc/passwd")

        assert not result.success
        assert result.error is not None
        # Should either detect traversal or be outside repo

    def test_path_traversal_in_middle(self, reader: LocalFileReader) -> None:
        """Test traversal in middle of path."""
        result = reader.read_file("python-packages/dataing/../../../.env")

        assert not result.success

    def test_absolute_path_blocked(self, reader: LocalFileReader) -> None:
        """Test that absolute paths outside repo are blocked."""
        result = reader.read_file("/etc/passwd")

        assert not result.success

    def test_nonexistent_file(self, reader: LocalFileReader) -> None:
        """Test handling of nonexistent file."""
        result = reader.read_file("python-packages/nonexistent.py")

        assert not result.success
        assert "not found" in result.error.lower()

    def test_read_line_range(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test reading specific line range."""
        # Create a longer file
        lines = [f"Line {i}" for i in range(1, 101)]
        (temp_repo / "python-packages" / "long_file.py").write_text("\n".join(lines))

        result = reader.read_file("python-packages/long_file.py", start_line=10, end_line=15)

        assert result.success
        assert "Line 10" in result.content
        assert "Line 15" in result.content
        assert "Line 9" not in result.content
        assert "Line 16" not in result.content

    def test_file_too_large(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test handling of oversized file."""
        # Create a reader with small size limit
        small_reader = LocalFileReader(temp_repo, max_file_size=100)

        # Create a file larger than limit
        (temp_repo / "python-packages" / "large.py").write_text("x" * 200)

        result = small_reader.read_file("python-packages/large.py")

        assert not result.success
        assert "too large" in result.error.lower()


class TestPathValidation:
    """Tests for path validation."""

    def test_is_path_allowed_in_allowed_dir(self, reader: LocalFileReader) -> None:
        """Test that paths in allowed dirs are allowed."""
        is_allowed, error = reader.is_path_allowed("python-packages/test.py")
        assert is_allowed
        assert error is None

    def test_is_path_allowed_root_pattern(self, reader: LocalFileReader) -> None:
        """Test root patterns are allowed."""
        is_allowed, error = reader.is_path_allowed("docker-compose.yml")
        assert is_allowed

        is_allowed, error = reader.is_path_allowed("docker-compose.dev.yml")
        assert is_allowed

    def test_is_path_blocked_pattern(self, reader: LocalFileReader) -> None:
        """Test blocked patterns."""
        patterns_to_test = [
            ".env",
            "credentials.json",
            "secret.yaml",
            "api_token.txt",
            "private.key",
            "cert.pem",
        ]

        for pattern in patterns_to_test:
            is_allowed, error = reader.is_path_allowed(f"python-packages/{pattern}")
            assert not is_allowed, f"{pattern} should be blocked"

    def test_is_path_outside_repo(self, reader: LocalFileReader) -> None:
        """Test paths outside repo are blocked."""
        is_allowed, error = reader.is_path_allowed("/etc/passwd")
        assert not is_allowed


class TestFileSearch:
    """Tests for file search functionality."""

    def test_search_files(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test searching for pattern in files."""
        results = reader.search_files("hello")

        assert len(results) > 0
        # Should find in python file
        found_python = any("main.py" in r[0] for r in results)
        assert found_python

    def test_search_in_directory(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test searching in specific directory."""
        results = reader.search_files("print", directory="python-packages")

        assert len(results) > 0
        # All results should be in python-packages
        assert all("python-packages" in r[0] for r in results)

    def test_search_blocked_directory(self, reader: LocalFileReader) -> None:
        """Test that searching blocked directories returns empty."""
        results = reader.search_files("data", directory="secret-dir")

        assert len(results) == 0

    def test_search_max_results(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test max results limit."""
        # Create many files with matching content
        for i in range(20):
            (temp_repo / "python-packages" / f"file_{i}.py").write_text("MATCH\n" * 10)

        results = reader.search_files("MATCH", max_results=5)

        assert len(results) <= 5


class TestListDirectory:
    """Tests for directory listing."""

    def test_list_directory(self, reader: LocalFileReader) -> None:
        """Test listing directory contents."""
        files = reader.list_files("python-packages/dataing/src")

        assert len(files) > 0
        assert any("main.py" in f for f in files)

    def test_list_with_pattern(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test listing with glob pattern."""
        # Create multiple file types
        (temp_repo / "python-packages" / "a.py").write_text("")
        (temp_repo / "python-packages" / "b.py").write_text("")
        (temp_repo / "python-packages" / "c.txt").write_text("")

        files = reader.list_files("python-packages", pattern="*.py")

        assert all(f.endswith(".py") for f in files)

    def test_list_blocked_directory(self, reader: LocalFileReader) -> None:
        """Test listing blocked directory."""
        files = reader.list_files("secret-dir")

        assert len(files) == 0


class TestToolFunctions:
    """Tests for async tool functions."""

    @pytest.mark.asyncio
    async def test_read_local_file(self, temp_repo: Path) -> None:
        """Test read_local_file tool function."""
        # Initialize with temp repo
        reset_file_reader()
        get_file_reader(temp_repo)

        result = await read_local_file("docker-compose.yml")

        assert "[yaml]" in result
        assert "docker-compose.yml" in result
        assert "services:" in result

    @pytest.mark.asyncio
    async def test_read_local_file_blocked(self, temp_repo: Path) -> None:
        """Test read_local_file with blocked file."""
        reset_file_reader()
        get_file_reader(temp_repo)

        result = await read_local_file(".env")

        assert "Error:" in result
        assert "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_search_in_files(self, temp_repo: Path) -> None:
        """Test search_in_files tool function."""
        reset_file_reader()
        get_file_reader(temp_repo)

        result = await search_in_files("hello")

        assert "matches" in result.lower()
        assert "main.py" in result


class TestSymlinkSafety:
    """Tests for symlink handling."""

    def test_symlink_to_blocked_file(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test that symlinks to blocked files are rejected."""
        # Create symlink to .env
        link_path = temp_repo / "python-packages" / "env_link"
        try:
            link_path.symlink_to(temp_repo / ".env")
        except OSError:
            pytest.skip("Symlinks not supported")

        result = reader.read_file("python-packages/env_link")

        # Should be blocked either because target is .env or outside allowed
        assert not result.success

    def test_symlink_outside_repo(self, reader: LocalFileReader, temp_repo: Path) -> None:
        """Test that symlinks outside repo are rejected."""
        # Create symlink to /etc/passwd (if it exists)
        if not Path("/etc/passwd").exists():
            pytest.skip("Test requires /etc/passwd")

        link_path = temp_repo / "python-packages" / "passwd_link"
        try:
            link_path.symlink_to("/etc/passwd")
        except OSError:
            pytest.skip("Symlinks not supported")

        result = reader.read_file("python-packages/passwd_link")

        assert not result.success
