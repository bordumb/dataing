"""Prompt Manager - Loads and renders YAML prompt templates.

This module provides a centralized way to manage LLM prompts
using Jinja2 templates stored in YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader


class PromptManager:
    """Loads and renders YAML prompt templates.

    Templates are stored in YAML format with 'system' and 'user'
    keys containing Jinja2 templates.

    Attributes:
        prompts_dir: Directory containing prompt templates.
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        """Initialize the prompt manager.

        Args:
            prompts_dir: Directory containing prompt YAML files.
                        Defaults to the package's prompts directory.
        """
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent.parent / "prompts"

        self.prompts_dir = prompts_dir
        self.env = Environment(
            loader=FileSystemLoader(prompts_dir),
            autoescape=False,  # We're generating text, not HTML
        )
        self._cache: dict[str, dict[str, str]] = {}

    def _load_template(self, template_name: str) -> dict[str, str]:
        """Load a template from cache or disk.

        Args:
            template_name: Name of the template file (without .yaml extension).

        Returns:
            Dictionary with 'system' and 'user' template strings.

        Raises:
            FileNotFoundError: If template file doesn't exist.
        """
        if template_name not in self._cache:
            path = self.prompts_dir / f"{template_name}.yaml"
            with open(path) as f:
                self._cache[template_name] = yaml.safe_load(f)

        return self._cache[template_name]

    def render(self, template_name: str, **context: Any) -> str:
        """Render a prompt template with context.

        Args:
            template_name: Name of the template file (without .yaml).
            **context: Variables to substitute in the template.

        Returns:
            Rendered prompt string combining system and user parts.
        """
        template_data = self._load_template(template_name)

        system = self.env.from_string(template_data.get("system", "")).render(**context)
        user = self.env.from_string(template_data.get("user", "")).render(**context)

        # Combine system and user prompts
        if system and user:
            return f"{system}\n\n{user}"
        return system or user

    def render_messages(
        self, template_name: str, **context: Any
    ) -> tuple[list[dict[str, str]], str]:
        """Render template as separate message dicts for Claude API.

        Args:
            template_name: Name of the template file.
            **context: Variables to substitute.

        Returns:
            Tuple of (messages list, system prompt string).
        """
        template_data = self._load_template(template_name)

        system = self.env.from_string(template_data.get("system", "")).render(**context)
        user = self.env.from_string(template_data.get("user", "")).render(**context)

        messages = []
        if user:
            messages.append({"role": "user", "content": user})

        return messages, system

    def list_templates(self) -> list[str]:
        """List all available template names.

        Returns:
            List of template names (without .yaml extension).
        """
        return [p.stem for p in self.prompts_dir.glob("*.yaml")]

    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._cache = {}
