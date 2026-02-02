"""JSON file parser with safe loading and helpful summaries.

Provides utilities for parsing JSON files with size limits
and formatted summaries for LLM consumption.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JsonParser:
    """Parser for JSON files with safe loading.

    Provides size-limited parsing and helpful summaries
    for large JSON structures.
    """

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(self, max_file_size: int = MAX_FILE_SIZE) -> None:
        """Initialize the JSON parser.

        Args:
            max_file_size: Maximum file size in bytes.
        """
        self.max_file_size = max_file_size

    def parse_file(self, path: Path | str) -> Any:
        """Parse a JSON file.

        Args:
            path: Path to the JSON file.

        Returns:
            Parsed JSON content.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file exceeds size limit.
            json.JSONDecodeError: If JSON is invalid.
        """
        path = Path(path)

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(
                f"JSON file exceeds size limit: {file_size:,} > {self.max_file_size:,} bytes"
            )

        content = path.read_text(encoding="utf-8")
        return self.parse_string(content)

    def parse_string(self, content: str) -> Any:
        """Parse a JSON string.

        Args:
            content: JSON content as string.

        Returns:
            Parsed JSON content.

        Raises:
            json.JSONDecodeError: If JSON is invalid.
        """
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise

    def format_summary(
        self,
        data: Any,
        max_depth: int = 3,
        max_array_items: int = 5,
    ) -> str:
        """Format JSON data as a readable summary.

        Useful for providing concise view of JSON content to LLMs.

        Args:
            data: Parsed JSON data.
            max_depth: Maximum nesting depth to show.
            max_array_items: Maximum array items to show before truncating.

        Returns:
            Formatted string summary.
        """
        return self._format_value(
            data,
            depth=0,
            max_depth=max_depth,
            max_array_items=max_array_items,
        )

    def get_schema_summary(self, data: Any) -> dict[str, Any]:
        """Infer a schema summary from JSON data.

        Useful for understanding the structure of large JSON files.

        Args:
            data: Parsed JSON data.

        Returns:
            Dict describing the structure.
        """
        return self._infer_schema(data)

    def _format_value(
        self,
        value: Any,
        depth: int,
        max_depth: int,
        max_array_items: int,
    ) -> str:
        """Recursively format a value.

        Args:
            value: Value to format.
            depth: Current depth.
            max_depth: Maximum depth.
            max_array_items: Maximum array items.

        Returns:
            Formatted string.
        """
        indent = "  " * depth

        if depth >= max_depth:
            if isinstance(value, dict):
                return f"{{...}} ({len(value)} keys)"
            elif isinstance(value, list):
                return f"[...] ({len(value)} items)"
            else:
                return self._format_primitive(value)

        if isinstance(value, dict):
            if not value:
                return "{}"
            lines = ["{"]
            for k, v in value.items():
                formatted_v = self._format_value(v, depth + 1, max_depth, max_array_items)
                lines.append(f'{indent}  "{k}": {formatted_v}')
            lines.append(f"{indent}}}")
            return "\n".join(lines)

        elif isinstance(value, list):
            if not value:
                return "[]"
            lines = ["["]
            for i, item in enumerate(value):
                if i >= max_array_items:
                    lines.append(f"{indent}  ... ({len(value) - max_array_items} more items)")
                    break
                formatted_item = self._format_value(item, depth + 1, max_depth, max_array_items)
                lines.append(f"{indent}  {formatted_item}")
            lines.append(f"{indent}]")
            return "\n".join(lines)

        else:
            return self._format_primitive(value)

    def _format_primitive(self, value: Any) -> str:
        """Format a primitive value.

        Args:
            value: Primitive value.

        Returns:
            Formatted string.
        """
        if isinstance(value, str):
            if len(value) > 100:
                return f'"{value[:100]}..." ({len(value)} chars)'
            return json.dumps(value)
        elif value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        else:
            return str(value)

    def _infer_schema(self, value: Any, path: str = "$") -> dict[str, Any]:
        """Infer schema from a value.

        Args:
            value: Value to analyze.
            path: JSON path to this value.

        Returns:
            Schema dict.
        """
        if isinstance(value, dict):
            properties = {}
            for k, v in value.items():
                properties[k] = self._infer_schema(v, f"{path}.{k}")
            return {"type": "object", "properties": properties}

        elif isinstance(value, list):
            if not value:
                return {"type": "array", "items": {"type": "unknown"}}
            # Sample first few items
            item_types = set()
            for item in value[:5]:
                item_types.add(self._get_type_name(item))
            return {
                "type": "array",
                "length": len(value),
                "item_types": list(item_types),
            }

        else:
            return {"type": self._get_type_name(value)}

    def _get_type_name(self, value: Any) -> str:
        """Get the JSON type name for a value.

        Args:
            value: Value to type.

        Returns:
            Type name string.
        """
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "number"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            return "array"
        elif isinstance(value, dict):
            return "object"
        else:
            return "unknown"
