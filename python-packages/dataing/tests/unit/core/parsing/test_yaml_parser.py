"""Tests for yaml_parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataing.core.parsing.yaml_parser import YamlParser


@pytest.fixture
def yaml_parser() -> YamlParser:
    """Create a YAML parser instance."""
    return YamlParser()


class TestYamlParser:
    """Tests for YamlParser class."""

    def test_parse_simple_dict(self, yaml_parser: YamlParser, tmp_path: Path) -> None:
        """Test parsing a simple dict."""
        file_path = tmp_path / "config.yaml"
        file_path.write_text("key: value\nnumber: 42")

        result = yaml_parser.parse_file(file_path)

        assert result == {"key": "value", "number": 42}

    def test_parse_nested_structure(self, yaml_parser: YamlParser, tmp_path: Path) -> None:
        """Test parsing nested structures."""
        content = """
database:
  host: localhost
  port: 5432
  credentials:
    username: admin
    password: secret
"""
        file_path = tmp_path / "nested.yaml"
        file_path.write_text(content)

        result = yaml_parser.parse_file(file_path)

        assert result["database"]["host"] == "localhost"
        assert result["database"]["port"] == 5432
        assert result["database"]["credentials"]["username"] == "admin"

    def test_parse_list(self, yaml_parser: YamlParser, tmp_path: Path) -> None:
        """Test parsing a list."""
        content = """
items:
  - name: item1
    value: 1
  - name: item2
    value: 2
"""
        file_path = tmp_path / "list.yaml"
        file_path.write_text(content)

        result = yaml_parser.parse_file(file_path)

        assert len(result["items"]) == 2
        assert result["items"][0]["name"] == "item1"

    def test_parse_string(self, yaml_parser: YamlParser) -> None:
        """Test parsing a YAML string directly."""
        result = yaml_parser.parse_string("key: value\nlist:\n  - a\n  - b")

        assert result["key"] == "value"
        assert result["list"] == ["a", "b"]

    def test_parse_multi_document(self, yaml_parser: YamlParser, tmp_path: Path) -> None:
        """Test parsing multi-document YAML."""
        content = """---
doc: 1
---
doc: 2
---
doc: 3
"""
        file_path = tmp_path / "multi.yaml"
        file_path.write_text(content)

        result = yaml_parser.parse_file_all(file_path)

        assert len(result) == 3
        assert result[0]["doc"] == 1
        assert result[2]["doc"] == 3

    def test_format_summary_simple(self, yaml_parser: YamlParser) -> None:
        """Test format_summary with simple data."""
        data = {"key": "value", "number": 42}
        summary = yaml_parser.format_summary(data)

        assert "key" in summary
        assert "'value'" in summary

    def test_format_summary_nested(self, yaml_parser: YamlParser) -> None:
        """Test format_summary with nested data."""
        data = {
            "level1": {
                "level2": {
                    "level3": {"level4": "deep"},
                },
            },
        }
        summary = yaml_parser.format_summary(data, max_depth=2)

        assert "level1" in summary
        assert "level2" in summary
        # level3 should be truncated
        assert "..." in summary

    def test_file_not_found(self, yaml_parser: YamlParser) -> None:
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            yaml_parser.parse_file("/nonexistent/file.yaml")

    def test_file_size_limit(self, yaml_parser: YamlParser, tmp_path: Path) -> None:
        """Test file size limit."""
        parser = YamlParser(max_file_size=100)
        file_path = tmp_path / "large.yaml"
        file_path.write_text("key: " + "x" * 200)

        with pytest.raises(ValueError, match="exceeds size limit"):
            parser.parse_file(file_path)

    def test_invalid_yaml(self, yaml_parser: YamlParser, tmp_path: Path) -> None:
        """Test handling of invalid YAML."""
        import yaml

        file_path = tmp_path / "invalid.yaml"
        file_path.write_text("key: [invalid\nbroken: yaml")

        with pytest.raises(yaml.YAMLError):
            yaml_parser.parse_file(file_path)
