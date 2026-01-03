"""Unit tests for PromptManager."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from dataing.adapters.llm.prompt_manager import PromptManager


class TestPromptManager:
    """Tests for PromptManager."""

    @pytest.fixture
    def temp_prompts_dir(self) -> TemporaryDirectory:
        """Create a temporary prompts directory."""
        temp_dir = TemporaryDirectory()

        # Create a test template
        test_template = {
            "system": "You are a {{ role }} assistant.",
            "user": "Hello, {{ name }}!",
        }

        template_path = Path(temp_dir.name) / "test.yaml"
        with open(template_path, "w") as f:
            yaml.dump(test_template, f)

        return temp_dir

    @pytest.fixture
    def manager(self, temp_prompts_dir: TemporaryDirectory) -> PromptManager:
        """Return a PromptManager with temp prompts dir."""
        return PromptManager(prompts_dir=Path(temp_prompts_dir.name))

    def test_init_with_default_dir(self) -> None:
        """Test initialization with default prompts directory."""
        manager = PromptManager()
        assert manager.prompts_dir.exists()

    def test_init_with_custom_dir(
        self,
        temp_prompts_dir: TemporaryDirectory,
    ) -> None:
        """Test initialization with custom prompts directory."""
        manager = PromptManager(prompts_dir=Path(temp_prompts_dir.name))
        assert manager.prompts_dir == Path(temp_prompts_dir.name)

    def test_load_template(self, manager: PromptManager) -> None:
        """Test loading a template from disk."""
        template = manager._load_template("test")

        assert "system" in template
        assert "user" in template
        assert "{{ role }}" in template["system"]

    def test_load_template_caches(self, manager: PromptManager) -> None:
        """Test that templates are cached."""
        manager._load_template("test")
        manager._load_template("test")

        assert "test" in manager._cache

    def test_render(self, manager: PromptManager) -> None:
        """Test rendering a template."""
        result = manager.render("test", role="helpful", name="World")

        assert "helpful" in result
        assert "World" in result

    def test_render_combines_system_and_user(
        self,
        manager: PromptManager,
    ) -> None:
        """Test that render combines system and user prompts."""
        result = manager.render("test", role="test", name="User")

        assert "You are a test assistant." in result
        assert "Hello, User!" in result

    def test_render_messages(self, manager: PromptManager) -> None:
        """Test rendering messages for Claude API."""
        messages, system = manager.render_messages("test", role="AI", name="Claude")

        assert system == "You are a AI assistant."
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello, Claude!"

    def test_list_templates(self, manager: PromptManager) -> None:
        """Test listing available templates."""
        templates = manager.list_templates()

        assert "test" in templates

    def test_clear_cache(self, manager: PromptManager) -> None:
        """Test clearing the template cache."""
        manager._load_template("test")
        assert "test" in manager._cache

        manager.clear_cache()

        assert manager._cache == {}

    def test_load_template_raises_on_missing(
        self,
        manager: PromptManager,
    ) -> None:
        """Test that loading missing template raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            manager._load_template("nonexistent")
