"""Tests for config module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from dataing_cli.config import (
    ConfigError,
    get_api_key,
    get_base_url,
    get_config_dir,
    get_config_path,
    load_config,
    save_api_key,
    save_config,
)


class TestGetConfigDir:
    """Tests for get_config_dir()."""

    def test_returns_xdg_config_home_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that XDG_CONFIG_HOME is respected."""
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        assert get_config_dir() == Path("/custom/config/dataing")

    def test_returns_default_when_xdg_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default config dir when XDG_CONFIG_HOME is not set."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        expected = Path.home() / ".config" / "dataing"
        assert get_config_dir() == expected


class TestGetConfigPath:
    """Tests for get_config_path()."""

    def test_returns_config_toml_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test config file path."""
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        assert get_config_path() == Path("/custom/config/dataing/config.toml")


class TestLoadConfig:
    """Tests for load_config()."""

    def test_returns_empty_dict_when_file_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that empty dict is returned when config file doesn't exist."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert load_config() == {}

    def test_loads_toml_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test loading a valid TOML config file."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config_dir = tmp_path / "dataing"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text('api_url = "https://example.com"\nverbose = true\n')

        config = load_config()
        assert config["api_url"] == "https://example.com"
        assert config["verbose"] is True


class TestSaveConfig:
    """Tests for save_config()."""

    def test_creates_config_dir_and_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that config directory and file are created."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_config({"api_url": "https://test.com"})

        config_file = tmp_path / "dataing" / "config.toml"
        assert config_file.exists()
        content = config_file.read_text()
        assert 'api_url = "https://test.com"' in content

    def test_merges_with_existing_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that new config is merged with existing."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config_dir = tmp_path / "dataing"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text('existing_key = "value"\n')

        save_config({"new_key": "new_value"})

        config = load_config()
        assert config["existing_key"] == "value"
        assert config["new_key"] == "new_value"


class TestGetApiKey:
    """Tests for get_api_key() - credential precedence."""

    def test_flag_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that flag has highest precedence."""
        monkeypatch.setenv("DATAING_API_KEY", "env_key")
        assert get_api_key(from_flag="flag_key") == "flag_key"

    def test_env_var_when_no_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test env var is used when no flag provided."""
        monkeypatch.setenv("DATAING_API_KEY", "env_key")
        assert get_api_key() == "env_key"

    def test_keyring_when_no_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test keyring is used when env var not set."""
        monkeypatch.delenv("DATAING_API_KEY", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        with patch("dataing_cli.config._is_keyring_available", return_value=True):
            with patch("dataing_cli.config._get_keyring_credential", return_value="keyring_key"):
                assert get_api_key() == "keyring_key"

    def test_config_file_when_no_keyring(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test config file is used as fallback."""
        monkeypatch.delenv("DATAING_API_KEY", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        # Create config with api_key
        config_dir = tmp_path / "dataing"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text('api_key = "config_key"\n')

        with patch("dataing_cli.config._get_keyring_credential", return_value=None):
            assert get_api_key() == "config_key"

    def test_returns_none_when_not_configured(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test None is returned when nothing configured."""
        monkeypatch.delenv("DATAING_API_KEY", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        with patch("dataing_cli.config._get_keyring_credential", return_value=None):
            assert get_api_key() is None


class TestGetBaseUrl:
    """Tests for get_base_url()."""

    def test_flag_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test flag has highest precedence."""
        monkeypatch.setenv("DATAING_BASE_URL", "https://env.com")
        assert get_base_url(from_flag="https://flag.com") == "https://flag.com"

    def test_env_var_when_no_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test env var is used when no flag."""
        monkeypatch.setenv("DATAING_BASE_URL", "https://env.com")
        assert get_base_url() == "https://env.com"

    def test_config_when_no_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test config file is used when no env var."""
        monkeypatch.delenv("DATAING_BASE_URL", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        config_dir = tmp_path / "dataing"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text('api_url = "https://config.com"\n')

        assert get_base_url() == "https://config.com"

    def test_default_when_nothing_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test default URL is returned."""
        monkeypatch.delenv("DATAING_BASE_URL", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert get_base_url() == "http://localhost:8000"


class TestSaveApiKey:
    """Tests for save_api_key()."""

    def test_saves_to_keyring_by_default(self) -> None:
        """Test keyring is used by default."""
        with patch("dataing_cli.config._set_keyring_credential", return_value=True) as mock:
            success, msg = save_api_key("test_key")
            assert success
            assert "keychain" in msg.lower()
            mock.assert_called_once_with("test_key")

    def test_falls_back_to_config_when_keyring_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fallback to config when keyring fails."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        with patch("dataing_cli.config._set_keyring_credential", return_value=False):
            success, msg = save_api_key("test_key")
            assert success
            assert "config file" in msg.lower()

            # Check it was written to config
            config = load_config()
            assert config["api_key"] == "test_key"

    def test_saves_to_config_when_use_keyring_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test explicit save to config file."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        success, msg = save_api_key("test_key", use_keyring=False)
        assert success
        assert "config file" in msg.lower()

        config = load_config()
        assert config["api_key"] == "test_key"


class TestGetClient:
    """Tests for get_client()."""

    def test_raises_config_error_when_no_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test ConfigError is raised when no API key configured."""
        monkeypatch.delenv("DATAING_API_KEY", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from dataing_cli.config import get_client

        with patch("dataing_cli.config._get_keyring_credential", return_value=None):
            with pytest.raises(ConfigError) as exc_info:
                get_client()
            assert "No API key" in str(exc_info.value)

    def test_returns_client_when_configured(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test client is returned when API key is configured."""
        monkeypatch.setenv("DATAING_API_KEY", "test_key")

        from dataing_cli.config import get_client

        with patch("dataing_sdk.DataingClient") as mock_client:
            get_client()
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args[1]
            assert call_kwargs["api_key"] == "test_key"
