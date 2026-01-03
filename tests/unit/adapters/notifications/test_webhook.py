"""Unit tests for WebhookNotifier."""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest

from dataing.adapters.notifications.webhook import WebhookConfig, WebhookNotifier


class TestWebhookNotifier:
    """Tests for WebhookNotifier."""

    @pytest.fixture
    def config(self) -> WebhookConfig:
        """Return a webhook configuration."""
        return WebhookConfig(
            url="https://example.com/webhook",
            secret="test_secret",
            timeout_seconds=10,
        )

    @pytest.fixture
    def notifier(self, config: WebhookConfig) -> WebhookNotifier:
        """Return a webhook notifier."""
        return WebhookNotifier(config)

    def test_init(self, notifier: WebhookNotifier, config: WebhookConfig) -> None:
        """Test notifier initialization."""
        assert notifier.config == config

    async def test_send_success(self, notifier: WebhookNotifier) -> None:
        """Test successful webhook delivery."""
        mock_response = AsyncMock()
        mock_response.is_success = True
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await notifier.send(
                "investigation.completed",
                {"investigation_id": "123"},
            )

            assert result is True
            mock_client.post.assert_called_once()

    async def test_send_includes_signature(self, notifier: WebhookNotifier) -> None:
        """Test that webhook includes HMAC signature when secret is set."""
        mock_response = AsyncMock()
        mock_response.is_success = True

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            await notifier.send("test.event", {"data": "value"})

            call_kwargs = mock_client.post.call_args.kwargs
            headers = call_kwargs["headers"]

            assert "X-Webhook-Signature" in headers
            assert headers["X-Webhook-Signature"].startswith("sha256=")

    async def test_send_failure(self, notifier: WebhookNotifier) -> None:
        """Test webhook delivery failure."""
        mock_response = AsyncMock()
        mock_response.is_success = False
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await notifier.send("test.event", {})

            assert result is False

    async def test_send_timeout(self, notifier: WebhookNotifier) -> None:
        """Test webhook timeout handling."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.TimeoutException("Timeout")
            mock_client_class.return_value = mock_client

            result = await notifier.send("test.event", {})

            assert result is False

    async def test_send_request_error(self, notifier: WebhookNotifier) -> None:
        """Test webhook request error handling."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.RequestError("Connection failed")
            mock_client_class.return_value = mock_client

            result = await notifier.send("test.event", {})

            assert result is False

    def test_verify_signature_valid(self) -> None:
        """Test signature verification with valid signature."""
        body = b'{"test": "data"}'
        secret = "test_secret"
        signature = "sha256=" + hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        result = WebhookNotifier.verify_signature(body, signature, secret)

        assert result is True

    def test_verify_signature_invalid(self) -> None:
        """Test signature verification with invalid signature."""
        body = b'{"test": "data"}'
        secret = "test_secret"
        signature = "sha256=invalid_signature"

        result = WebhookNotifier.verify_signature(body, signature, secret)

        assert result is False

    def test_verify_signature_wrong_prefix(self) -> None:
        """Test signature verification with wrong prefix."""
        body = b'{"test": "data"}'
        secret = "test_secret"
        signature = "md5=some_signature"

        result = WebhookNotifier.verify_signature(body, signature, secret)

        assert result is False


class TestWebhookConfig:
    """Tests for WebhookConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = WebhookConfig(url="https://example.com")

        assert config.url == "https://example.com"
        assert config.secret is None
        assert config.timeout_seconds == 30
