"""Tests for init and status commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from dataing_cli.main import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    pass


class TestInitCommand:
    """Tests for the init command."""

    def test_init_success_with_keyring(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test successful init with keyring storage."""
        monkeypatch.setattr("dataing_cli.config._set_keyring_credential", lambda x: True)

        with patch("dataing_sdk.DataingClient") as mock_client:
            mock_client.return_value.health.return_value = None

            result = runner.invoke(
                app,
                [
                    "init",
                    "--url",
                    "http://localhost:8000",
                    "--api-key",
                    "test_key",
                ],
            )

        assert result.exit_code == 0
        assert "Configuration saved" in result.output

    def test_init_success_without_keyring(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init with --no-keyring flag."""
        with patch("dataing_sdk.DataingClient") as mock_client:
            mock_client.return_value.health.return_value = None

            result = runner.invoke(
                app,
                [
                    "init",
                    "--url",
                    "http://localhost:8000",
                    "--api-key",
                    "test_key",
                    "--no-keyring",
                ],
            )

        assert result.exit_code == 0
        assert "Configuration saved" in result.output

        # Check config file was written
        config_file = mock_config_dir / "config.toml"
        assert config_file.exists()
        content = config_file.read_text()
        assert "api_url" in content
        assert "api_key" in content

    def test_init_connection_failure(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
    ) -> None:
        """Test init when connection fails."""
        with patch("dataing_sdk.DataingClient") as mock_client:
            mock_client.return_value.health.side_effect = ConnectionError("Connection refused")

            result = runner.invoke(
                app,
                [
                    "init",
                    "--url",
                    "http://localhost:8000",
                    "--api-key",
                    "test_key",
                ],
            )

        assert result.exit_code == 1
        assert "Connection failed" in result.output

    def test_init_with_custom_url(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init with custom URL."""
        monkeypatch.setattr("dataing_cli.config._set_keyring_credential", lambda x: True)

        with patch("dataing_sdk.DataingClient") as mock_client:
            mock_client.return_value.health.return_value = None

            result = runner.invoke(
                app,
                [
                    "init",
                    "--url",
                    "https://api.example.com",
                    "--api-key",
                    "test_key",
                ],
            )

        assert result.exit_code == 0
        mock_client.assert_called_once_with(base_url="https://api.example.com", api_key="test_key")

    def test_init_keyring_fallback_shows_warning(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init shows warning when keyring fails."""
        monkeypatch.setattr("dataing_cli.config._set_keyring_credential", lambda x: False)

        with patch("dataing_sdk.DataingClient") as mock_client:
            mock_client.return_value.health.return_value = None

            result = runner.invoke(
                app,
                [
                    "init",
                    "--url",
                    "http://localhost:8000",
                    "--api-key",
                    "test_key",
                ],
            )

        assert result.exit_code == 0
        assert "Warning" in result.output or "less secure" in result.output.lower()


class TestStatusCommand:
    """Tests for the status command."""

    def test_status_connected(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test status when connected."""
        mock_client_patch.health.return_value = None

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Connected" in result.output or "dataing CLI" in result.output

    def test_status_disconnected(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test status when disconnected."""
        mock_client_patch.health.side_effect = ConnectionError("Connection refused")

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 1
        assert "Disconnected" in result.output or "Connection refused" in result.output

    def test_status_not_configured(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test status when not configured."""
        monkeypatch.setattr("dataing_cli.config._get_keyring_credential", lambda: None)

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 1
        assert "No API key" in result.output or "Not configured" in result.output

    def test_status_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test status with --json flag."""
        mock_client_patch.health.return_value = None

        result = runner.invoke(app, ["--json", "status"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["connected"] is True
        assert "url" in data
        assert "api_key_configured" in data

    def test_status_json_output_error(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test status with --json flag when error occurs."""
        mock_client_patch.health.side_effect = ConnectionError("Network error")

        result = runner.invoke(app, ["--json", "status"])

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["connected"] is False
        assert "error" in data


class TestVersionOption:
    """Tests for --version option."""

    def test_version_shows_version(self, runner: CliRunner) -> None:
        """Test --version shows version string."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "dataing-cli" in result.output


class TestGlobalOptions:
    """Tests for global options."""

    def test_help_shows_subcommands(self, runner: CliRunner) -> None:
        """Test help shows available subcommands."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "run" in result.output
        assert "ds" in result.output
        assert "init" in result.output
        assert "status" in result.output
