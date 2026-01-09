"""Unit tests for audit middleware."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing_ee.entrypoints.api.middleware.audit import AuditMiddleware


class TestAuditMiddleware:
    """Tests for AuditMiddleware."""

    @pytest.fixture
    def mock_app(self) -> MagicMock:
        """Return a mock app."""
        return MagicMock()

    @pytest.fixture
    def middleware(self, mock_app: MagicMock) -> AuditMiddleware:
        """Return an audit middleware."""
        return AuditMiddleware(mock_app)

    def test_get_action_get(self, middleware: AuditMiddleware) -> None:
        """Test action determination for GET."""
        action = middleware._get_action("GET", "/api/v1/investigations")

        assert action == "investigations.read"

    def test_get_action_post(self, middleware: AuditMiddleware) -> None:
        """Test action determination for POST."""
        action = middleware._get_action("POST", "/api/v1/investigations")

        assert action == "investigations.created"

    def test_get_action_put(self, middleware: AuditMiddleware) -> None:
        """Test action determination for PUT."""
        action = middleware._get_action("PUT", "/api/v1/investigations/123")

        assert action == "investigations.updated"

    def test_get_action_delete(self, middleware: AuditMiddleware) -> None:
        """Test action determination for DELETE."""
        action = middleware._get_action("DELETE", "/api/v1/investigations/123")

        assert action == "investigations.deleted"

    def test_get_action_root(self, middleware: AuditMiddleware) -> None:
        """Test action determination for root path."""
        action = middleware._get_action("GET", "/api/v1/")

        assert action == "get.root"

    def test_parse_resource_with_id(self, middleware: AuditMiddleware) -> None:
        """Test parsing resource with ID."""
        resource_type, resource_id = middleware._parse_resource("/api/v1/investigations/123")

        assert resource_type == "investigations"
        assert resource_id == "123"

    def test_parse_resource_without_id(self, middleware: AuditMiddleware) -> None:
        """Test parsing resource without ID."""
        resource_type, resource_id = middleware._parse_resource("/api/v1/investigations")

        assert resource_type == "investigations"
        assert resource_id is None

    def test_parse_resource_empty(self, middleware: AuditMiddleware) -> None:
        """Test parsing empty path."""
        resource_type, resource_id = middleware._parse_resource("/")

        assert resource_type is None
        assert resource_id is None

    def test_sanitize_body_json(self, middleware: AuditMiddleware) -> None:
        """Test sanitizing JSON body."""
        body = b'{"name": "test", "email": "user@example.com"}'

        result = middleware._sanitize_body(body)

        assert result["name"] == "test"
        assert result["email"] == "user@example.com"

    def test_sanitize_body_redacts_sensitive(self, middleware: AuditMiddleware) -> None:
        """Test that sensitive fields are redacted."""
        body = b'{"username": "test", "password": "secret123"}'

        result = middleware._sanitize_body(body)

        assert result["username"] == "test"
        assert result["password"] == "[REDACTED]"

    def test_sanitize_body_redacts_nested(self, middleware: AuditMiddleware) -> None:
        """Test that nested sensitive fields are redacted."""
        body = b'{"user": {"name": "test", "api_key": "secret"}}'

        result = middleware._sanitize_body(body)

        assert result["user"]["name"] == "test"
        assert result["user"]["api_key"] == "[REDACTED]"

    def test_sanitize_body_invalid_json(self, middleware: AuditMiddleware) -> None:
        """Test handling invalid JSON body."""
        body = b"not valid json"

        result = middleware._sanitize_body(body)

        assert result is None

    def test_sanitize_body_none(self, middleware: AuditMiddleware) -> None:
        """Test handling None body."""
        result = middleware._sanitize_body(None)

        assert result is None

    def test_redact_dict_depth_limit(self, middleware: AuditMiddleware) -> None:
        """Test that redaction has a depth limit."""
        # Create deeply nested dict
        deep = {"level": 1}
        current = deep
        for i in range(10):
            current["nested"] = {"level": i + 2}
            current = current["nested"]

        result = middleware._redact_dict(deep)

        # Should not raise, should have depth limit
        assert result is not None

    def test_redact_dict_handles_lists(self, middleware: AuditMiddleware) -> None:
        """Test that lists are handled."""
        data = {
            "items": [
                {"name": "item1", "secret": "hidden"},
                {"name": "item2", "token": "hidden"},
            ]
        }

        result = middleware._redact_dict(data)

        assert result["items"][0]["name"] == "item1"
        assert result["items"][0]["secret"] == "[REDACTED]"

    async def test_dispatch_adds_request_id(
        self,
        middleware: AuditMiddleware,
    ) -> None:
        """Test that dispatch adds request ID."""
        request = MagicMock()
        request.state = MagicMock()
        request.url.path = "/api/test"
        request.method = "GET"

        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert hasattr(request.state, "request_id")
        assert "X-Request-ID" in result.headers

    async def test_dispatch_skips_health_checks(
        self,
        middleware: AuditMiddleware,
    ) -> None:
        """Test dispatch skips health check endpoints."""
        request = MagicMock()
        request.url.path = "/health"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        # Should not set request_id for health checks
        call_next.assert_called_once()

    async def test_dispatch_skips_options(
        self,
        middleware: AuditMiddleware,
    ) -> None:
        """Test dispatch skips OPTIONS requests."""
        request = MagicMock()
        request.url.path = "/api/test"
        request.method = "OPTIONS"

        response = MagicMock()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once()

    async def test_dispatch_disabled(self, mock_app: MagicMock) -> None:
        """Test dispatch when disabled."""
        middleware = AuditMiddleware(mock_app, enabled=False)
        request = MagicMock()
        request.state = MagicMock()
        request.url.path = "/api/test"
        request.method = "GET"

        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        call_next.assert_called_once()

    async def test_dispatch_captures_body_for_post(
        self,
        middleware: AuditMiddleware,
    ) -> None:
        """Test that body is captured for POST requests."""
        request = MagicMock()
        request.state = MagicMock()
        request.url.path = "/api/test"
        request.method = "POST"
        request.body = AsyncMock(return_value=b'{"data": "test"}')

        response = MagicMock()
        response.headers = {}
        response.status_code = 200
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        request.body.assert_called_once()
