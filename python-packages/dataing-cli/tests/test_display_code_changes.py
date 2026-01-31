"""Tests for code change link display in CLI."""

from __future__ import annotations

import os
from unittest.mock import patch

from dataing_cli.display import (
    format_code_change_link,
    format_code_changes_panel,
    terminal_link,
    terminal_supports_hyperlinks,
)

from dataing.core.domain_types import CodeChangeLink


class TestTerminalSupportsHyperlinks:
    """Tests for terminal_supports_hyperlinks function."""

    def test_iterm_supports_hyperlinks(self) -> None:
        """iTerm.app should support hyperlinks."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}, clear=False):
            assert terminal_supports_hyperlinks() is True

    def test_wezterm_supports_hyperlinks(self) -> None:
        """WezTerm should support hyperlinks."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "WezTerm"}, clear=False):
            assert terminal_supports_hyperlinks() is True

    def test_vscode_supports_hyperlinks(self) -> None:
        """VS Code terminal should support hyperlinks."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "vscode"}, clear=False):
            assert terminal_supports_hyperlinks() is True

    def test_vte_5000_supports_hyperlinks(self) -> None:
        """VTE 0.50+ should support hyperlinks."""
        with patch.dict(os.environ, {"VTE_VERSION": "5000", "TERM_PROGRAM": ""}, clear=False):
            assert terminal_supports_hyperlinks() is True

    def test_kitty_supports_hyperlinks(self) -> None:
        """Kitty terminal should support hyperlinks."""
        with patch.dict(os.environ, {"TERM": "xterm-kitty", "TERM_PROGRAM": ""}, clear=False):
            assert terminal_supports_hyperlinks() is True


class TestTerminalLink:
    """Tests for terminal_link function."""

    def test_creates_osc8_link_when_supported(self) -> None:
        """Should create OSC 8 hyperlink when terminal supports it."""
        with patch("dataing_cli.display.terminal_supports_hyperlinks", return_value=True):
            result = terminal_link("Click me", "https://example.com")
            assert "\033]8;;" in result
            assert "https://example.com" in result
            assert "Click me" in result

    def test_falls_back_to_plain_text(self) -> None:
        """Should fall back to plain text when hyperlinks not supported."""
        with patch("dataing_cli.display.terminal_supports_hyperlinks", return_value=False):
            result = terminal_link("Click me", "https://example.com")
            assert result == "Click me (https://example.com)"


class TestFormatCodeChangeLink:
    """Tests for format_code_change_link function."""

    def test_formats_pr_with_title(self) -> None:
        """Should format PR with number and title."""
        link = CodeChangeLink(
            commit_hash="abc123def456",
            message="Fix null handling",
            url="https://github.com/acme/repo/pull/42",
            pr_number=42,
            pr_title="Fix null handling in orders",
            author="developer123",
        )
        with patch("dataing_cli.display.terminal_supports_hyperlinks", return_value=False):
            result = format_code_change_link(link)
            assert "PR #42" in result
            assert "Fix null handling in orders" in result
            assert "https://github.com/acme/repo/pull/42" in result

    def test_formats_pr_without_title(self) -> None:
        """Should format PR with just number when no title."""
        link = CodeChangeLink(
            commit_hash="abc123def456",
            url="https://github.com/acme/repo/pull/42",
            pr_number=42,
        )
        with patch("dataing_cli.display.terminal_supports_hyperlinks", return_value=False):
            result = format_code_change_link(link)
            assert "PR #42" in result

    def test_formats_commit_with_message(self) -> None:
        """Should format commit with hash and message."""
        link = CodeChangeLink(
            commit_hash="abc123def456",
            message="Fix null handling",
            url="https://github.com/acme/repo/commit/abc123def456",
        )
        with patch("dataing_cli.display.terminal_supports_hyperlinks", return_value=False):
            result = format_code_change_link(link)
            assert "abc123d" in result  # Short hash
            assert "Fix null handling" in result

    def test_formats_commit_without_message(self) -> None:
        """Should format commit with just hash when no message."""
        link = CodeChangeLink(
            commit_hash="abc123def456",
            url="https://github.com/acme/repo/commit/abc123def456",
        )
        with patch("dataing_cli.display.terminal_supports_hyperlinks", return_value=False):
            result = format_code_change_link(link)
            assert "abc123d" in result

    def test_truncates_long_message(self) -> None:
        """Should truncate long commit messages."""
        long_message = "A" * 100
        link = CodeChangeLink(
            commit_hash="abc123def456",
            message=long_message,
            url="https://github.com/acme/repo/commit/abc123def456",
        )
        with patch("dataing_cli.display.terminal_supports_hyperlinks", return_value=False):
            result = format_code_change_link(link)
            assert "..." in result


class TestFormatCodeChangesPanel:
    """Tests for format_code_changes_panel function."""

    def test_returns_none_for_empty_list(self) -> None:
        """Should return None when no code changes."""
        result = format_code_changes_panel([])
        assert result is None

    def test_formats_list_of_code_change_links(self) -> None:
        """Should format list of CodeChangeLink objects."""
        changes = [
            CodeChangeLink(
                commit_hash="abc123",
                message="Fix bug",
                url="https://github.com/acme/repo/pull/42",
                pr_number=42,
                pr_title="Fix bug",
                author="dev1",
            ),
            CodeChangeLink(
                commit_hash="def456",
                message="Add feature",
                url="https://github.com/acme/repo/commit/def456",
                author="dev2",
            ),
        ]
        result = format_code_changes_panel(changes)
        assert result is not None
        assert result.title == "Related Code Changes"

    def test_formats_list_of_dicts(self) -> None:
        """Should format list of dicts."""
        changes = [
            {
                "commit_hash": "abc123",
                "message": "Fix bug",
                "url": "https://github.com/acme/repo/pull/42",
                "pr_number": 42,
                "pr_title": "Fix bug",
                "author": "dev1",
            },
        ]
        result = format_code_changes_panel(changes)
        assert result is not None

    def test_limits_to_10_changes(self) -> None:
        """Should limit display to 10 changes."""
        changes = [
            CodeChangeLink(
                commit_hash=f"hash{i}",
                message=f"Change {i}",
                url=f"https://github.com/acme/repo/commit/hash{i}",
            )
            for i in range(15)
        ]
        result = format_code_changes_panel(changes)
        assert result is not None
        # Panel should be created (exact content is Rich internal)
