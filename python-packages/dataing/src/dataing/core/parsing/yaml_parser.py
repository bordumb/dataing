"""YAML file parser with safe loading.

Provides utilities for parsing YAML files with safe defaults
and helpful error messages.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class YamlParser:
    """Parser for YAML files with safe loading.

    Uses safe_load by default to prevent code execution.
    Provides helpful error messages for common YAML issues.
    """

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

    def __init__(self, max_file_size: int = MAX_FILE_SIZE) -> None:
        """Initialize the YAML parser.

        Args:
            max_file_size: Maximum file size in bytes.
        """
        self.max_file_size = max_file_size

    def parse_file(self, path: Path | str) -> Any:
        """Parse a YAML file safely.

        Args:
            path: Path to the YAML file.

        Returns:
            Parsed YAML content (dict, list, or primitive).

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file exceeds size limit.
            yaml.YAMLError: If YAML is invalid.
        """
        path = Path(path)

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(
                f"YAML file exceeds size limit: {file_size:,} > {self.max_file_size:,} bytes"
            )

        content = path.read_text(encoding="utf-8")
        return self.parse_string(content)

    def parse_string(self, content: str) -> Any:
        """Parse a YAML string safely.

        Args:
            content: YAML content as string.

        Returns:
            Parsed YAML content.

        Raises:
            yaml.YAMLError: If YAML is invalid.
        """
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error: {e}")
            raise

    def parse_file_all(self, path: Path | str) -> list[Any]:
        """Parse a multi-document YAML file.

        Args:
            path: Path to the YAML file.

        Returns:
            List of parsed documents.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file exceeds size limit.
            yaml.YAMLError: If YAML is invalid.
        """
        path = Path(path)

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(
                f"YAML file exceeds size limit: {file_size:,} > {self.max_file_size:,} bytes"
            )

        content = path.read_text(encoding="utf-8")
        return list(yaml.safe_load_all(content))

    def format_summary(self, data: Any, max_depth: int = 3) -> str:
        """Format YAML data as a readable summary.

        Useful for providing concise view of YAML content to LLMs.

        Args:
            data: Parsed YAML data.
            max_depth: Maximum nesting depth to show.

        Returns:
            Formatted string summary.
        """
        return self._format_value(data, depth=0, max_depth=max_depth)

    def _format_value(self, value: Any, depth: int, max_depth: int) -> str:
        """Recursively format a value.

        Args:
            value: Value to format.
            depth: Current depth.
            max_depth: Maximum depth.

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
                return repr(value)

        if isinstance(value, dict):
            if not value:
                return "{}"
            lines = ["{"]
            for k, v in value.items():
                formatted_v = self._format_value(v, depth + 1, max_depth)
                lines.append(f"{indent}  {k}: {formatted_v}")
            lines.append(f"{indent}}}")
            return "\n".join(lines)

        elif isinstance(value, list):
            if not value:
                return "[]"
            lines = ["["]
            for item in value:
                formatted_item = self._format_value(item, depth + 1, max_depth)
                lines.append(f"{indent}  - {formatted_item}")
            lines.append(f"{indent}]")
            return "\n".join(lines)

        elif isinstance(value, str):
            if len(value) > 100:
                return f'"{value[:100]}..." ({len(value)} chars)'
            return repr(value)

        else:
            return repr(value)
