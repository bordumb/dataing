"""Tests for run commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from dataing_cli.main import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    pass


class TestRunStartCommand:
    """Tests for run start command."""

    def test_run_start_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run start creates an investigation."""
        mock_run = MagicMock()
        mock_run.run_id = "run-xyz123"
        mock_run.model_dump.return_value = {"run_id": "run-xyz123"}
        mock_client_patch.run.return_value = mock_run
        mock_client_patch.stream_run.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "run",
                "start",
                "schema.table",
                "--goal",
                "investigate null spike",
                "--no-watch",
            ],
        )

        assert result.exit_code == 0
        assert "Started run" in result.output
        assert "run-xyz123" in result.output

    def test_run_start_with_datasource(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run start with explicit datasource."""
        mock_run = MagicMock()
        mock_run.run_id = "run-xyz123"
        mock_client_patch.run.return_value = mock_run
        mock_client_patch.stream_run.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "run",
                "start",
                "schema.table",
                "--goal",
                "test",
                "--datasource",
                "ds-custom",
                "--no-watch",
            ],
        )

        assert result.exit_code == 0
        # Verify the asset was created with correct datasource_id
        call_kwargs = mock_client_patch.run.call_args[1]
        assert call_kwargs["assets"][0].datasource_id == "ds-custom"

    def test_run_start_no_datasource(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test run start fails when no datasource configured."""
        # Write minimal config without default datasource
        config_file = mock_config_dir / "config.toml"
        config_file.write_text('api_key = "test_key"\n')
        monkeypatch.setattr("dataing_cli.config._get_keyring_credential", lambda: None)

        result = runner.invoke(
            app,
            ["run", "start", "schema.table", "--goal", "test"],
        )

        assert result.exit_code == 1
        assert "No datasource" in result.output

    def test_run_start_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run start with --json flag."""
        mock_run = MagicMock()
        mock_run.run_id = "run-xyz123"
        mock_run.model_dump.return_value = {
            "run_id": "run-xyz123",
            "status": "running",
        }
        mock_client_patch.run.return_value = mock_run

        result = runner.invoke(
            app,
            [
                "--json",
                "run",
                "start",
                "schema.table",
                "--goal",
                "test",
            ],
        )

        assert result.exit_code == 0
        # Should contain JSON output and run ID
        assert "run-xyz123" in result.output
        # Find and parse the JSON portion (after the "Started run" line)
        lines = result.output.strip().split("\n")
        # The JSON output starts with a line containing just "{"
        json_lines = []
        in_json = False
        for line in lines:
            if line.strip() == "{":
                in_json = True
            if in_json:
                json_lines.append(line)
        if json_lines:
            data = json.loads("\n".join(json_lines))
            assert data["run_id"] == "run-xyz123"


class TestRunWatchCommand:
    """Tests for run watch command."""

    def test_run_watch_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch streams events."""
        # Create mock events
        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test root cause", "confidence": 0.85}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0
        # Accept either Rich format or plain text format (non-TTY)
        assert (
            "Root Cause" in result.output
            or "Synthesis" in result.output
            or "run_completed" in result.output
        )

    def test_run_watch_with_evidence(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch displays evidence events."""
        evidence_event = MagicMock()
        evidence_event.event = "run_evidence"
        evidence_event.data = {
            "hypothesis": "Test hypothesis",
            "query": "SELECT * FROM test",
            "interpretation": "Test finding",
        }
        evidence_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([evidence_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0

    def test_run_watch_failed(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch handles failed run."""
        failed_event = MagicMock()
        failed_event.event = "run_failed"
        failed_event.data = {"error": "Investigation failed"}
        failed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([failed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 1
        assert "Failed" in result.output or "failed" in result.output

    def test_run_watch_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run watch with --json flag."""
        started_event = MagicMock()
        started_event.event = "run_started"
        started_event.data = {"message": "Started"}
        started_event.is_terminal = False
        started_event.model_dump.return_value = {
            "event": "run_started",
            "data": {"message": "Started"},
        }

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True
        completed_event.model_dump.return_value = {
            "event": "run_completed",
            "data": {"root_cause": "Test", "confidence": 0.9},
        }

        mock_client_patch.stream_run.return_value = iter([started_event, completed_event])

        result = runner.invoke(app, ["--json", "run", "watch", "run-123"])

        assert result.exit_code == 0
        # Output should contain JSON
        assert "run_completed" in result.output


class TestRunProgressEvents:
    """Tests for progress event handling."""

    def test_progress_events_are_handled(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test progress events are handled without error."""
        progress_event = MagicMock()
        progress_event.event = "run_progress"
        progress_event.data = {"message": "Gathering context..."}
        progress_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([progress_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0

    def test_hypothesis_testing_events(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test hypothesis testing events are handled."""
        hypothesis_event = MagicMock()
        hypothesis_event.event = "hypothesis_testing"
        hypothesis_event.data = {"message": "Testing hypothesis..."}
        hypothesis_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([hypothesis_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0

    def test_run_started_event(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test run_started event is handled."""
        started_event = MagicMock()
        started_event.event = "run_started"
        started_event.data = {}
        started_event.is_terminal = False

        completed_event = MagicMock()
        completed_event.event = "run_completed"
        completed_event.data = {"root_cause": "Test", "confidence": 0.9}
        completed_event.is_terminal = True

        mock_client_patch.stream_run.return_value = iter([started_event, completed_event])

        result = runner.invoke(app, ["run", "watch", "run-123"])

        assert result.exit_code == 0
