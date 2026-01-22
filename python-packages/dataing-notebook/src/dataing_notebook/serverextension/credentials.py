"""Credential storage for Dataing server extension.

Supports three credential storage modes:
- OS Keychain: Permanent storage via `keyring` library
- Environment Variable: Uses DATAING_API_KEY env var
- Session-Only: In-memory storage, cleared on server restart

Security notes:
- Actual credential values are NEVER returned via API
- Credentials are NEVER logged, even in debug mode
- Session-only credentials are stored only in server extension memory
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Constants
ENV_API_KEY = "DATAING_API_KEY"
KEYRING_SERVICE = "dataing-notebook"
KEYRING_USERNAME = "api_key"


class CredentialMode(Enum):
    """Available credential storage modes."""

    KEYCHAIN = "keychain"
    ENV_VAR = "env_var"
    SESSION_ONLY = "session"


@dataclass
class CredentialStatus:
    """Current credential status (never contains actual key)."""

    mode: CredentialMode
    stored: bool
    explanation: str


# In-memory session storage (cleared on server restart)
_session_credential: str | None = None


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


def detect_credential_mode() -> tuple[CredentialMode, str]:
    """Detect best available credential mode.

    Returns:
        Tuple of (mode, explanation_message).
    """
    # Check env var first (always works)
    if os.environ.get(ENV_API_KEY):
        return (
            CredentialMode.ENV_VAR,
            "Using API key from DATAING_API_KEY environment variable",
        )

    # Check keyring availability
    if _is_keyring_available():
        return (
            CredentialMode.KEYCHAIN,
            "API key will be stored securely in your OS keychain",
        )

    # Fallback to session-only
    return (
        CredentialMode.SESSION_ONLY,
        "API key will be stored in memory only (cleared on server restart). "
        "Tip: Set DATAING_API_KEY environment variable for persistent auth.",
    )


def get_credential_status() -> CredentialStatus:
    """Get current credential status.

    Returns:
        CredentialStatus with mode, stored flag, and explanation.
    """
    mode, explanation = detect_credential_mode()

    # Check if credential is stored
    stored = False

    if mode == CredentialMode.ENV_VAR:
        stored = bool(os.environ.get(ENV_API_KEY))
    elif mode == CredentialMode.KEYCHAIN:
        stored = _get_keychain_credential() is not None
    elif mode == CredentialMode.SESSION_ONLY:
        stored = _session_credential is not None

    return CredentialStatus(mode=mode, stored=stored, explanation=explanation)


def _get_keychain_credential() -> str | None:
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


def _set_keychain_credential(api_key: str) -> bool:
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
        logger.info("credential_stored_keychain")
        return True
    except Exception:
        logger.warning("credential_store_keychain_failed")
        return False


def _delete_keychain_credential() -> bool:
    """Delete credential from OS keychain.

    Returns:
        True if deleted (or didn't exist).
    """
    if not _is_keyring_available():
        return True

    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        logger.info("credential_deleted_keychain")
        return True
    except Exception:
        # May not exist, that's fine
        return True


def store_credential(api_key: str, persist: bool = True) -> CredentialStatus:
    """Store a credential.

    Args:
        api_key: The API key to store.
        persist: If True, try to use keychain. If False, use session-only.

    Returns:
        Updated CredentialStatus.
    """
    global _session_credential

    mode, _ = detect_credential_mode()

    if not persist:
        # User explicitly requested session-only
        _session_credential = api_key
        logger.info("credential_stored_session")
        return CredentialStatus(
            mode=CredentialMode.SESSION_ONLY,
            stored=True,
            explanation="API key stored in memory only (session)",
        )

    if mode == CredentialMode.ENV_VAR:
        # Can't programmatically set env var, store in session
        _session_credential = api_key
        logger.info("credential_stored_session_env_mode")
        return CredentialStatus(
            mode=CredentialMode.ENV_VAR,
            stored=True,
            explanation="API key stored in session (env var mode - use env var for persistence)",
        )

    if mode == CredentialMode.KEYCHAIN:
        if _set_keychain_credential(api_key):
            return CredentialStatus(
                mode=CredentialMode.KEYCHAIN,
                stored=True,
                explanation="API key stored in OS keychain",
            )
        # Keychain failed, fall back to session
        _session_credential = api_key
        return CredentialStatus(
            mode=CredentialMode.SESSION_ONLY,
            stored=True,
            explanation="Keychain storage failed, stored in memory only",
        )

    # Session-only mode
    _session_credential = api_key
    logger.info("credential_stored_session")
    return CredentialStatus(
        mode=CredentialMode.SESSION_ONLY,
        stored=True,
        explanation="API key stored in memory only",
    )


def get_credential() -> str | None:
    """Get the active credential using precedence order.

    Precedence (highest first):
    1. Session-only memory store (if set this session)
    2. OS keyring
    3. Environment variable

    Returns:
        API key or None if not configured.
    """
    global _session_credential

    # 1. Session-only (highest precedence if set)
    if _session_credential:
        return _session_credential

    # 2. OS keyring
    keychain_cred = _get_keychain_credential()
    if keychain_cred:
        return keychain_cred

    # 3. Environment variable
    env_cred = os.environ.get(ENV_API_KEY)
    if env_cred:
        return env_cred

    return None


def delete_credential() -> CredentialStatus:
    """Delete stored credentials (both keychain and session).

    Returns:
        Updated CredentialStatus.
    """
    global _session_credential

    # Clear session credential
    _session_credential = None

    # Clear keychain credential
    _delete_keychain_credential()

    logger.info("credentials_cleared")

    # Return current status
    return get_credential_status()
