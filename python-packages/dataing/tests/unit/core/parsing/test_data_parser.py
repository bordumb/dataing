"""Tests for data_parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataing.core.parsing.data_parser import DataParser, SampleResult


@pytest.fixture
def data_parser() -> DataParser:
    """Create a data parser instance."""
    return DataParser()


@pytest.fixture
def sample_csv_file(tmp_path: Path) -> Path:
    """Create a sample CSV file."""
    content = """id,name,value,active
1,Alice,100,true
2,Bob,200,false
3,Carol,300,true
4,Dave,400,false
5,Eve,500,true
"""
    file_path = tmp_path / "data.csv"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_tsv_file(tmp_path: Path) -> Path:
    """Create a sample TSV file."""
    content = "id\tname\tvalue\n1\tAlice\t100\n2\tBob\t200\n"
    file_path = tmp_path / "data.tsv"
    file_path.write_text(content)
    return file_path


class TestSampleResult:
    """Tests for SampleResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a sample result."""
        result = SampleResult(
            columns=["id", "name"],
            rows=[{"id": "1", "name": "test"}],
            total_rows=100,
            file_size=1000,
            format="csv",
        )

        assert len(result.columns) == 2
        assert len(result.rows) == 1
        assert result.total_rows == 100
        assert not result.truncated


class TestDataParser:
    """Tests for DataParser class."""

    def test_sample_csv(self, data_parser: DataParser, sample_csv_file: Path) -> None:
        """Test sampling a CSV file."""
        result = data_parser.sample_file(sample_csv_file)

        assert isinstance(result, SampleResult)
        assert result.format == "csv"
        assert "id" in result.columns
        assert "name" in result.columns
        assert len(result.rows) == 5
        assert result.rows[0]["name"] == "Alice"

    def test_sample_csv_with_n_rows(self, data_parser: DataParser, sample_csv_file: Path) -> None:
        """Test sampling specific number of rows."""
        result = data_parser.sample_file(sample_csv_file, n_rows=2)

        assert len(result.rows) == 2
        assert result.truncated

    def test_sample_csv_specific_columns(
        self, data_parser: DataParser, sample_csv_file: Path
    ) -> None:
        """Test sampling specific columns."""
        result = data_parser.sample_file(sample_csv_file, columns=["id", "name"])

        assert result.columns == ["id", "name"]
        assert "value" not in result.rows[0]

    def test_sample_tsv(self, data_parser: DataParser, sample_tsv_file: Path) -> None:
        """Test sampling a TSV file."""
        result = data_parser.sample_file(sample_tsv_file)

        assert result.format == "csv"  # TSV is a variant of CSV
        assert len(result.rows) == 2
        assert result.rows[0]["name"] == "Alice"

    def test_get_schema(self, data_parser: DataParser, sample_csv_file: Path) -> None:
        """Test getting schema from CSV."""
        schema = data_parser.get_schema(sample_csv_file)

        assert "id" in schema
        assert "name" in schema
        # Schema inference should detect types
        assert schema["id"] == "integer"
        assert schema["name"] == "string"
        assert schema["active"] == "boolean"

    def test_count_rows(self, data_parser: DataParser, sample_csv_file: Path) -> None:
        """Test counting rows."""
        count = data_parser.count_rows(sample_csv_file)
        assert count == 5

    def test_format_as_markdown(self, data_parser: DataParser, sample_csv_file: Path) -> None:
        """Test formatting as markdown table."""
        result = data_parser.sample_file(sample_csv_file, n_rows=2)
        markdown = data_parser.format_sample_as_markdown(result)

        assert "| id |" in markdown
        assert "| name |" in markdown
        assert "Alice" in markdown
        assert "---" in markdown  # Table separator

    def test_file_not_found(self, data_parser: DataParser) -> None:
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            data_parser.sample_file("/nonexistent/file.csv")

    def test_unsupported_format(self, data_parser: DataParser, tmp_path: Path) -> None:
        """Test handling of unsupported format."""
        file_path = tmp_path / "data.xlsx"
        file_path.write_text("not excel")

        with pytest.raises(ValueError, match="Unsupported"):
            data_parser.sample_file(file_path)

    def test_file_size_limit(self, data_parser: DataParser, tmp_path: Path) -> None:
        """Test file size limit."""
        parser = DataParser(max_file_size=100)
        file_path = tmp_path / "large.csv"
        file_path.write_text("a,b,c\n" + "1,2,3\n" * 100)

        with pytest.raises(ValueError, match="exceeds size limit"):
            parser.sample_file(file_path)

    def test_empty_csv(self, data_parser: DataParser, tmp_path: Path) -> None:
        """Test handling of empty CSV."""
        file_path = tmp_path / "empty.csv"
        file_path.write_text("id,name,value\n")

        result = data_parser.sample_file(file_path)

        assert len(result.rows) == 0
        assert result.total_rows == 0
