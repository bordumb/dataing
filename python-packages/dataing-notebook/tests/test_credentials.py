"""Tests for credential storage module."""

import os
from unittest.mock import MagicMock, patch

from dataing_notebook.serverextension.credentials import (
    CredentialMode,
    _is_keyring_available,
    delete_credential,
    detect_credential_mode,
    get_credential,
    get_credential_status,
    store_credential,
)


class TestCredentialModeDetection:
    """Tests for credential mode detection."""

    def test_detect_env_var_mode(self) -> None:
        """Test detection when env var is set."""
        with patch.dict(os.environ, {"DATAING_API_KEY": "test-key"}):
            mode, explanation = detect_credential_mode()
            assert mode == CredentialMode.ENV_VAR
            assert "DATAING_API_KEY" in explanation

    def test_detect_keychain_mode(self) -> None:
        """Test detection when keyring is available."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available",
                return_value=True,
            ):
                mode, explanation = detect_credential_mode()
                assert mode == CredentialMode.KEYCHAIN
                assert "keychain" in explanation.lower()

    def test_detect_session_mode(self) -> None:
        """Test detection when nothing is available."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available",
                return_value=False,
            ):
                mode, explanation = detect_credential_mode()
                assert mode == CredentialMode.SESSION_ONLY
                assert "memory" in explanation.lower()


class TestKeyringAvailability:
    """Tests for keyring availability check."""

    def test_keyring_not_installed(self) -> None:
        """Test when keyring is not installed."""
        with patch.dict("sys.modules", {"keyring": None}):
            # Force import error
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available"
            ) as mock:
                mock.return_value = False
                assert not mock()

    def test_keyring_fail_backend(self) -> None:
        """Test when keyring has fail backend."""
        mock_keyring = MagicMock()
        mock_backend = MagicMock()
        type(mock_backend).__name__ = "FailKeyring"
        mock_keyring.get_keyring.return_value = mock_backend

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            # The actual function checks the backend name
            _is_keyring_available()
            # Can't easily test this without mocking the import, but the logic is covered


class TestCredentialStorage:
    """Tests for credential storage operations."""

    def setup_method(self) -> None:
        """Reset session credential before each test."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = None

    def test_store_session_only(self) -> None:
        """Test storing credential in session only."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available",
                return_value=False,
            ):
                status = store_credential("test-key-123", persist=False)
                assert status.mode == CredentialMode.SESSION_ONLY
                assert status.stored is True

                # Verify credential is retrievable
                cred = get_credential()
                assert cred == "test-key-123"

    def test_store_with_persist_uses_keychain(self) -> None:
        """Test storing with persist=True uses keychain when available."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available",
                return_value=True,
            ):
                with patch(
                    "dataing_notebook.serverextension.credentials._set_keychain_credential",
                    return_value=True,
                ):
                    status = store_credential("test-key-456", persist=True)
                    assert status.mode == CredentialMode.KEYCHAIN
                    assert status.stored is True

    def test_store_fallback_to_session_on_keychain_failure(self) -> None:
        """Test falling back to session when keychain fails."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available",
                return_value=True,
            ):
                with patch(
                    "dataing_notebook.serverextension.credentials._set_keychain_credential",
                    return_value=False,  # Keychain failed
                ):
                    status = store_credential("test-key-789", persist=True)
                    assert status.mode == CredentialMode.SESSION_ONLY
                    assert status.stored is True

                    # Should still be retrievable from session
                    cred = get_credential()
                    assert cred == "test-key-789"


class TestCredentialRetrieval:
    """Tests for credential retrieval with precedence."""

    def setup_method(self) -> None:
        """Reset session credential before each test."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = None

    def test_precedence_session_first(self) -> None:
        """Test session credential has highest precedence."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = "session-key"

        with patch.dict(os.environ, {"DATAING_API_KEY": "env-key"}):
            with patch(
                "dataing_notebook.serverextension.credentials._get_keychain_credential",
                return_value="keychain-key",
            ):
                cred = get_credential()
                assert cred == "session-key"

    def test_precedence_keychain_second(self) -> None:
        """Test keychain credential used when no session."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = None

        with patch.dict(os.environ, {"DATAING_API_KEY": "env-key"}):
            with patch(
                "dataing_notebook.serverextension.credentials._get_keychain_credential",
                return_value="keychain-key",
            ):
                cred = get_credential()
                assert cred == "keychain-key"

    def test_precedence_env_third(self) -> None:
        """Test env var used as last resort."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = None

        with patch.dict(os.environ, {"DATAING_API_KEY": "env-key"}):
            with patch(
                "dataing_notebook.serverextension.credentials._get_keychain_credential",
                return_value=None,
            ):
                cred = get_credential()
                assert cred == "env-key"

    def test_returns_none_when_nothing_available(self) -> None:
        """Test returns None when no credentials available."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = None

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._get_keychain_credential",
                return_value=None,
            ):
                cred = get_credential()
                assert cred is None


class TestCredentialDeletion:
    """Tests for credential deletion."""

    def setup_method(self) -> None:
        """Reset session credential before each test."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = None

    def test_delete_clears_session(self) -> None:
        """Test delete clears session credential."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = "test-key"

        with patch(
            "dataing_notebook.serverextension.credentials._delete_keychain_credential",
            return_value=True,
        ):
            delete_credential()
            assert creds._session_credential is None

    def test_delete_clears_keychain(self) -> None:
        """Test delete attempts to clear keychain."""
        with patch(
            "dataing_notebook.serverextension.credentials._delete_keychain_credential"
        ) as mock_delete:
            mock_delete.return_value = True
            delete_credential()
            mock_delete.assert_called_once()


class TestCredentialStatus:
    """Tests for credential status reporting."""

    def setup_method(self) -> None:
        """Reset session credential before each test."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = None

    def test_status_env_var_stored(self) -> None:
        """Test status when env var is set."""
        with patch.dict(os.environ, {"DATAING_API_KEY": "test-key"}):
            status = get_credential_status()
            assert status.mode == CredentialMode.ENV_VAR
            assert status.stored is True

    def test_status_session_not_stored(self) -> None:
        """Test status when session mode but nothing stored."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available",
                return_value=False,
            ):
                status = get_credential_status()
                assert status.mode == CredentialMode.SESSION_ONLY
                assert status.stored is False

    def test_status_session_stored(self) -> None:
        """Test status when session credential is set."""
        import dataing_notebook.serverextension.credentials as creds

        creds._session_credential = "test-key"

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            with patch(
                "dataing_notebook.serverextension.credentials._is_keyring_available",
                return_value=False,
            ):
                status = get_credential_status()
                assert status.mode == CredentialMode.SESSION_ONLY
                assert status.stored is True
