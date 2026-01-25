"""Configuration and credential management for Dataing CLI.

Supports multiple credential storage modes:
- Command-line flag (highest precedence, for CI/CD)
- Environment variable (DATAING_API_KEY)
- OS Keychain via keyring library
- Config file (fallback, with security warning)
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dataing_sdk import DataingClient

logger = logging.getLogger(__name__)

# Constants
ENV_API_KEY = "DATAING_API_KEY"  # pragma: allowlist secret
ENV_BASE_URL = "DATAING_BASE_URL"
ENV_FRONTEND_URL = "DATAING_FRONTEND_URL"
KEYRING_SERVICE = "dataing-cli"
KEYRING_USERNAME = "api_key"
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_FRONTEND_URL = "http://localhost:3000"


class ConfigError(Exception):
    """Configuration error."""


def get_config_dir() -> Path:
    """Get XDG-compliant config directory.

    Returns:
        Path to config directory (~/.config/dataing or $XDG_CONFIG_HOME/dataing).
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "dataing"
    return Path.home() / ".config" / "dataing"


def get_config_path() -> Path:
    """Get config file path.

    Returns:
        Path to config.toml file.
    """
    return get_config_dir() / "config.toml"


def load_config() -> dict[str, Any]:
    """Load configuration from TOML file.

    Returns:
        Config dictionary, empty if file doesn't exist.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return {}
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to TOML file (non-sensitive settings only).

    Args:
        config: Configuration dictionary to save.
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = get_config_path()

    # Merge with existing config
    existing = load_config()
    existing.update(config)

    # Write TOML manually (no tomli-w dependency)
    lines = []
    for key, value in existing.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, int | float):
            lines.append(f"{key} = {value}")
        else:
            # Skip complex types
            continue

    with open(config_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _is_keyring_available() -> bool:
    """Check if keyring is available and functional.

    Returns:
        True if keyring can be used, False otherwise.
    """
    try:
        import keyring

        # Get the active keyring backend
        backend = keyring.get_keyring()
        # Check if it's a real backend (not fail backend)
        backend_name = type(backend).__name__.lower()
        # Common non-functional backends
        if "fail" in backend_name or "null" in backend_name:
            return False
        return True
    except Exception:
        return False


def _get_keyring_credential() -> str | None:
    """Get credential from OS keychain.

    Returns:
        API key or None if not stored.
    """
    if not _is_keyring_available():
        return None

    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None


def _set_keyring_credential(api_key: str) -> bool:
    """Store credential in OS keychain.

    Args:
        api_key: The API key to store.

    Returns:
        True if stored successfully.
    """
    if not _is_keyring_available():
        return False

    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
        logger.info("API key stored in OS keychain")
        return True
    except Exception:
        logger.warning("Failed to store API key in keychain")
        return False


def get_api_key(from_flag: str | None = None) -> str | None:
    """Get API key with precedence: flag > env > keyring > config.

    Args:
        from_flag: API key passed via command line flag.

    Returns:
        API key or None if not configured anywhere.
    """
    # 1. Command-line flag (highest precedence)
    if from_flag:
        return from_flag

    # 2. Environment variable
    if env_key := os.environ.get(ENV_API_KEY):
        return env_key

    # 3. OS keyring
    if kr_key := _get_keyring_credential():
        return kr_key

    # 4. Config file (lowest precedence)
    return load_config().get("api_key")


def save_api_key(key: str, use_keyring: bool = True) -> tuple[bool, str]:
    """Save API key to keyring or config.

    Args:
        key: API key to save.
        use_keyring: If True, try keyring first. If False, save to config.

    Returns:
        Tuple of (success, message).
    """
    if use_keyring:
        if _set_keyring_credential(key):
            return True, "API key stored in OS keychain"
        # Keyring failed, fall back to config
        logger.warning("Keyring unavailable, falling back to config file")

    # Save to config file
    config = load_config()
    config["api_key"] = key
    save_config(config)

    warning = (
        "API key stored in config file. "
        "This is less secure than keyring. "
        "Consider setting DATAING_API_KEY environment variable."
    )
    return True, warning


def get_base_url(from_flag: str | None = None) -> str:
    """Get base URL with precedence: flag > env > config > default.

    Args:
        from_flag: Base URL passed via command line flag.

    Returns:
        Base URL for the Dataing backend.
    """
    if from_flag:
        return from_flag
    if env_url := os.environ.get(ENV_BASE_URL):
        return env_url
    return load_config().get("api_url", DEFAULT_BASE_URL)


def get_frontend_url() -> str:
    """Get frontend URL with precedence: env > config > default.

    Returns:
        Frontend URL for the Dataing web app.
    """
    if env_url := os.environ.get(ENV_FRONTEND_URL):
        return env_url
    return load_config().get("frontend_url", DEFAULT_FRONTEND_URL)


def get_client(
    api_key: str | None = None,
    base_url: str | None = None,
) -> DataingClient:
    """Get configured SDK client.

    Args:
        api_key: Optional API key override.
        base_url: Optional base URL override.

    Returns:
        Configured DataingClient instance.

    Raises:
        ConfigError: If no API key is configured.
    """
    from dataing_sdk import DataingClient

    key = get_api_key(api_key)
    url = get_base_url(base_url)

    if not key:
        raise ConfigError(
            "No API key configured. "
            "Run 'dataing init' or set DATAING_API_KEY environment variable."
        )

    return DataingClient(base_url=url, api_key=key)


def get_default_datasource() -> tuple[str | None, str | None]:
    """Get default datasource from config.

    Returns:
        Tuple of (datasource_id, datasource_name) or (None, None).
    """
    config = load_config()
    return (
        config.get("default_datasource_id"),
        config.get("default_datasource_name"),
    )


def set_default_datasource(datasource_id: str, datasource_name: str | None = None) -> None:
    """Set default datasource in config.

    Args:
        datasource_id: Datasource ID to set as default.
        datasource_name: Optional display name.
    """
    config = load_config()
    config["default_datasource_id"] = datasource_id
    if datasource_name:
        config["default_datasource_name"] = datasource_name
    save_config(config)
