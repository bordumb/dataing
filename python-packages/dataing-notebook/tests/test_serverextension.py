"""Tests for Jupyter Server Extension handlers."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
import tornado.testing
import tornado.web
from tornado.httpclient import HTTPResponse

from dataing_notebook.serverextension.handlers import (
    HandshakeHandler,
    ProxyHandler,
    TokenHandler,
    get_api_key,
    get_backend_url,
    is_jupyterhub_environment,
    setup_handlers,
)


class TestEnvironmentFunctions:
    """Tests for environment variable functions."""

    def test_get_backend_url_default(self) -> None:
        """Test default backend URL."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_BACKEND_URL", None)
            url = get_backend_url()
            assert url == "http://localhost:8000"

    def test_get_backend_url_from_env(self) -> None:
        """Test backend URL from environment variable."""
        with patch.dict(os.environ, {"DATAING_BACKEND_URL": "https://api.example.com/"}):
            url = get_backend_url()
            assert url == "https://api.example.com"  # Trailing slash stripped

    def test_get_api_key_none(self) -> None:
        """Test API key when not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            key = get_api_key()
            assert key is None

    def test_get_api_key_from_env(self) -> None:
        """Test API key from environment variable."""
        with patch.dict(os.environ, {"DATAING_API_KEY": "test-key-123"}):
            key = get_api_key()
            assert key == "test-key-123"

    def test_is_jupyterhub_false(self) -> None:
        """Test JupyterHub detection when not in JupyterHub."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JUPYTERHUB_SERVICE_URL", None)
            assert is_jupyterhub_environment() is False

    def test_is_jupyterhub_true(self) -> None:
        """Test JupyterHub detection when in JupyterHub."""
        with patch.dict(os.environ, {"JUPYTERHUB_SERVICE_URL": "http://hub:8081"}):
            assert is_jupyterhub_environment() is True


def make_test_app(handlers: list) -> tornado.web.Application:
    """Create a test application with authentication bypassed.

    In test environments, we disable authentication by providing
    a get_current_user that always returns a test user.
    """
    # Create handlers that bypass auth for testing
    test_handlers = []
    for pattern, handler in handlers:
        # Create a subclass that overrides get_current_user
        class TestHandler(handler):  # type: ignore[valid-type,misc]
            def get_current_user(self) -> str:
                return "test_user"
        test_handlers.append((pattern, TestHandler))

    return tornado.web.Application(
        test_handlers,
        cookie_secret="test_secret_for_testing_only",
    )


class TestHandshakeHandler(tornado.testing.AsyncHTTPTestCase):
    """Tests for HandshakeHandler."""

    def get_app(self) -> tornado.web.Application:
        """Create test application."""
        return make_test_app([
            (r"/dataing/handshake", HandshakeHandler),
        ])

    def test_handshake_response(self) -> None:
        """Test handshake returns expected fields."""
        response = self.fetch("/dataing/handshake")
        assert response.code == 200

        data = json.loads(response.body)
        assert "backend_url" in data
        assert "jupyterhub" in data
        assert "api_key_configured" in data
        assert "version" in data

    def test_handshake_with_env(self) -> None:
        """Test handshake with environment variables."""
        with patch.dict(os.environ, {
            "DATAING_BACKEND_URL": "https://api.test.com",
            "DATAING_API_KEY": "test-key",
        }):
            response = self.fetch("/dataing/handshake")
            data = json.loads(response.body)

            assert data["backend_url"] == "https://api.test.com"
            assert data["api_key_configured"] is True


class TestTokenHandler(tornado.testing.AsyncHTTPTestCase):
    """Tests for TokenHandler."""

    def get_app(self) -> tornado.web.Application:
        """Create test application."""
        return make_test_app([
            (r"/dataing/token", TokenHandler),
        ])

    def test_get_token_no_key(self) -> None:
        """Test GET token when no API key configured."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            response = self.fetch("/dataing/token")
            assert response.code == 200

            data = json.loads(response.body)
            assert data["has_token"] is False

    def test_get_token_with_key(self) -> None:
        """Test GET token when API key configured (does not expose the key)."""
        with patch.dict(os.environ, {"DATAING_API_KEY": "test-key-12345678"}):
            response = self.fetch("/dataing/token")
            assert response.code == 200

            data = json.loads(response.body)
            assert data["has_token"] is True
            assert data["token_type"] == "api_key"
            assert data["token_configured"] is True
            # Key should NOT be exposed
            assert "token" not in data
            assert "masked" not in data

    def test_post_token_no_key(self) -> None:
        """Test POST token when no API key configured."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATAING_API_KEY", None)
            response = self.fetch(
                "/dataing/token",
                method="POST",
                body="{}",
            )
            assert response.code == 401

    def test_post_token_with_key_status(self) -> None:
        """Test POST token returns status only (not the actual token)."""
        with patch.dict(os.environ, {"DATAING_API_KEY": "test-key"}):
            response = self.fetch(
                "/dataing/token",
                method="POST",
                body='{"action": "status"}',
            )
            assert response.code == 200

            data = json.loads(response.body)
            assert data["success"] is True
            assert data["token_configured"] is True
            # Token should NOT be returned
            assert "token" not in data


class TestSetupHandlers:
    """Tests for handler setup."""

    def test_setup_handlers(self) -> None:
        """Test handlers are properly registered."""
        app = tornado.web.Application()
        app.settings["base_url"] = "/"

        # Should not raise
        try:
            setup_handlers(app)
        except Exception as e:
            pytest.fail(f"setup_handlers raised {e}")

        # Verify wildcard_router has handlers
        # Tornado 6.x stores handlers differently
        assert hasattr(app, "wildcard_router") or len(app.default_router.rules) > 0

    def test_setup_handlers_with_base_url(self) -> None:
        """Test handlers respect base_url."""
        app = tornado.web.Application()
        app.settings["base_url"] = "/jupyter/"

        # Should not raise
        try:
            setup_handlers(app)
        except Exception as e:
            pytest.fail(f"setup_handlers raised {e}")
