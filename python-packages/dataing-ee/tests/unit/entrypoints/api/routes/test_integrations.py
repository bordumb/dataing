"""Unit tests for Integrations API routes (EE)."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from dataing_ee.adapters.integrations.registry import AdapterRegistry
from dataing_ee.entrypoints.api.routes.integrations import (
    FieldMappingCreate,
    IntegrationCreate,
    IntegrationResponse,
    IntegrationUpdate,
    _apply_transform,
    _extract_event_type,
    _extract_idempotency_key,
    _get_default_description,
    _get_default_title,
    _get_nested_value,
    _verify_provider_signature,
    router,
)
from dataing_ee.models.integration import Integration, IntegrationProvider
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key


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
        valid_providers = [
            "jira",
            "linear",
            "pagerduty",
            "opsgenie",
            "monte_carlo",
            "great_expectations",
            "slack",
            "custom",
        ]
        for provider in valid_providers:
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


class TestIntegrationModel:
    """Test the Integration ORM model matches the schema."""

    def test_signing_secret_is_required(self) -> None:
        """Test signing_secret is NOT NULL, as in migration 035."""
        assert Integration.__table__.c.signing_secret.nullable is False


class TestVerifyProviderSignature:
    """Test provider-specific signature verification."""

    def test_jira_signature(self) -> None:
        """Test Jira signature verification."""
        secret = "test_secret"
        body = b'{"issue": {"id": "123"}}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert (
            _verify_provider_signature(
                body, f"sha256={signature}", secret, IntegrationProvider.JIRA
            )
            is True
        )

    def test_linear_signature(self) -> None:
        """Test Linear signature verification (raw HMAC)."""
        secret = "test_secret"
        body = b'{"data": {"id": "123"}}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert (
            _verify_provider_signature(body, signature, secret, IntegrationProvider.LINEAR) is True
        )

    def test_pagerduty_signature(self) -> None:
        """Test PagerDuty signature verification."""
        secret = "test_secret"
        body = b'{"messages": [{"incident": {"id": "123"}}]}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert (
            _verify_provider_signature(
                body, f"v1={signature}", secret, IntegrationProvider.PAGERDUTY
            )
            is True
        )

    def test_custom_signature(self) -> None:
        """Test custom provider signature verification."""
        secret = "test_secret"
        body = b'{"title": "Test"}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert (
            _verify_provider_signature(
                body, f"sha256={signature}", secret, IntegrationProvider.CUSTOM
            )
            is True
        )

    def test_missing_signature(self) -> None:
        """Test missing signature is rejected."""
        assert _verify_provider_signature(b"{}", None, "secret", IntegrationProvider.JIRA) is False


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
        assert (
            _get_default_description(payload, IntegrationProvider.JIRA)
            == "Detailed bug description"
        )

    def test_linear_description(self) -> None:
        """Test Linear description extraction."""
        payload = {"data": {"description": "Feature details"}}
        assert _get_default_description(payload, IntegrationProvider.LINEAR) == "Feature details"

    def test_generic_description(self) -> None:
        """Test generic description extraction."""
        payload = {"description": "Generic description"}
        assert (
            _get_default_description(payload, IntegrationProvider.CUSTOM) == "Generic description"
        )


class TestAdapterDelegation:
    """Test that adapter classes are used for MC and GX providers."""

    def test_get_adapter_monte_carlo(self) -> None:
        """Test that get_adapter returns MonteCarloAdapter for monte_carlo provider."""
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("monte_carlo")
        assert adapter is not None
        assert adapter.provider == "monte_carlo"
        assert adapter.signature_header == "X-MC-Signature"

    def test_get_adapter_great_expectations(self) -> None:
        """Test that get_adapter returns GreatExpectationsAdapter for GX provider."""
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("great_expectations")
        assert adapter is not None
        assert adapter.provider == "great_expectations"
        assert adapter.signature_header == "X-GE-Signature"

    def test_get_adapter_fallback_for_jira(self) -> None:
        """Test that get_adapter returns JiraAdapter for jira provider."""
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("jira")
        assert adapter is not None
        assert adapter.provider == "jira"

    def test_monte_carlo_adapter_verify_signature(self) -> None:
        """Test Monte Carlo adapter signature verification."""
        from dataing_ee.adapters.integrations.base import WebhookRequest
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("monte_carlo")
        assert adapter is not None

        secret = "test_secret"
        body = b'{"incident": {"id": "123"}}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        request = WebhookRequest(
            body=body,
            headers={"X-MC-Signature": signature},
            query_params={},
        )
        assert adapter.verify_signature(request, secret) is True

    def test_monte_carlo_adapter_parse_payload(self) -> None:
        """Test Monte Carlo adapter payload parsing."""
        import json

        from dataing_ee.adapters.integrations.base import WebhookRequest
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("monte_carlo")
        assert adapter is not None

        payload = {
            "incident": {
                "id": "inc-123",
                "title": "Data freshness issue",
                "severity": "high",
                "tables": [{"full_table_id": "db.schema.table"}],
            }
        }
        body = json.dumps(payload).encode()

        request = WebhookRequest(
            body=body,
            headers={},
            query_params={},
        )
        issue_data = adapter.parse_payload(request)
        assert issue_data.title == "Data freshness issue"
        assert issue_data.severity == "high"
        assert "monte-carlo" in issue_data.labels

    def test_monte_carlo_adapter_get_fingerprint(self) -> None:
        """Test Monte Carlo adapter fingerprint generation."""
        import json

        from dataing_ee.adapters.integrations.base import WebhookRequest
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("monte_carlo")
        assert adapter is not None

        payload = {"incident": {"id": "inc-456"}}
        body = json.dumps(payload).encode()

        request = WebhookRequest(
            body=body,
            headers={},
            query_params={},
        )
        fingerprint = adapter.get_fingerprint(request)
        assert fingerprint == "mc_incident_inc-456"

    def test_great_expectations_adapter_should_process_failure(self) -> None:
        """Test GX adapter processes failed validations."""
        import json

        from dataing_ee.adapters.integrations.base import WebhookRequest
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("great_expectations")
        assert adapter is not None

        payload = {"result": {"success": False, "statistics": {"success_percent": 50}}}
        body = json.dumps(payload).encode()

        request = WebhookRequest(
            body=body,
            headers={},
            query_params={},
        )
        assert adapter.should_process(request) is True

    def test_great_expectations_adapter_skips_success(self) -> None:
        """Test GX adapter skips successful validations."""
        import json

        from dataing_ee.adapters.integrations.base import WebhookRequest
        from dataing_ee.adapters.integrations.registry import get_adapter

        adapter = get_adapter("great_expectations")
        assert adapter is not None

        payload = {"result": {"success": True}}
        body = json.dumps(payload).encode()

        request = WebhookRequest(
            body=body,
            headers={},
            query_params={},
        )
        assert adapter.should_process(request) is False


WEBHOOK_SECRET = "whsec_test"
WRONG_SIGNATURE = "sha256=" + "0" * 64


def _integration_row(
    provider: str, signing_secret: str | None, *, enabled: bool = True
) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "provider": provider,
        "enabled": enabled,
        "signing_secret": signing_secret,
        "rate_limit_per_minute": 60,
    }


def _webhook_db(integration: dict[str, Any]) -> AsyncMock:
    """App DB holding one integration; accepts the writes of a skipped webhook."""
    db = AsyncMock()
    db.fetch_one.side_effect = [integration, None, {"id": uuid4()}]
    db.fetch_all.return_value = []
    return db


def _post_webhook(
    db: AsyncMock, provider: str, payload: dict[str, Any], headers: dict[str, str] | None = None
) -> Any:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: db
    return TestClient(app).post(
        f"/api/v1/integrations/{provider}/webhook",
        params={"integration_id": str(uuid4())},
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def _signed(payload: dict[str, Any], header: str) -> dict[str, str]:
    digest = hmac.new(
        WEBHOOK_SECRET.encode(), json.dumps(payload).encode(), hashlib.sha256
    ).hexdigest()
    return {header: f"sha256={digest}"}


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _signed_by(
    provider: str, payload: dict[str, Any], secret: str = WEBHOOK_SECRET
) -> dict[str, str]:
    """Sign ``payload`` the way ``provider`` does, under its own header names."""
    return _signed_body(provider, json.dumps(payload).encode(), secret)


def _signed_body(provider: str, body: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    """Sign a raw request ``body`` the way ``provider`` does."""
    if provider == "slack":
        timestamp = str(int(time.time()))
        digest = _hmac_hex(secret, f"v0:{timestamp}:{body.decode()}".encode())
        return {"X-Slack-Signature": f"v0={digest}", "X-Slack-Request-Timestamp": timestamp}
    digest = _hmac_hex(secret, body)
    if provider == "monte_carlo":
        return {"X-MC-Signature": digest}
    if provider == "dbt":
        return {"Authorization": digest}
    header = {
        "jira": "X-Hub-Signature",
        "great_expectations": "X-GE-Signature",
        "soda": "X-Soda-Signature",
    }[provider]
    return {header: f"sha256={digest}"}


# A webhook for each provider that has an adapter, and the response it gets once its
# signature checks out: the adapter either filters it or records it and finds no title.
ADAPTER_WEBHOOKS: dict[str, tuple[dict[str, Any], dict[str, str]]] = {
    "jira": (
        {"webhookEvent": "jira:issue_created", "issue": {"id": "1", "fields": {}}},
        {"status": "skipped", "reason": "no_title"},
    ),
    "monte_carlo": (
        {"event_type": "incident_created"},
        {"status": "skipped", "reason": "no_title"},
    ),
    "great_expectations": (
        {"result": {"success": True}},
        {"status": "skipped", "reason": "filtered_by_adapter"},
    ),
    "dbt": (
        {"eventType": "job.run.completed", "data": {"runStatus": "Success"}},
        {"status": "skipped", "reason": "filtered_by_adapter"},
    ),
    "slack": (
        {"type": "event_callback", "event": {"type": "reaction_added", "reaction": "eyes"}},
        {"status": "skipped", "reason": "filtered_by_adapter"},
    ),
    "soda": (
        {"event_type": "check.passed"},
        {"status": "skipped", "reason": "filtered_by_adapter"},
    ),
}


def _recorded_event(db: AsyncMock) -> bool:
    return any(
        "INSERT INTO integration_events" in call.args[0] for call in db.fetch_one.await_args_list
    )


class TestProviderWebhookAuthentication:
    """Webhooks are authenticated before any processing, and fail closed."""

    @pytest.mark.parametrize("signing_secret", [None, ""])
    @pytest.mark.parametrize(
        ("provider", "payload"),
        [
            # No adapter: inline signature check
            ("custom", {"event": "ping"}),
            # Adapter-based signature check
            ("jira", {"webhookEvent": "jira:issue_created", "issue": {"id": "1", "fields": {}}}),
        ],
    )
    def test_rejects_webhook_when_no_signing_secret(
        self, provider: str, payload: dict[str, Any], signing_secret: str | None
    ) -> None:
        db = _webhook_db(_integration_row(provider, signing_secret))

        response = _post_webhook(db, provider, payload)

        assert response.status_code == 401
        assert not _recorded_event(db)

    @pytest.mark.parametrize(
        ("signing_secret", "headers"),
        [(None, {}), (WEBHOOK_SECRET, {"X-GE-Signature": WRONG_SIGNATURE})],
    )
    def test_rejects_unauthenticated_webhook_before_adapter_filtering(
        self, signing_secret: str | None, headers: dict[str, str]
    ) -> None:
        # Great Expectations skips successful validations; that must not bypass auth.
        db = _webhook_db(_integration_row("great_expectations", signing_secret))

        response = _post_webhook(db, "great_expectations", {"result": {"success": True}}, headers)

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("signing_secret", "headers"),
        [(None, {}), (WEBHOOK_SECRET, {"X-Webhook-Signature": WRONG_SIGNATURE})],
    )
    def test_rejects_unauthenticated_webhook_for_disabled_integration(
        self, signing_secret: str | None, headers: dict[str, str]
    ) -> None:
        db = _webhook_db(_integration_row("custom", signing_secret, enabled=False))

        response = _post_webhook(db, "custom", {"event": "ping"}, headers)

        assert response.status_code == 401

    def test_processes_webhook_with_valid_signature(self) -> None:
        payload = {"event": "ping"}
        db = _webhook_db(_integration_row("custom", WEBHOOK_SECRET))

        response = _post_webhook(db, "custom", payload, _signed(payload, "X-Webhook-Signature"))

        assert response.status_code == 200
        assert response.json() == {"status": "skipped", "reason": "no_title"}
        assert _recorded_event(db)

    def test_acknowledges_signed_webhook_for_disabled_integration(self) -> None:
        payload = {"event": "ping"}
        db = _webhook_db(_integration_row("custom", WEBHOOK_SECRET, enabled=False))

        response = _post_webhook(db, "custom", payload, _signed(payload, "X-Webhook-Signature"))

        assert response.status_code == 200
        assert response.json() == {"status": "skipped", "reason": "integration_disabled"}

    @pytest.mark.parametrize("provider", list(ADAPTER_WEBHOOKS))
    def test_accepts_webhook_signed_by_provider(self, provider: str) -> None:
        # The server hands the adapter lowercase header names, whatever case was sent.
        payload, expected = ADAPTER_WEBHOOKS[provider]
        db = _webhook_db(_integration_row(provider, WEBHOOK_SECRET))

        response = _post_webhook(db, provider, payload, _signed_by(provider, payload))

        assert response.status_code == 200
        assert response.json() == expected

    @pytest.mark.parametrize("provider", list(ADAPTER_WEBHOOKS))
    def test_rejects_webhook_signed_with_another_secret(self, provider: str) -> None:
        payload, _ = ADAPTER_WEBHOOKS[provider]
        db = _webhook_db(_integration_row(provider, WEBHOOK_SECRET))

        response = _post_webhook(
            db, provider, payload, _signed_by(provider, payload, secret="another_secret")
        )

        assert response.status_code == 401
        assert not _recorded_event(db)

    def test_signed_webhooks_cover_every_adapter(self) -> None:
        assert set(ADAPTER_WEBHOOKS) == set(AdapterRegistry.list_providers())


SLACK_URL_VERIFICATION = {"type": "url_verification", "token": "legacy", "challenge": "3eZbrw1aB"}


class TestProviderHandshake:
    """Endpoint-verification handshakes are answered only once authenticated."""

    def test_answers_signed_slack_url_verification(self) -> None:
        payload = SLACK_URL_VERIFICATION
        db = _webhook_db(_integration_row("slack", WEBHOOK_SECRET))

        response = _post_webhook(db, "slack", payload, _signed_by("slack", payload))

        assert response.status_code == 200
        assert response.json() == {"challenge": "3eZbrw1aB"}
        assert not _recorded_event(db)

    def test_rejects_url_verification_with_bad_signature(self) -> None:
        payload = SLACK_URL_VERIFICATION
        db = _webhook_db(_integration_row("slack", WEBHOOK_SECRET))

        response = _post_webhook(
            db, "slack", payload, _signed_by("slack", payload, secret="another_secret")
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid webhook signature"}


# Shaped like a Slack signing secret: 32 hex characters, issued by the provider.
PROVIDER_SECRET = "0123456789abcdef" * 2


def _admin_client(db: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: db
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=uuid4(),
        tenant_slug="test",
        tenant_name="Test",
        user_id=uuid4(),
        scopes=["admin"],
    )
    return TestClient(app)


def _integration_record() -> dict[str, Any]:
    """An integrations row as the CRUD routes read it back."""
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "name": "Slack",
        "provider": "slack",
        "enabled": True,
        "config": {},
        "rate_limit_per_minute": 60,
        "last_webhook_at": None,
        "webhook_count": 0,
        "error_count": 0,
        "created_at": now,
        "updated_at": now,
    }


class TestProviderSigningSecret:
    """Providers that issue their own signing secret (Slack, dbt Cloud) can supply it."""

    def test_create_stores_supplied_secret(self) -> None:
        db = AsyncMock()
        db.fetch_one.return_value = {"id": uuid4()}

        response = _admin_client(db).post(
            "/api/v1/integrations",
            json={"name": "Slack", "provider": "slack", "signing_secret": PROVIDER_SECRET},
        )

        assert response.status_code == 201
        assert response.json()["signing_secret"] == PROVIDER_SECRET
        assert PROVIDER_SECRET in db.fetch_one.await_args.args

    def test_create_generates_secret_when_none_supplied(self) -> None:
        db = AsyncMock()
        db.fetch_one.return_value = {"id": uuid4()}

        response = _admin_client(db).post(
            "/api/v1/integrations", json={"name": "Jira", "provider": "jira"}
        )

        secret = response.json()["signing_secret"]
        assert response.status_code == 201
        assert len(secret) == 64
        assert secret in db.fetch_one.await_args.args

    def test_update_replaces_secret_without_returning_it(self) -> None:
        record = _integration_record()
        db = AsyncMock()
        db.fetch_one.side_effect = [{"id": record["id"]}, record]

        response = _admin_client(db).patch(
            f"/api/v1/integrations/{record['id']}", json={"signing_secret": PROVIDER_SECRET}
        )

        assert response.status_code == 200
        assert "signing_secret" not in response.json()
        update = db.fetch_one.await_args
        assert "signing_secret = $" in update.args[0]
        assert PROVIDER_SECRET in update.args

    def test_create_rejects_short_secret(self) -> None:
        with pytest.raises(ValueError):
            IntegrationCreate(name="Slack", provider="slack", signing_secret="x" * 15)

    def test_update_rejects_short_secret(self) -> None:
        with pytest.raises(ValueError):
            IntegrationUpdate(signing_secret="x" * 15)


FORM = "application/x-www-form-urlencoded"
# Slack sends interactive components form-encoded, as JSON in a payload field...
SLACK_BLOCK_ACTION = {
    "type": "block_actions",
    "trigger_id": "13345224609.738474920.8088930838d88f008e0",
    "user": {"id": "U123"},
    "actions": [{"action_id": "flag_issue", "value": "orders"}],
}
# ...and slash commands as plain form fields.
SLACK_SLASH_COMMAND = {
    "command": "/dataing",
    "text": "orders has nulls",
    "user_id": "U123",
    "channel_id": "C123",
    "trigger_id": "13345224609.738474920.8088930838d88f008e1",
    "response_url": "https://hooks.slack.com/commands/T123/1/abc",
}


def _post_raw(db: AsyncMock, provider: str, body: bytes, headers: dict[str, str]) -> Any:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: db
    return TestClient(app).post(
        f"/api/v1/integrations/{provider}/webhook",
        params={"integration_id": str(uuid4())},
        content=body,
        headers=headers,
    )


class TestFormEncodedWebhooks:
    """Webhook bodies are decoded once authenticated, JSON or form-encoded."""

    def test_processes_signed_block_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = urlencode({"payload": json.dumps(SLACK_BLOCK_ACTION)}).encode()
        db = AsyncMock()
        db.fetch_one.side_effect = [
            _integration_row("slack", WEBHOOK_SECRET),
            None,  # not delivered before
            {"id": uuid4()},  # integration event recorded
            {"num": 7},  # next issue number
            {"id": uuid4(), "number": 7},  # issue created
        ]
        db.fetch_all.return_value = []
        monkeypatch.setattr(
            "dataing_ee.entrypoints.api.routes.integrations._evaluate_and_start_investigation",
            AsyncMock(return_value=None),
        )

        headers = {"Content-Type": FORM, **_signed_body("slack", body)}
        response = _post_raw(db, "slack", body, headers)

        assert response.status_code == 200
        assert response.json()["status"] == "processed"
        assert "Slack Action: flag_issue = orders" in db.fetch_one.await_args.args

    def test_acknowledges_signed_slash_command(self) -> None:
        body = urlencode(SLACK_SLASH_COMMAND).encode()
        db = _webhook_db(_integration_row("slack", WEBHOOK_SECRET))

        headers = {"Content-Type": FORM, **_signed_body("slack", body)}
        response = _post_raw(db, "slack", body, headers)

        assert response.status_code == 200
        assert response.json() == {"status": "skipped", "reason": "filtered_by_adapter"}

    def test_rejects_malformed_body_after_authentication(self) -> None:
        body = b"not json"
        db = _webhook_db(_integration_row("jira", WEBHOOK_SECRET))

        headers = {"Content-Type": "application/json", **_signed_body("jira", body)}
        response = _post_raw(db, "jira", body, headers)

        assert response.status_code == 400
        assert not _recorded_event(db)
