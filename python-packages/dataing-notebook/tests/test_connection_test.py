"""Tests for Connection Test handler."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import tornado.testing
import tornado.web

from dataing_notebook.serverextension.handlers import ConnectionTestHandler


def make_test_app(handlers: list) -> tornado.web.Application:
    """Create a test application with authentication bypassed."""
    test_handlers = []
    for pattern, handler in handlers:

        class TestHandler(handler):  # type: ignore[valid-type,misc]
            def get_current_user(self) -> str:
                return "test_user"

        test_handlers.append((pattern, TestHandler))

    return tornado.web.Application(
        test_handlers,
        cookie_secret="test_secret_for_testing_only",
    )


class TestConnectionTestHandler(tornado.testing.AsyncHTTPTestCase):
    """Tests for ConnectionTestHandler."""

    def get_app(self) -> tornado.web.Application:
        """Create test application."""
        return make_test_app(
            [
                (r"/dataing/connection/test", ConnectionTestHandler),
            ]
        )

    def test_missing_base_url(self) -> None:
        """Test error when base_url is missing."""
        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"api_key": "test-key"}',
        )
        assert response.code == 400
        data = json.loads(response.body)
        assert data["success"] is False
        assert "base_url" in data["error"]

    def test_missing_api_key(self) -> None:
        """Test error when api_key is missing."""
        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://localhost:8000"}',
        )
        assert response.code == 400
        data = json.loads(response.body)
        assert data["success"] is False
        assert "api_key" in data["error"]

    def test_invalid_json(self) -> None:
        """Test error on invalid JSON body."""
        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body="not json",
        )
        assert response.code == 400
        data = json.loads(response.body)
        assert data["success"] is False
        assert "Invalid JSON" in data["error"]

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_successful_connection(self, mock_client_class: MagicMock) -> None:
        """Test successful connection test."""
        mock_response = MagicMock()
        mock_response.code = 200

        mock_client = AsyncMock()
        mock_client.fetch.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://localhost:8000", "api_key": "valid-key"}',
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["success"] is True

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_invalid_api_key(self, mock_client_class: MagicMock) -> None:
        """Test connection with invalid API key."""
        mock_response = MagicMock()
        mock_response.code = 401

        mock_client = AsyncMock()
        mock_client.fetch.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://localhost:8000", "api_key": "invalid"}',
        )
        assert response.code == 200  # HTTP 200 but success=false
        data = json.loads(response.body)
        assert data["success"] is False
        assert "Invalid API key" in data["error"]

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_forbidden_api_key(self, mock_client_class: MagicMock) -> None:
        """Test connection with forbidden API key."""
        mock_response = MagicMock()
        mock_response.code = 403

        mock_client = AsyncMock()
        mock_client.fetch.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://localhost:8000", "api_key": "forbidden"}',
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["success"] is False
        assert "not authorized" in data["error"]

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_backend_not_found(self, mock_client_class: MagicMock) -> None:
        """Test connection when backend returns 404."""
        mock_response = MagicMock()
        mock_response.code = 404

        mock_client = AsyncMock()
        mock_client.fetch.return_value = mock_response
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://wrong-url.example.com", "api_key": "key"}',
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["success"] is False
        assert "not found" in data["error"]

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_connection_refused(self, mock_client_class: MagicMock) -> None:
        """Test friendly error for connection refused."""
        mock_client = AsyncMock()
        mock_client.fetch.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://localhost:9999", "api_key": "key"}',
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["success"] is False
        assert "Cannot connect" in data["error"]

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_timeout(self, mock_client_class: MagicMock) -> None:
        """Test friendly error for timeout."""
        mock_client = AsyncMock()
        mock_client.fetch.side_effect = Exception("Operation timed out")
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://slow.example.com", "api_key": "key"}',
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["success"] is False
        assert "timed out" in data["error"]

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_dns_error(self, mock_client_class: MagicMock) -> None:
        """Test friendly error for DNS resolution failure."""
        mock_client = AsyncMock()
        mock_client.fetch.side_effect = Exception("nodename nor servname provided")
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "http://nonexistent.invalid", "api_key": "key"}',
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["success"] is False
        assert "hostname" in data["error"]

    @patch("tornado.httpclient.AsyncHTTPClient")
    def test_ssl_error(self, mock_client_class: MagicMock) -> None:
        """Test friendly error for SSL errors."""
        mock_client = AsyncMock()
        mock_client.fetch.side_effect = Exception("SSL certificate verify failed")
        mock_client_class.return_value = mock_client

        response = self.fetch(
            "/dataing/connection/test",
            method="POST",
            body='{"base_url": "https://badcert.example.com", "api_key": "key"}',
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["success"] is False
        assert "SSL" in data["error"]

    def test_url_normalization(self) -> None:
        """Test that trailing slashes are stripped from URL."""
        with patch("tornado.httpclient.AsyncHTTPClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.code = 200

            mock_client = AsyncMock()
            mock_client.fetch.return_value = mock_response
            mock_client_class.return_value = mock_client

            response = self.fetch(
                "/dataing/connection/test",
                method="POST",
                body='{"base_url": "http://localhost:8000/", "api_key": "key"}',
            )
            assert response.code == 200

            # Verify the URL was normalized
            call_args = mock_client.fetch.call_args
            called_url = call_args[0][0]
            assert called_url == "http://localhost:8000/health"
            assert "//" not in called_url.replace("http://", "")
