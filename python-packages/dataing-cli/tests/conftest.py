"""Shared test fixtures for CLI tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def runner() -> CliRunner:
    """Get a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a temporary config directory."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_dir = tmp_path / "dataing"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def mock_keyring(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the keyring module."""
    mock = MagicMock()
    mock.get_password.return_value = None
    mock.set_password.return_value = None
    monkeypatch.setattr("dataing_cli.config._is_keyring_available", lambda: True)
    monkeypatch.setattr("dataing_cli.config._get_keyring_credential", lambda: None)
    monkeypatch.setattr("dataing_cli.config._set_keyring_credential", lambda x: True)
    return mock


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock DataingClient."""
    client = MagicMock()
    client.health.return_value = None
    client.list_datasources.return_value = []
    client.test_datasource.return_value = MagicMock(success=True, latency_ms=50, error=None)
    client.get_schema.return_value = MagicMock(tables=[])
    client.run.return_value = MagicMock(run_id="run-123")
    client.stream_run.return_value = iter([])
    return client


@pytest.fixture
def mock_client_patch(
    mock_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[MagicMock, None, None]:
    """Patch get_client to return mock client."""

    def _get_client(*args: Any, **kwargs: Any) -> MagicMock:
        return mock_client

    monkeypatch.setattr("dataing_cli.config.get_client", _get_client)
    monkeypatch.setattr("dataing_cli.commands.ds.get_client", _get_client)
    monkeypatch.setattr("dataing_cli.commands.run.get_client", _get_client)
    yield mock_client


@pytest.fixture
def configured_env(
    mock_config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Set up a fully configured environment."""
    # Write config file
    config_file = mock_config_dir / "config.toml"
    config_file.write_text(
        'api_url = "http://localhost:8000"\n'
        'api_key = "test_api_key"\n'
        'default_datasource_id = "ds-123"\n'
        'default_datasource_name = "test-db"\n'
    )

    # Clear env vars that could interfere
    monkeypatch.delenv("DATAING_API_KEY", raising=False)
    monkeypatch.delenv("DATAING_BASE_URL", raising=False)

    return mock_config_dir


@pytest.fixture
def sample_datasources() -> list[MagicMock]:
    """Create sample datasources for testing."""
    ds1 = MagicMock()
    ds1.id = "ds-abc123456789"
    ds1.name = "prod-db"
    ds1.source_type = "postgres"
    ds1.status = "connected"
    ds1.model_dump.return_value = {
        "id": "ds-abc123456789",
        "name": "prod-db",
        "source_type": "postgres",
        "status": "connected",
    }

    ds2 = MagicMock()
    ds2.id = "ds-def987654321"
    ds2.name = "staging-db"
    ds2.source_type = "snowflake"
    ds2.status = "disconnected"
    ds2.model_dump.return_value = {
        "id": "ds-def987654321",
        "name": "staging-db",
        "source_type": "snowflake",
        "status": "disconnected",
    }

    return [ds1, ds2]


@pytest.fixture
def sample_schema() -> MagicMock:
    """Create sample schema for testing."""
    col1 = MagicMock()
    col1.name = "id"
    col1.data_type = "integer"
    col1.nullable = False

    col2 = MagicMock()
    col2.name = "name"
    col2.data_type = "varchar"
    col2.nullable = True

    table = MagicMock()
    table.name = "users"
    table.columns = [col1, col2]

    schema = MagicMock()
    schema.tables = [table]
    schema.model_dump.return_value = {
        "tables": [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "data_type": "integer", "nullable": False},
                    {"name": "name", "data_type": "varchar", "nullable": True},
                ],
            }
        ]
    }

    return schema
