"""Unit tests for Integrations API routes (CE)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from dataing.entrypoints.api.routes.integrations import (
    GenericWebhookPayload,
    WebhookIssueResponse,
    decode_header_schema,
    get_configured_schema,
    validate_payload_against_schema,
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

    def test_response_with_policy_action(self) -> None:
        """Test response with policy action."""
        inv_id = uuid4()
        response = WebhookIssueResponse(
            id=uuid4(),
            number=789,
            status="open",
            created=True,
            policy_action="auto",
            investigation_id=inv_id,
        )
        assert response.policy_action == "auto"
        assert response.investigation_id == inv_id

    def test_response_without_policy_action(self) -> None:
        """Test response without policy action (deduplicated)."""
        response = WebhookIssueResponse(
            id=uuid4(),
            number=789,
            status="open",
            created=False,
        )
        assert response.policy_action is None
        assert response.investigation_id is None


class TestEvaluateAndApplyPolicy:
    """Tests for _evaluate_and_apply_policy function."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database."""
        from unittest.mock import AsyncMock

        return AsyncMock()

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Create mock request."""
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.app.state.temporal_client = None
        return mock

    @pytest.fixture
    def mock_auth(self) -> MagicMock:
        """Create mock auth context."""
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.tenant_id = uuid4()
        return mock

    @pytest.fixture
    def sample_payload(self) -> GenericWebhookPayload:
        """Create sample payload."""
        return GenericWebhookPayload(
            title="Test Issue",
            severity="high",
            dataset_id="prod.orders",
            source_provider="dbt",
        )

    async def test_no_team_returns_issue_only(
        self,
        mock_db: AsyncMock,
        mock_request: MagicMock,
        mock_auth: MagicMock,
        sample_payload: GenericWebhookPayload,
    ) -> None:
        """Test that no team defaults to issue_only."""
        from unittest.mock import AsyncMock, patch

        from dataing.entrypoints.api.routes.integrations import _evaluate_and_apply_policy

        # Mock no team found
        with patch("dataing.entrypoints.api.routes.integrations.TeamPolicyRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_default_team_for_tenant = AsyncMock(return_value=None)

            action, inv_id = await _evaluate_and_apply_policy(
                request=mock_request,
                db=mock_db,
                auth=mock_auth,
                issue_id=uuid4(),
                payload=sample_payload,
            )

            assert action == "issue_only"
            assert inv_id is None

    async def test_review_action_sends_notification(
        self,
        mock_db: AsyncMock,
        mock_request: MagicMock,
        mock_auth: MagicMock,
        sample_payload: GenericWebhookPayload,
    ) -> None:
        """Test that review action sends notification."""
        from unittest.mock import AsyncMock, patch

        from dataing.adapters.db.team_policy_repository import PolicyAction
        from dataing.entrypoints.api.routes.integrations import _evaluate_and_apply_policy
        from dataing.services.policy import PolicyResult, QueueConfig

        team_id = uuid4()

        with (
            patch("dataing.entrypoints.api.routes.integrations.TeamPolicyRepository") as MockRepo,
            patch("dataing.entrypoints.api.routes.integrations.PolicyService") as MockPolicyService,
            patch(
                "dataing.entrypoints.api.routes.integrations.NotificationService"
            ) as MockNotifService,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_default_team_for_tenant = AsyncMock(return_value=team_id)

            mock_policy_svc = MockPolicyService.return_value
            mock_policy_svc.evaluate = AsyncMock(
                return_value=PolicyResult(
                    action=PolicyAction.REVIEW,
                    queue_config=QueueConfig(),
                    source="team_default",
                    team_id=team_id,
                )
            )

            mock_notif = MockNotifService.return_value
            mock_notif.notify = AsyncMock()

            mock_db.execute = AsyncMock()

            action, inv_id = await _evaluate_and_apply_policy(
                request=mock_request,
                db=mock_db,
                auth=mock_auth,
                issue_id=uuid4(),
                payload=sample_payload,
            )

            assert action == "review"
            assert inv_id is None
            mock_notif.notify.assert_called_once()

    async def test_issue_only_action_no_investigation(
        self,
        mock_db: AsyncMock,
        mock_request: MagicMock,
        mock_auth: MagicMock,
        sample_payload: GenericWebhookPayload,
    ) -> None:
        """Test that issue_only action does not start investigation."""
        from unittest.mock import AsyncMock, patch

        from dataing.adapters.db.team_policy_repository import PolicyAction
        from dataing.entrypoints.api.routes.integrations import _evaluate_and_apply_policy
        from dataing.services.policy import PolicyResult, QueueConfig

        team_id = uuid4()

        with (
            patch("dataing.entrypoints.api.routes.integrations.TeamPolicyRepository") as MockRepo,
            patch("dataing.entrypoints.api.routes.integrations.PolicyService") as MockPolicyService,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_default_team_for_tenant = AsyncMock(return_value=team_id)

            mock_policy_svc = MockPolicyService.return_value
            mock_policy_svc.evaluate = AsyncMock(
                return_value=PolicyResult(
                    action=PolicyAction.ISSUE_ONLY,
                    queue_config=QueueConfig(),
                    source="system_default",
                    team_id=team_id,
                )
            )

            mock_db.execute = AsyncMock()

            action, inv_id = await _evaluate_and_apply_policy(
                request=mock_request,
                db=mock_db,
                auth=mock_auth,
                issue_id=uuid4(),
                payload=sample_payload,
            )

            assert action == "issue_only"
            assert inv_id is None

    async def test_auto_action_starts_investigation_when_temporal_available(
        self,
        mock_db: AsyncMock,
        mock_auth: MagicMock,
        sample_payload: GenericWebhookPayload,
    ) -> None:
        """Test that auto action starts investigation when Temporal is available."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from dataing.adapters.db.team_policy_repository import PolicyAction
        from dataing.entrypoints.api.routes.integrations import _evaluate_and_apply_policy
        from dataing.services.policy import PolicyResult, QueueConfig

        team_id = uuid4()

        # Create mock request with Temporal client
        mock_request = MagicMock()
        mock_temporal = AsyncMock()
        mock_temporal.start_investigation = AsyncMock()
        mock_request.app.state.temporal_client = mock_temporal

        with (
            patch("dataing.entrypoints.api.routes.integrations.TeamPolicyRepository") as MockRepo,
            patch("dataing.entrypoints.api.routes.integrations.PolicyService") as MockPolicyService,
            patch("dataing.entrypoints.api.deps.resolve_datasource_id") as mock_resolve_ds,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_default_team_for_tenant = AsyncMock(return_value=team_id)

            mock_policy_svc = MockPolicyService.return_value
            mock_policy_svc.evaluate = AsyncMock(
                return_value=PolicyResult(
                    action=PolicyAction.AUTO,
                    queue_config=QueueConfig(),
                    source="team_default",
                    team_id=team_id,
                )
            )

            mock_resolve_ds.return_value = uuid4()
            mock_db.execute = AsyncMock()

            action, inv_id = await _evaluate_and_apply_policy(
                request=mock_request,
                db=mock_db,
                auth=mock_auth,
                issue_id=uuid4(),
                payload=sample_payload,
            )

            assert action == "auto"
            assert inv_id is not None
            mock_temporal.start_investigation.assert_called_once()

    async def test_auto_action_without_temporal_returns_none_investigation(
        self,
        mock_db: AsyncMock,
        mock_request: MagicMock,
        mock_auth: MagicMock,
        sample_payload: GenericWebhookPayload,
    ) -> None:
        """Test that auto action without Temporal returns None investigation_id."""
        from unittest.mock import AsyncMock, patch

        from dataing.adapters.db.team_policy_repository import PolicyAction
        from dataing.entrypoints.api.routes.integrations import _evaluate_and_apply_policy
        from dataing.services.policy import PolicyResult, QueueConfig

        team_id = uuid4()

        with (
            patch("dataing.entrypoints.api.routes.integrations.TeamPolicyRepository") as MockRepo,
            patch("dataing.entrypoints.api.routes.integrations.PolicyService") as MockPolicyService,
        ):
            mock_repo = MockRepo.return_value
            mock_repo.get_default_team_for_tenant = AsyncMock(return_value=team_id)

            mock_policy_svc = MockPolicyService.return_value
            mock_policy_svc.evaluate = AsyncMock(
                return_value=PolicyResult(
                    action=PolicyAction.AUTO,
                    queue_config=QueueConfig(),
                    source="team_default",
                    team_id=team_id,
                )
            )

            mock_db.execute = AsyncMock()

            action, inv_id = await _evaluate_and_apply_policy(
                request=mock_request,
                db=mock_db,
                auth=mock_auth,
                issue_id=uuid4(),
                payload=sample_payload,
            )

            assert action == "auto"
            assert inv_id is None  # No Temporal configured


class TestJsonSchemaValidation:
    """Tests for JSON Schema validation functions."""

    def test_decode_header_schema_valid(self) -> None:
        """Test decoding valid base64-encoded schema from header."""
        schema = {"type": "object", "properties": {"title": {"type": "string"}}}
        encoded = base64.b64encode(json.dumps(schema).encode()).decode()

        result = decode_header_schema(encoded)
        assert result == schema

    def test_decode_header_schema_invalid_base64(self) -> None:
        """Test decoding invalid base64 raises error."""
        with pytest.raises(HTTPException) as exc_info:
            decode_header_schema("not-valid-base64!!!")

        assert exc_info.value.status_code == 400
        assert "Invalid base64" in exc_info.value.detail

    def test_decode_header_schema_invalid_json(self) -> None:
        """Test decoding invalid JSON raises error."""
        # Valid base64 but invalid JSON
        encoded = base64.b64encode(b"not json content").decode()

        with pytest.raises(HTTPException) as exc_info:
            decode_header_schema(encoded)

        assert exc_info.value.status_code == 400
        assert "Invalid JSON in schema" in exc_info.value.detail

    def test_decode_header_schema_invalid_schema(self) -> None:
        """Test decoding invalid JSON Schema raises error."""
        # Valid JSON but invalid schema structure
        invalid_schema = {"type": "not_a_real_type"}
        encoded = base64.b64encode(json.dumps(invalid_schema).encode()).decode()

        with pytest.raises(HTTPException) as exc_info:
            decode_header_schema(encoded)

        assert exc_info.value.status_code == 400
        assert "Invalid JSON Schema" in exc_info.value.detail

    def test_validate_payload_against_schema_valid(self) -> None:
        """Test validating valid payload passes."""
        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        }
        payload = {"title": "Test Issue"}

        # Should not raise
        validate_payload_against_schema(payload, schema)

    def test_validate_payload_against_schema_missing_required(self) -> None:
        """Test validating payload with missing required field fails."""
        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        }
        payload = {"description": "Missing title"}

        with pytest.raises(HTTPException) as exc_info:
            validate_payload_against_schema(payload, schema)

        assert exc_info.value.status_code == 400
        assert "Schema validation failed" in exc_info.value.detail
        assert "'title' is a required property" in exc_info.value.detail

    def test_validate_payload_against_schema_wrong_type(self) -> None:
        """Test validating payload with wrong type fails."""
        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}, "severity": {"type": "string"}},
        }
        payload = {"title": "Test", "severity": 123}  # Should be string

        with pytest.raises(HTTPException) as exc_info:
            validate_payload_against_schema(payload, schema)

        assert exc_info.value.status_code == 400
        assert "Schema validation failed" in exc_info.value.detail
        assert "is not of type" in exc_info.value.detail

    def test_validate_payload_multiple_errors(self) -> None:
        """Test multiple validation errors are reported."""
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "count": {"type": "integer", "minimum": 0},
            },
            "required": ["title"],
        }
        payload = {"count": -1}  # Missing title AND count too low

        with pytest.raises(HTTPException) as exc_info:
            validate_payload_against_schema(payload, schema)

        assert exc_info.value.status_code == 400
        # Should contain multiple error messages
        detail = exc_info.value.detail
        assert "Schema validation failed" in detail

    def test_validate_complex_schema(self) -> None:
        """Test validating against complex schema works."""
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "labels": {"type": "array", "items": {"type": "string"}},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            },
            "required": ["title"],
        }

        # Valid payload
        payload = {
            "title": "Test Issue",
            "labels": ["bug", "urgent"],
            "severity": "high",
        }
        validate_payload_against_schema(payload, schema)  # Should not raise

        # Invalid enum value
        invalid_payload = {
            "title": "Test",
            "severity": "extreme",  # Not in enum
        }
        with pytest.raises(HTTPException):
            validate_payload_against_schema(invalid_payload, schema)

    def test_get_configured_schema_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test get_configured_schema returns None when not set."""
        # Clear cache to ensure fresh state
        from dataing.entrypoints.api.routes.integrations import _parse_json_schema

        _parse_json_schema.cache_clear()

        monkeypatch.delenv("WEBHOOK_JSON_SCHEMA", raising=False)
        assert get_configured_schema() is None

    def test_get_configured_schema_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test get_configured_schema returns parsed schema when set."""
        from dataing.entrypoints.api.routes.integrations import _parse_json_schema

        _parse_json_schema.cache_clear()

        schema = {"type": "object", "properties": {"title": {"type": "string"}}}
        monkeypatch.setenv("WEBHOOK_JSON_SCHEMA", json.dumps(schema))

        result = get_configured_schema()
        assert result == schema
