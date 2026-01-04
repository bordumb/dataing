"""Unit tests for EmailNotifier."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dataing.adapters.notifications.email import EmailConfig, EmailNotifier


class TestEmailNotifier:
    """Tests for EmailNotifier."""

    @pytest.fixture
    def config(self) -> EmailConfig:
        """Return an email configuration."""
        return EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="test@example.com",
            smtp_password="password",
            from_email="noreply@example.com",
            from_name="Dataing Test",
            use_tls=True,
        )

    @pytest.fixture
    def notifier(self, config: EmailConfig) -> EmailNotifier:
        """Return an email notifier."""
        return EmailNotifier(config)

    def test_init(self, notifier: EmailNotifier, config: EmailConfig) -> None:
        """Test notifier initialization."""
        assert notifier.config == config

    def test_send_success(self, notifier: EmailNotifier) -> None:
        """Test successful email delivery."""
        mock_server = MagicMock()

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = notifier.send(
                to_emails=["user@example.com"],
                subject="Test Subject",
                body_html="<p>Test HTML</p>",
                body_text="Test text",
            )

            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("test@example.com", "password")
            mock_server.sendmail.assert_called_once()

    def test_send_without_auth(self, config: EmailConfig) -> None:
        """Test email delivery without authentication."""
        config.smtp_user = None
        config.smtp_password = None
        notifier = EmailNotifier(config)

        mock_server = MagicMock()

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = notifier.send(
                to_emails=["user@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
            )

            assert result is True
            mock_server.login.assert_not_called()

    def test_send_without_tls(self, config: EmailConfig) -> None:
        """Test email delivery without TLS."""
        config.use_tls = False
        notifier = EmailNotifier(config)

        mock_server = MagicMock()

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = notifier.send(
                to_emails=["user@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
            )

            assert result is True
            mock_server.starttls.assert_not_called()

    def test_send_failure(self, notifier: EmailNotifier) -> None:
        """Test email delivery failure."""
        import smtplib

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.side_effect = smtplib.SMTPException("Failed")

            result = notifier.send(
                to_emails=["user@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
            )

            assert result is False

    def test_send_investigation_completed(self, notifier: EmailNotifier) -> None:
        """Test sending investigation completed email."""
        mock_server = MagicMock()

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = notifier.send_investigation_completed(
                to_emails=["user@example.com"],
                investigation_id="inv-123",
                finding={
                    "root_cause": "ETL job failed",
                    "confidence": 0.9,
                    "summary": "The ETL job timed out.",
                },
            )

            assert result is True
            # Check that sendmail was called with proper content
            call_args = mock_server.sendmail.call_args
            msg_str = call_args[0][2]  # Third argument is the message
            assert "Investigation Completed" in msg_str
            assert "inv-123" in msg_str

    def test_send_approval_required(self, notifier: EmailNotifier) -> None:
        """Test sending approval required email."""
        mock_server = MagicMock()

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = notifier.send_approval_required(
                to_emails=["admin@example.com"],
                investigation_id="inv-456",
                approval_url="https://app.example.com/approve/req-123",
                context={"query": "SELECT 1"},
            )

            assert result is True
            call_args = mock_server.sendmail.call_args
            msg_str = call_args[0][2]
            assert "Approval Required" in msg_str


class TestEmailConfig:
    """Tests for EmailConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = EmailConfig(smtp_host="smtp.example.com")

        assert config.smtp_port == 587
        assert config.smtp_user is None
        assert config.smtp_password is None
        assert config.from_email == "dataing@example.com"
        assert config.from_name == "Dataing"
        assert config.use_tls is True
