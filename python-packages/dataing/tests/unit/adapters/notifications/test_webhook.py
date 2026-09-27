"""Unit tests for WebhookNotifier."""

from __future__ import annotations

import functools
import hashlib
import hmac
import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import structlog

from dataing.adapters.notifications.webhook import WebhookConfig, WebhookNotifier
from dataing.telemetry.logging import configure_logging


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
        signature = (
            "sha256="
            + hmac.new(
                secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
        )

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


class TestWebhookNotifierLogRedaction:
    """Webhook logs must never contain the secret parts of the destination URL.

    Incoming-webhook URLs (Slack, Microsoft Teams, Discord) embed a bearer secret in
    the path, so only the scheme and host may be logged.
    """

    SECRET_URL = (
        "https://bot:SECRETPASS@hooks.example.com/services/T000/B000/SECRETTOKEN?sig=SECRETQUERY"
    )
    SECRET_PARTS = ("SECRETPASS", "SECRETTOKEN", "SECRETQUERY", "/services/")

    @pytest.fixture
    def mock_post(self) -> Iterator[AsyncMock]:
        """Patch httpx.AsyncClient and return the mocked ``post`` method."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client
            yield mock_client.post

    @pytest.fixture
    def restore_structlog_config(self) -> Iterator[None]:
        """Restore the global structlog config, which configure_logging replaces."""
        saved_config = structlog.get_config()
        yield
        structlog.configure(**saved_config)

    @staticmethod
    def _logged_output(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> str:
        """Return all log output, whether structlog printed it or routed it to stdlib."""
        captured = capsys.readouterr()
        return captured.out + captured.err + caplog.text

    @pytest.mark.parametrize(
        ("outcome", "event_name"),
        [
            (httpx.Response(200), "webhook_sent"),
            (httpx.TimeoutException("timed out"), "webhook_timeout"),
            (httpx.ConnectError("All connection attempts failed"), "webhook_error"),
        ],
        ids=["success", "timeout", "request_error"],
    )
    async def test_send_logs_only_scheme_and_host(
        self,
        mock_post: AsyncMock,
        outcome: httpx.Response | httpx.RequestError,
        event_name: str,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that every send outcome logs the host but no secret part of the URL."""
        caplog.set_level(logging.DEBUG)
        mock_post.side_effect = [outcome]

        await WebhookNotifier(WebhookConfig(url=self.SECRET_URL)).send("test.event", {})

        output = self._logged_output(capsys, caplog)
        assert event_name in output
        for secret in self.SECRET_PARTS:
            assert secret not in output
        assert "https://hooks.example.com" in output

    @pytest.mark.parametrize(
        "url",
        [
            "hooks.example.com/services/T000/B000/SECRETTOKEN",
            "https://[hooks.example.com/services/T000/B000/SECRETTOKEN",
        ],
        ids=["missing_scheme", "unparseable"],
    )
    async def test_send_never_echoes_malformed_url(
        self,
        mock_post: AsyncMock,
        url: str,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that a URL without a parseable host is neither logged nor fatal to send."""
        caplog.set_level(logging.DEBUG)
        mock_post.side_effect = [httpx.Response(200)]

        result = await WebhookNotifier(WebhookConfig(url=url)).send("test.event", {})

        output = self._logged_output(capsys, caplog)
        assert result is True
        assert "webhook_sent" in output
        assert "SECRETTOKEN" not in output

    @pytest.mark.usefixtures("unset_http_client_log_levels", "restore_structlog_config")
    async def test_real_send_under_app_logging_never_logs_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that httpx's own request log does not leak the URL under the app's logging.

        httpx logs every request's full URL at INFO, so real httpx client code must run.
        """
        configure_logging(log_level="INFO")
        # pytest's handlers on the root logger make basicConfig a no-op, so set the level
        # it would have set.
        caplog.set_level(logging.INFO)
        transport = httpx.MockTransport(lambda request: httpx.Response(200))
        monkeypatch.setattr(
            httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=transport)
        )

        result = await WebhookNotifier(WebhookConfig(url=self.SECRET_URL)).send("test.event", {})

        output = self._logged_output(capsys, caplog)
        assert result is True
        assert "webhook_sent" in output
        for secret in self.SECRET_PARTS:
            assert secret not in output


class TestWebhookConfig:
    """Tests for WebhookConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = WebhookConfig(url="https://example.com")

        assert config.url == "https://example.com"
        assert config.secret is None
        assert config.timeout_seconds == 30
