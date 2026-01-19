"""Unit tests for Integrations API routes (CE)."""

import hashlib
import hmac
from uuid import uuid4

import pytest

from dataing.entrypoints.api.routes.integrations import (
    GenericWebhookPayload,
    WebhookIssueResponse,
    verify_webhook_signature,
)


class TestVerifyWebhookSignature:
    """Test webhook signature verification."""

    def test_valid_signature(self) -> None:
        """Test valid signature verification."""
        secret = "test_secret_123"
        body = b'{"title": "Test Issue"}'

        # Calculate valid signature
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        signature_header = f"sha256={signature}"

        assert verify_webhook_signature(body, signature_header, secret) is True

    def test_invalid_signature(self) -> None:
        """Test invalid signature is rejected."""
        secret = "test_secret_123"
        body = b'{"title": "Test Issue"}'
        signature_header = "sha256=invalid_signature"

        assert verify_webhook_signature(body, signature_header, secret) is False

    def test_missing_signature_header(self) -> None:
        """Test missing signature header is rejected."""
        secret = "test_secret_123"
        body = b'{"title": "Test Issue"}'

        assert verify_webhook_signature(body, None, secret) is False

    def test_wrong_prefix(self) -> None:
        """Test wrong signature prefix is rejected."""
        secret = "test_secret_123"
        body = b'{"title": "Test Issue"}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        # Wrong prefix
        assert verify_webhook_signature(body, f"md5={signature}", secret) is False

    def test_tampered_body(self) -> None:
        """Test tampered body fails verification."""
        secret = "test_secret_123"
        original_body = b'{"title": "Test Issue"}'
        tampered_body = b'{"title": "Tampered Issue"}'

        # Signature for original body
        signature = hmac.new(secret.encode(), original_body, hashlib.sha256).hexdigest()
        signature_header = f"sha256={signature}"

        # Verify with tampered body should fail
        assert verify_webhook_signature(tampered_body, signature_header, secret) is False


class TestGenericWebhookPayload:
    """Test GenericWebhookPayload schema."""

    def test_minimal_payload(self) -> None:
        """Test minimal payload with only title."""
        payload = GenericWebhookPayload(title="Test Issue")
        assert payload.title == "Test Issue"
        assert payload.description is None
        assert payload.severity is None
        assert payload.priority is None
        assert payload.labels is None

    def test_full_payload(self) -> None:
        """Test payload with all fields."""
        payload = GenericWebhookPayload(
            title="Test Issue",
            description="Detailed description",
            severity="critical",
            priority="P0",
            dataset_id="public.orders",
            labels=["bug", "urgent"],
            source_provider="alertmanager",
            source_external_id="alert-12345",
            source_external_url="https://alerts.example.com/12345",
        )
        assert payload.title == "Test Issue"
        assert payload.severity == "critical"
        assert payload.priority == "P0"
        assert len(payload.labels) == 2

    def test_empty_title_invalid(self) -> None:
        """Test empty title is rejected."""
        with pytest.raises(ValueError):
            GenericWebhookPayload(title="")

    def test_invalid_severity(self) -> None:
        """Test invalid severity is rejected."""
        with pytest.raises(ValueError):
            GenericWebhookPayload(title="Test", severity="extreme")

    def test_invalid_priority(self) -> None:
        """Test invalid priority is rejected."""
        with pytest.raises(ValueError):
            GenericWebhookPayload(title="Test", priority="P5")

    def test_valid_severities(self) -> None:
        """Test all valid severity values."""
        for severity in ["low", "medium", "high", "critical"]:
            payload = GenericWebhookPayload(title="Test", severity=severity)
            assert payload.severity == severity

    def test_valid_priorities(self) -> None:
        """Test all valid priority values."""
        for priority in ["P0", "P1", "P2", "P3"]:
            payload = GenericWebhookPayload(title="Test", priority=priority)
            assert payload.priority == priority


class TestWebhookIssueResponse:
    """Test WebhookIssueResponse schema."""

    def test_created_response(self) -> None:
        """Test response for newly created issue."""
        response = WebhookIssueResponse(
            id=uuid4(),
            number=123,
            status="open",
            created=True,
        )
        assert response.created is True
        assert response.status == "open"
        assert response.number == 123

    def test_deduplicated_response(self) -> None:
        """Test response for deduplicated issue."""
        response = WebhookIssueResponse(
            id=uuid4(),
            number=456,
            status="in_progress",
            created=False,
        )
        assert response.created is False
        assert response.status == "in_progress"
