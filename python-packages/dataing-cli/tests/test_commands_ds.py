"""Tests for datasource (ds) commands."""

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


class TestDsListCommand:
    """Tests for ds list command."""

    def test_ds_list_shows_table(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_datasources: list[MagicMock],
    ) -> None:
        """Test ds list shows datasources in table format."""
        mock_client_patch.list_datasources.return_value = sample_datasources

        result = runner.invoke(app, ["ds", "list"])

        assert result.exit_code == 0
        assert "prod-db" in result.output
        assert "staging-db" in result.output
        assert "postgres" in result.output

    def test_ds_list_empty(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test ds list when no datasources exist."""
        mock_client_patch.list_datasources.return_value = []

        result = runner.invoke(app, ["ds", "list"])

        assert result.exit_code == 0
        assert "No datasources" in result.output

    def test_ds_list_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_datasources: list[MagicMock],
    ) -> None:
        """Test ds list with --json flag."""
        mock_client_patch.list_datasources.return_value = sample_datasources

        result = runner.invoke(app, ["--json", "ds", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["id"] == "ds-abc123456789"
        assert data[0]["name"] == "prod-db"


class TestDsTestCommand:
    """Tests for ds test command."""

    def test_ds_test_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test ds test with successful connection."""
        mock_client_patch.test_datasource.return_value = MagicMock(
            success=True, latency_ms=50, error=None
        )

        result = runner.invoke(app, ["ds", "test", "ds-123"])

        assert result.exit_code == 0
        assert "Connection successful" in result.output
        assert "50ms" in result.output

    def test_ds_test_failure(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test ds test with failed connection."""
        mock_client_patch.test_datasource.return_value = MagicMock(
            success=False, latency_ms=None, error="Connection refused"
        )

        result = runner.invoke(app, ["ds", "test", "ds-123"])

        assert result.exit_code == 1
        assert "Connection failed" in result.output
        assert "Connection refused" in result.output

    def test_ds_test_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test ds test with --json flag."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.latency_ms = 50
        mock_result.error = None
        mock_result.model_dump.return_value = {
            "success": True,
            "latency_ms": 50,
            "error": None,
        }
        mock_client_patch.test_datasource.return_value = mock_result

        result = runner.invoke(app, ["--json", "ds", "test", "ds-123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["latency_ms"] == 50


class TestDsAttachCommand:
    """Tests for ds attach command."""

    def test_ds_attach_success(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_datasources: list[MagicMock],
    ) -> None:
        """Test ds attach sets default datasource."""
        mock_client_patch.list_datasources.return_value = sample_datasources

        result = runner.invoke(app, ["ds", "attach", "ds-abc123456789"])

        assert result.exit_code == 0
        assert "Default datasource set" in result.output
        assert "prod-db" in result.output

        # Check config was updated
        config_file = configured_env / "config.toml"
        content = config_file.read_text()
        assert "ds-abc123456789" in content

    def test_ds_attach_not_found(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_datasources: list[MagicMock],
    ) -> None:
        """Test ds attach with non-existent datasource."""
        mock_client_patch.list_datasources.return_value = sample_datasources

        result = runner.invoke(app, ["ds", "attach", "ds-nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestDsSchemaCommand:
    """Tests for ds schema command."""

    def test_ds_schema_shows_tables(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_schema: MagicMock,
    ) -> None:
        """Test ds schema shows table and columns."""
        mock_client_patch.get_schema.return_value = sample_schema

        result = runner.invoke(app, ["ds", "schema", "ds-123"])

        assert result.exit_code == 0
        assert "users" in result.output
        assert "id" in result.output
        assert "name" in result.output
        assert "integer" in result.output
        assert "varchar" in result.output

    def test_ds_schema_uses_default_datasource(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_schema: MagicMock,
    ) -> None:
        """Test ds schema uses default when no arg provided."""
        mock_client_patch.get_schema.return_value = sample_schema

        result = runner.invoke(app, ["ds", "schema"])

        assert result.exit_code == 0
        mock_client_patch.get_schema.assert_called_once_with("ds-123")

    def test_ds_schema_no_datasource(
        self,
        runner: CliRunner,
        mock_config_dir: Path,
        mock_client_patch: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test ds schema when no datasource specified or default."""
        # Write minimal config without default datasource
        config_file = mock_config_dir / "config.toml"
        config_file.write_text('api_key = "test_key"\n')
        monkeypatch.setattr("dataing_cli.config._get_keyring_credential", lambda: None)

        result = runner.invoke(app, ["ds", "schema"])

        assert result.exit_code == 1
        assert "No datasource specified" in result.output

    def test_ds_schema_with_table_filter(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_schema: MagicMock,
    ) -> None:
        """Test ds schema with --table filter."""
        mock_client_patch.get_schema.return_value = sample_schema

        result = runner.invoke(app, ["ds", "schema", "ds-123", "--table", "users"])

        assert result.exit_code == 0
        assert "users" in result.output

    def test_ds_schema_empty(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
    ) -> None:
        """Test ds schema when no tables exist."""
        mock_client_patch.get_schema.return_value = MagicMock(tables=[])

        result = runner.invoke(app, ["ds", "schema", "ds-123"])

        assert result.exit_code == 0
        assert "No tables found" in result.output

    def test_ds_schema_json_output(
        self,
        runner: CliRunner,
        configured_env: Path,
        mock_client_patch: MagicMock,
        sample_schema: MagicMock,
    ) -> None:
        """Test ds schema with --json flag."""
        mock_client_patch.get_schema.return_value = sample_schema

        result = runner.invoke(app, ["--json", "ds", "schema", "ds-123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tables" in data
        assert len(data["tables"]) == 1
        assert data["tables"][0]["name"] == "users"
