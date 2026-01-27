"""Tests for ask command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from dataing_cli.main import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    pass


class TestAskCommand:
    """Tests for dataing ask command."""

    def test_ask_help(self, runner: CliRunner) -> None:
        """Test ask --help shows usage."""
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0
        assert "Interactive investigation mode" in result.output

    def test_ask_no_investigation_error(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test error when no investigation attached."""
        # Write minimal config without current investigation
        config_file = mock_config_dir / "config.toml"
        config_file.write_text('api_key = "test_key"\n')
        monkeypatch.setattr("dataing_cli.config._get_keyring_credential", lambda: None)

        result = runner.invoke(app, ["ask", "test question"])

        assert result.exit_code == 1
        assert "No investigation attached" in result.output

    def test_ask_one_shot_sends_message(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test one-shot mode sends message via SDK."""
        # Configure current investigation
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        # Mock stream_run to return terminal event
        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True
        mock_client_patch.stream_run.return_value = iter([completed_event])

        result = runner.invoke(app, ["ask", "What caused this?"])

        mock_client_patch.send_message.assert_called_once_with("test-inv-id", "What caused this?")
        assert result.exit_code == 0

    def test_ask_with_investigation_flag(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --investigation flag overrides config."""
        # Return None from config so flag is required
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: None,
        )

        # Mock stream_run to return terminal event
        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True
        mock_client_patch.stream_run.return_value = iter([completed_event])

        result = runner.invoke(app, ["ask", "--investigation", "explicit-id", "question"])

        mock_client_patch.send_message.assert_called_with("explicit-id", "question")
        assert result.exit_code == 0

    def test_ask_saves_investigation_to_config(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test explicit investigation ID saved to config."""
        mock_set = MagicMock()
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: None,
        )
        monkeypatch.setattr(
            "dataing_cli.commands.ask.set_current_investigation_id",
            mock_set,
        )

        # Mock stream_run to return terminal event
        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True
        mock_client_patch.stream_run.return_value = iter([completed_event])

        runner.invoke(app, ["ask", "--investigation", "new-id", "question"])

        mock_set.assert_called_with("new-id")


class TestAskOneShot:
    """Tests for one-shot message sending."""

    def test_streams_response(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test response is streamed to terminal."""
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Root cause found", "confidence": 0.85}
        completed_event.is_terminal = True
        mock_client_patch.stream_run.return_value = iter([completed_event])

        result = runner.invoke(app, ["ask", "question"])

        mock_client_patch.stream_run.assert_called_once()
        assert result.exit_code == 0

    def test_stops_on_terminal_event(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test streaming stops on terminal event."""
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        terminal_event = MagicMock()
        terminal_event.event = "run_completed"
        terminal_event.data = {"root_cause": "Test", "confidence": 0.9}
        terminal_event.is_terminal = True
        mock_client_patch.stream_run.return_value = iter([terminal_event])

        result = runner.invoke(app, ["ask", "question"])
        # Should not hang or error
        assert result.exit_code == 0

    def test_handles_hypothesis_events(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test hypothesis testing events are handled."""
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        hypothesis_event = MagicMock()
        hypothesis_event.event = "hypothesis_testing"
        hypothesis_event.data = {"hypothesis": "Test hypothesis"}
        hypothesis_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([hypothesis_event, completed_event])

        result = runner.invoke(app, ["ask", "question"])
        assert result.exit_code == 0

    def test_handles_evidence_events(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test evidence events are handled."""
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        evidence_event = MagicMock()
        evidence_event.event = "run_evidence"
        evidence_event.data = {
            "kind": "query_result",
            "query": "SELECT * FROM test",
            "interpretation": "Found data",
        }
        evidence_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([evidence_event, completed_event])

        result = runner.invoke(app, ["ask", "question"])
        assert result.exit_code == 0

    def test_handles_failed_run(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test failed run returns non-zero exit code."""
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        failed_event = MagicMock()
        failed_event.event = "run_failed"
        failed_event.data = {"error": "Investigation failed"}
        failed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([failed_event])

        result = runner.invoke(app, ["ask", "question"])
        assert result.exit_code == 1

    def test_handles_awaiting_user_event(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test awaiting_user event ends streaming gracefully."""
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        awaiting_event = MagicMock()
        awaiting_event.event = "awaiting_user"
        awaiting_event.data = {}
        awaiting_event.is_terminal = False

        mock_client_patch.stream_run.return_value = iter([awaiting_event])

        result = runner.invoke(app, ["ask", "question"])
        assert result.exit_code == 0


class TestAskRepl:
    """Tests for REPL entry point."""

    def test_ask_no_args_enters_repl(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test ask with no args tries to enter REPL mode."""
        monkeypatch.setattr(
            "dataing_cli.commands.ask.get_current_investigation_id",
            lambda: "test-inv-id",
        )

        # Mock the REPL to avoid actual interactive mode
        mock_repl_class = MagicMock()
        mock_repl_instance = MagicMock()
        mock_repl_class.return_value = mock_repl_instance

        with patch("dataing_cli.repl.DataingREPL", mock_repl_class):
            result = runner.invoke(app, ["ask"])

        mock_repl_class.assert_called_once_with(mock_client_patch, "test-inv-id")
        mock_repl_instance.run.assert_called_once()
        assert result.exit_code == 0
