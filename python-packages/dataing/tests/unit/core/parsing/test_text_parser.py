"""Tests for text_parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataing.core.parsing.text_parser import TextChunk, TextParser


@pytest.fixture
def text_parser() -> TextParser:
    """Create a text parser instance."""
    return TextParser()


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a sample text file."""
    content = "\n".join([f"Line {i}" for i in range(1, 101)])
    file_path = tmp_path / "sample.txt"
    file_path.write_text(content)
    return file_path


class TestTextParser:
    """Tests for TextParser class."""

    def test_read_entire_file(self, text_parser: TextParser, sample_file: Path) -> None:
        """Test reading an entire file."""
        result = text_parser.read_file(sample_file)

        assert isinstance(result, TextChunk)
        assert result.total_lines == 100
        assert result.start_line == 1
        assert result.end_line == 100
        assert "Line 1" in result.content
        assert "Line 100" in result.content
        assert not result.truncated

    def test_read_line_range(self, text_parser: TextParser, sample_file: Path) -> None:
        """Test reading a specific line range."""
        result = text_parser.read_file(sample_file, start_line=10, end_line=20)

        assert result.start_line == 10
        assert result.end_line == 20
        assert "Line 10" in result.content
        assert "Line 20" in result.content
        assert "Line 9" not in result.content
        assert "Line 21" not in result.content

    def test_read_with_max_lines(self, text_parser: TextParser, sample_file: Path) -> None:
        """Test reading with max_lines limit."""
        result = text_parser.read_file(sample_file, start_line=1, max_lines=5)

        assert result.start_line == 1
        assert result.end_line == 5
        lines = result.content.split("\n")
        assert len(lines) == 5

    def test_count_lines(self, text_parser: TextParser, sample_file: Path) -> None:
        """Test counting lines in a file."""
        count = text_parser.count_lines(sample_file)
        assert count == 100

    def test_search_lines(self, text_parser: TextParser, sample_file: Path) -> None:
        """Test searching for lines."""
        results = text_parser.search_lines(sample_file, "Line 5")

        # Should match Line 5, Line 50-59 (11 total)
        assert len(results) == 11
        assert (5, "Line 5") in results
        assert (50, "Line 50") in results

    def test_search_case_insensitive(self, text_parser: TextParser, tmp_path: Path) -> None:
        """Test case-insensitive search."""
        file_path = tmp_path / "mixed_case.txt"
        file_path.write_text("Hello World\nhello world\nHELLO WORLD")

        results = text_parser.search_lines(file_path, "hello", case_sensitive=False)
        assert len(results) == 3

        results_sensitive = text_parser.search_lines(file_path, "Hello", case_sensitive=True)
        assert len(results_sensitive) == 1

    def test_search_max_results(self, text_parser: TextParser, sample_file: Path) -> None:
        """Test search with max results limit."""
        results = text_parser.search_lines(sample_file, "Line", max_results=5)
        assert len(results) == 5

    def test_long_line_truncation(self, text_parser: TextParser, tmp_path: Path) -> None:
        """Test that long lines are truncated."""
        parser = TextParser(max_line_length=50)
        file_path = tmp_path / "long_lines.txt"
        file_path.write_text("a" * 100 + "\nshort line")

        result = parser.read_file(file_path)
        lines = result.content.split("\n")

        assert len(lines[0]) == 53  # 50 chars + "..."
        assert lines[0].endswith("...")
        assert result.truncated

    def test_file_not_found(self, text_parser: TextParser) -> None:
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            text_parser.read_file("/nonexistent/file.txt")

    def test_file_size_limit(self, text_parser: TextParser, tmp_path: Path) -> None:
        """Test file size limit."""
        parser = TextParser(max_file_size=100)
        file_path = tmp_path / "large.txt"
        file_path.write_text("x" * 200)

        with pytest.raises(ValueError, match="exceeds size limit"):
            parser.read_file(file_path)

    def test_encoding_fallback(self, text_parser: TextParser, tmp_path: Path) -> None:
        """Test encoding fallback for non-UTF8 files."""
        file_path = tmp_path / "latin1.txt"
        # Write bytes that are valid Latin-1 but not UTF-8
        file_path.write_bytes(b"Caf\xe9")

        result = text_parser.read_file(file_path)
        assert "Caf" in result.content
