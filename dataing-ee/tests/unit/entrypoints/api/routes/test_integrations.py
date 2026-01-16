"""Unit tests for Integrations API routes (EE)."""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from dataing_ee.entrypoints.api.routes.integrations import (
    FieldMappingCreate,
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationResponse,
    IntegrationSecretResponse,
    IntegrationUpdate,
    _apply_transform,
    _extract_event_type,
    _extract_idempotency_key,
    _get_default_description,
    _get_default_title,
    _get_nested_value,
    _verify_provider_signature,
)
from dataing_ee.models.integration import IntegrationProvider


class TestIntegrationCreateSchema:
    """Test IntegrationCreate Pydantic schema."""

    def test_valid_create(self) -> None:
        """Test valid creation payload."""
        payload = IntegrationCreate(
            name="My Jira Integration",
            provider="jira",
            config={"project_key": "PROJ"},
            rate_limit_per_minute=30,
        )
        assert payload.name == "My Jira Integration"
        assert payload.provider == "jira"
        assert payload.rate_limit_per_minute == 30

    def test_minimal_create(self) -> None:
        """Test minimal creation payload."""
        payload = IntegrationCreate(name="Test", provider="custom")
        assert payload.name == "Test"
        assert payload.provider == "custom"
        assert payload.config is None
        assert payload.rate_limit_per_minute == 60

    def test_invalid_provider(self) -> None:
        """Test invalid provider is rejected."""
        with pytest.raises(ValueError):
            IntegrationCreate(name="Test", provider="invalid_provider")

    def test_empty_name_invalid(self) -> None:
        """Test empty name is rejected."""
        with pytest.raises(ValueError):
            IntegrationCreate(name="", provider="jira")

    def test_valid_providers(self) -> None:
        """Test all valid provider values."""
        for provider in ["jira", "linear", "pagerduty", "opsgenie", "custom"]:
            payload = IntegrationCreate(name="Test", provider=provider)
            assert payload.provider == provider


class TestIntegrationUpdateSchema:
    """Test IntegrationUpdate Pydantic schema."""

    def test_all_none(self) -> None:
        """Test all fields can be None."""
        update = IntegrationUpdate()
        assert update.name is None
        assert update.enabled is None
        assert update.config is None
        assert update.rate_limit_per_minute is None

    def test_partial_update(self) -> None:
        """Test partial update."""
        update = IntegrationUpdate(name="New Name", enabled=False)
        assert update.name == "New Name"
        assert update.enabled is False
        assert update.config is None


class TestIntegrationResponseSchema:
    """Test IntegrationResponse Pydantic schema."""

    def test_response_fields(self) -> None:
        """Test response has expected fields."""
        now = datetime.now(UTC)
        response = IntegrationResponse(
            id=uuid4(),
            tenant_id=uuid4(),
            name="My Integration",
            provider="jira",
            enabled=True,
            config={"project_key": "PROJ"},
            rate_limit_per_minute=60,
            webhook_url="https://example.com/api/v1/integrations/jira/webhook?integration_id=...",
            last_webhook_at=None,
            webhook_count=0,
            error_count=0,
            created_at=now,
            updated_at=now,
        )
        assert response.name == "My Integration"
        assert response.provider == "jira"
        assert response.enabled is True
        assert response.webhook_count == 0


class TestFieldMappingCreateSchema:
    """Test FieldMappingCreate Pydantic schema."""

    def test_valid_mapping(self) -> None:
        """Test valid field mapping."""
        mapping = FieldMappingCreate(
            source_field="issue.fields.summary",
            target_field="title",
            transform="uppercase",
        )
        assert mapping.source_field == "issue.fields.summary"
        assert mapping.target_field == "title"
        assert mapping.transform == "uppercase"

    def test_invalid_target_field(self) -> None:
        """Test invalid target field is rejected."""
        with pytest.raises(ValueError):
            FieldMappingCreate(
                source_field="issue.summary",
                target_field="invalid_field",
            )

    def test_valid_target_fields(self) -> None:
        """Test all valid target field values."""
        for target in ["title", "description", "severity", "priority", "dataset_id", "labels"]:
            mapping = FieldMappingCreate(source_field="test.field", target_field=target)
            assert mapping.target_field == target


class TestVerifyProviderSignature:
    """Test provider-specific signature verification."""

    def test_jira_signature(self) -> None:
        """Test Jira signature verification."""
        secret = "test_secret"
        body = b'{"issue": {"id": "123"}}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_provider_signature(
            body, f"sha256={signature}", secret, IntegrationProvider.JIRA
        ) is True

    def test_linear_signature(self) -> None:
        """Test Linear signature verification (raw HMAC)."""
        secret = "test_secret"
        body = b'{"data": {"id": "123"}}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_provider_signature(
            body, signature, secret, IntegrationProvider.LINEAR
        ) is True

    def test_pagerduty_signature(self) -> None:
        """Test PagerDuty signature verification."""
        secret = "test_secret"
        body = b'{"messages": [{"incident": {"id": "123"}}]}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_provider_signature(
            body, f"v1={signature}", secret, IntegrationProvider.PAGERDUTY
        ) is True

    def test_custom_signature(self) -> None:
        """Test custom provider signature verification."""
        secret = "test_secret"
        body = b'{"title": "Test"}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_provider_signature(
            body, f"sha256={signature}", secret, IntegrationProvider.CUSTOM
        ) is True

    def test_missing_signature(self) -> None:
        """Test missing signature is rejected."""
        assert _verify_provider_signature(
            b'{}', None, "secret", IntegrationProvider.JIRA
        ) is False


class TestGetNestedValue:
    """Test nested value extraction from dicts."""

    def test_simple_key(self) -> None:
        """Test simple key access."""
        obj = {"title": "Test"}
        assert _get_nested_value(obj, "title") == "Test"

    def test_nested_key(self) -> None:
        """Test nested key access."""
        obj = {"issue": {"fields": {"summary": "Test Issue"}}}
        assert _get_nested_value(obj, "issue.fields.summary") == "Test Issue"

    def test_missing_key(self) -> None:
        """Test missing key returns None."""
        obj = {"title": "Test"}
        assert _get_nested_value(obj, "missing") is None

    def test_missing_nested_key(self) -> None:
        """Test missing nested key returns None."""
        obj = {"issue": {"fields": {}}}
        assert _get_nested_value(obj, "issue.fields.summary") is None


class TestApplyTransform:
    """Test value transformations."""

    def test_uppercase(self) -> None:
        """Test uppercase transform."""
        assert _apply_transform("hello", "uppercase") == "HELLO"

    def test_lowercase(self) -> None:
        """Test lowercase transform."""
        assert _apply_transform("HELLO", "lowercase") == "hello"

    def test_severity_map(self) -> None:
        """Test severity mapping transform."""
        assert _apply_transform("blocker", "severity_map") == "critical"
        assert _apply_transform("major", "severity_map") == "high"
        assert _apply_transform("minor", "severity_map") == "low"

    def test_unknown_transform(self) -> None:
        """Test unknown transform returns value unchanged."""
        assert _apply_transform("value", "unknown") == "value"


class TestExtractIdempotencyKey:
    """Test idempotency key extraction."""

    def test_jira_payload(self) -> None:
        """Test Jira idempotency key extraction."""
        from unittest.mock import MagicMock
        request = MagicMock()
        request.headers = {}

        payload = {"issue": {"id": "12345"}, "webhookEvent": "issue_created"}
        key = _extract_idempotency_key(payload, IntegrationProvider.JIRA, request)
        assert key == "jira_12345_issue_created"

    def test_linear_payload(self) -> None:
        """Test Linear idempotency key extraction."""
        from unittest.mock import MagicMock
        request = MagicMock()
        request.headers = {}

        payload = {"data": {"id": "lin-456"}, "action": "create"}
        key = _extract_idempotency_key(payload, IntegrationProvider.LINEAR, request)
        assert key == "linear_lin-456_create"

    def test_fallback_to_request_id(self) -> None:
        """Test fallback to X-Request-Id header."""
        from unittest.mock import MagicMock
        request = MagicMock()
        request.headers = {"X-Request-Id": "req-789"}

        payload = {}
        key = _extract_idempotency_key(payload, IntegrationProvider.CUSTOM, request)
        assert key == "custom_req-789"


class TestExtractEventType:
    """Test event type extraction."""

    def test_jira_event_type(self) -> None:
        """Test Jira event type extraction."""
        payload = {"webhookEvent": "issue_updated"}
        assert _extract_event_type(payload, IntegrationProvider.JIRA) == "issue_updated"

    def test_linear_event_type(self) -> None:
        """Test Linear event type extraction."""
        payload = {"action": "create"}
        assert _extract_event_type(payload, IntegrationProvider.LINEAR) == "create"

    def test_pagerduty_event_type(self) -> None:
        """Test PagerDuty event type extraction."""
        payload = {"messages": [{"event": "incident.trigger"}]}
        assert _extract_event_type(payload, IntegrationProvider.PAGERDUTY) == "incident.trigger"


class TestGetDefaultTitle:
    """Test default title extraction."""

    def test_jira_title(self) -> None:
        """Test Jira title extraction."""
        payload = {"issue": {"fields": {"summary": "Bug in login"}}}
        assert _get_default_title(payload, IntegrationProvider.JIRA) == "Bug in login"

    def test_linear_title(self) -> None:
        """Test Linear title extraction."""
        payload = {"data": {"title": "Feature request"}}
        assert _get_default_title(payload, IntegrationProvider.LINEAR) == "Feature request"

    def test_pagerduty_title(self) -> None:
        """Test PagerDuty title extraction."""
        payload = {"messages": [{"incident": {"title": "Server down"}}]}
        assert _get_default_title(payload, IntegrationProvider.PAGERDUTY) == "Server down"

    def test_generic_title(self) -> None:
        """Test generic title extraction."""
        payload = {"title": "Generic title"}
        assert _get_default_title(payload, IntegrationProvider.CUSTOM) == "Generic title"


class TestGetDefaultDescription:
    """Test default description extraction."""

    def test_jira_description(self) -> None:
        """Test Jira description extraction."""
        payload = {"issue": {"fields": {"description": "Detailed bug description"}}}
        assert _get_default_description(payload, IntegrationProvider.JIRA) == "Detailed bug description"

    def test_linear_description(self) -> None:
        """Test Linear description extraction."""
        payload = {"data": {"description": "Feature details"}}
        assert _get_default_description(payload, IntegrationProvider.LINEAR) == "Feature details"

    def test_generic_description(self) -> None:
        """Test generic description extraction."""
        payload = {"description": "Generic description"}
        assert _get_default_description(payload, IntegrationProvider.CUSTOM) == "Generic description"
