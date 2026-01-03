"""Unit tests for SlackNotifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dataing.adapters.notifications.slack import SlackConfig, SlackNotifier


class TestSlackNotifier:
    """Tests for SlackNotifier."""

    @pytest.fixture
    def config(self) -> SlackConfig:
        """Return a Slack configuration."""
        return SlackConfig(
            webhook_url="https://hooks.slack.com/services/T00000/B00000/XXXX",
            channel="#test-channel",
            username="TestBot",
            icon_emoji=":robot:",
        )

    @pytest.fixture
    def notifier(self, config: SlackConfig) -> SlackNotifier:
        """Return a Slack notifier."""
        return SlackNotifier(config)

    def test_init(self, notifier: SlackNotifier, config: SlackConfig) -> None:
        """Test notifier initialization."""
        assert notifier.config == config

    async def test_send_success(self, notifier: SlackNotifier) -> None:
        """Test successful Slack message delivery."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await notifier.send(
                "investigation.completed",
                {"investigation_id": "123", "finding": {"root_cause": "Test"}},
            )

            assert result is True
            mock_client.post.assert_called_once()

    async def test_send_failure(self, notifier: SlackNotifier) -> None:
        """Test Slack message delivery failure."""
        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await notifier.send("test.event", {})

            assert result is False

    async def test_send_timeout(self, notifier: SlackNotifier) -> None:
        """Test Slack timeout handling."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.TimeoutException("Timeout")
            mock_client_class.return_value = mock_client

            result = await notifier.send("test.event", {})

            assert result is False

    def test_build_message_investigation_completed(
        self,
        notifier: SlackNotifier,
    ) -> None:
        """Test message building for investigation.completed event."""
        payload = {
            "investigation_id": "inv-123",
            "finding": {"root_cause": "ETL job failed"},
        }

        message = notifier._build_message("investigation.completed", payload)

        assert message["username"] == "TestBot"
        assert message["icon_emoji"] == ":robot:"
        assert message["channel"] == "#test-channel"
        assert len(message["attachments"]) == 1
        assert message["attachments"][0]["color"] == "#36a64f"  # Green

    def test_build_message_investigation_failed(
        self,
        notifier: SlackNotifier,
    ) -> None:
        """Test message building for investigation.failed event."""
        payload = {"investigation_id": "inv-123", "error": "Timeout"}

        message = notifier._build_message("investigation.failed", payload)

        assert message["attachments"][0]["color"] == "#dc3545"  # Red
        assert any(
            f["title"] == "Error"
            for f in message["attachments"][0]["fields"]
        )

    def test_build_message_approval_required(
        self,
        notifier: SlackNotifier,
    ) -> None:
        """Test message building for approval.required event."""
        payload = {
            "investigation_id": "inv-123",
            "context": {"query": "SELECT 1"},
        }

        message = notifier._build_message("approval.required", payload)

        assert message["attachments"][0]["color"] == "#ffc107"  # Yellow

    def test_build_message_generic_event(
        self,
        notifier: SlackNotifier,
    ) -> None:
        """Test message building for generic events."""
        payload = {"key1": "value1", "key2": 42}

        message = notifier._build_message("custom.event", payload)

        # Generic events should have gray color
        assert message["attachments"][0]["color"] == "#6c757d"

    def test_get_color_for_event(self, notifier: SlackNotifier) -> None:
        """Test color selection for events."""
        assert notifier._get_color_for_event("investigation.completed") == "#36a64f"
        assert notifier._get_color_for_event("investigation.failed") == "#dc3545"
        assert notifier._get_color_for_event("investigation.started") == "#007bff"
        assert notifier._get_color_for_event("approval.required") == "#ffc107"
        assert notifier._get_color_for_event("unknown.event") == "#6c757d"


class TestSlackConfig:
    """Tests for SlackConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = SlackConfig(webhook_url="https://hooks.slack.com/test")

        assert config.channel is None
        assert config.username == "DataDr"
        assert config.icon_emoji == ":microscope:"
        assert config.timeout_seconds == 30
