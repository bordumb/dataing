"""Tests for json_parser module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dataing.core.parsing.json_parser import JsonParser


@pytest.fixture
def json_parser() -> JsonParser:
    """Create a JSON parser instance."""
    return JsonParser()


class TestJsonParser:
    """Tests for JsonParser class."""

    def test_parse_simple_dict(self, json_parser: JsonParser, tmp_path: Path) -> None:
        """Test parsing a simple dict."""
        file_path = tmp_path / "config.json"
        file_path.write_text('{"key": "value", "number": 42}')

        result = json_parser.parse_file(file_path)

        assert result == {"key": "value", "number": 42}

    def test_parse_nested_structure(self, json_parser: JsonParser, tmp_path: Path) -> None:
        """Test parsing nested structures."""
        data = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "credentials": {"username": "admin", "password": "secret"},
            }
        }
        file_path = tmp_path / "nested.json"
        file_path.write_text(json.dumps(data))

        result = json_parser.parse_file(file_path)

        assert result["database"]["host"] == "localhost"
        assert result["database"]["port"] == 5432
        assert result["database"]["credentials"]["username"] == "admin"

    def test_parse_array(self, json_parser: JsonParser, tmp_path: Path) -> None:
        """Test parsing an array."""
        data = [{"name": "item1", "value": 1}, {"name": "item2", "value": 2}]
        file_path = tmp_path / "array.json"
        file_path.write_text(json.dumps(data))

        result = json_parser.parse_file(file_path)

        assert len(result) == 2
        assert result[0]["name"] == "item1"

    def test_parse_string(self, json_parser: JsonParser) -> None:
        """Test parsing a JSON string directly."""
        result = json_parser.parse_string('{"key": "value", "list": ["a", "b"]}')

        assert result["key"] == "value"
        assert result["list"] == ["a", "b"]

    def test_format_summary_simple(self, json_parser: JsonParser) -> None:
        """Test format_summary with simple data."""
        data = {"key": "value", "number": 42}
        summary = json_parser.format_summary(data)

        assert '"key"' in summary
        assert '"value"' in summary

    def test_format_summary_truncates_arrays(self, json_parser: JsonParser) -> None:
        """Test format_summary truncates long arrays."""
        data = {"items": list(range(20))}
        summary = json_parser.format_summary(data, max_array_items=3)

        assert "0" in summary
        assert "1" in summary
        assert "2" in summary
        assert "more items" in summary

    def test_format_summary_max_depth(self, json_parser: JsonParser) -> None:
        """Test format_summary respects max_depth."""
        data = {"l1": {"l2": {"l3": {"l4": "deep"}}}}
        summary = json_parser.format_summary(data, max_depth=2)

        assert "l1" in summary
        assert "l2" in summary
        assert "..." in summary

    def test_get_schema_summary(self, json_parser: JsonParser) -> None:
        """Test schema inference."""
        data = {
            "name": "test",
            "count": 42,
            "active": True,
            "items": [1, 2, 3],
            "nested": {"key": "value"},
        }
        schema = json_parser.get_schema_summary(data)

        assert schema["type"] == "object"
        assert "properties" in schema
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["active"]["type"] == "boolean"
        assert schema["properties"]["items"]["type"] == "array"
        assert schema["properties"]["nested"]["type"] == "object"

    def test_file_not_found(self, json_parser: JsonParser) -> None:
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            json_parser.parse_file("/nonexistent/file.json")

    def test_file_size_limit(self, json_parser: JsonParser, tmp_path: Path) -> None:
        """Test file size limit."""
        parser = JsonParser(max_file_size=100)
        file_path = tmp_path / "large.json"
        file_path.write_text('{"key": "' + "x" * 200 + '"}')

        with pytest.raises(ValueError, match="exceeds size limit"):
            parser.parse_file(file_path)

    def test_invalid_json(self, json_parser: JsonParser, tmp_path: Path) -> None:
        """Test handling of invalid JSON."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text('{"key": invalid}')

        with pytest.raises(json.JSONDecodeError):
            json_parser.parse_file(file_path)
