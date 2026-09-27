"""Unit tests for audit middleware."""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing_ee.entrypoints.api.middleware.audit import AuditMiddleware
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from dataing.adapters.audit import audited, record_audit


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

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://hooks.slack.com/services/T000/B000/SECRETTOKEN", "https://hooks.slack.com"),
            (
                "https://example.webhook.office.com/webhookb2/G1@G2/IncomingWebhook/SECRETTOKEN/G3",
                "https://example.webhook.office.com",
            ),
            ("https://discord.com/api/webhooks/123/SECRETTOKEN", "https://discord.com"),
        ],
        ids=["slack", "teams", "discord"],
    )
    def test_sanitize_body_reduces_webhook_url_to_scheme_and_host(
        self,
        middleware: AuditMiddleware,
        url: str,
        expected: str,
    ) -> None:
        """Test that a webhook URL loses the bearer secret embedded in its path."""
        body = json.dumps({"url": url, "events": ["investigation.completed"]}).encode()

        result = middleware._sanitize_body(body)

        assert result == {"url": expected, "events": ["investigation.completed"]}

    def test_sanitize_body_reduces_url_inside_text(self, middleware: AuditMiddleware) -> None:
        """Test that a URL embedded in free text is reduced in place."""
        body = json.dumps(
            {"note": "Posting to https://hooks.slack.com/services/T000/B000/SECRETTOKEN now"}
        ).encode()

        result = middleware._sanitize_body(body)

        assert result == {"note": "Posting to https://hooks.slack.com now"}

    def test_sanitize_body_replaces_unparseable_url(self, middleware: AuditMiddleware) -> None:
        """Test that a URL without a parseable host is replaced, never stored raw."""
        body = json.dumps({"url": "https://[hooks.slack.com/services/T000/SECRETTOKEN"}).encode()

        result = middleware._sanitize_body(body)

        assert result == {"url": "<invalid url>"}

    def test_sanitize_body_reduces_urls_inside_lists(self, middleware: AuditMiddleware) -> None:
        """Test that URLs are reduced at any list nesting level."""
        body = json.dumps(
            {
                "urls": ["https://hooks.slack.com/services/T000/B000/SECRETTOKEN"],
                "matrix": [["https://discord.com/api/webhooks/123/SECRETTOKEN"]],
            }
        ).encode()

        result = middleware._sanitize_body(body)

        assert result == {
            "urls": ["https://hooks.slack.com"],
            "matrix": [["https://discord.com"]],
        }

    def test_sanitize_body_scans_long_strings_in_linear_time(
        self,
        middleware: AuditMiddleware,
    ) -> None:
        """Test that URL scanning stays fast on a long run of scheme characters.

        Every POST, PUT and PATCH body is scanned on the event loop, authenticated or not.
        A pattern that backtracks quadratically takes seconds on 50 KB of letters.
        """
        blob = "a" * 50_000
        body = json.dumps({"blob": blob}).encode()

        start = time.perf_counter()
        result = middleware._sanitize_body(body)
        elapsed = time.perf_counter() - start

        assert result == {"blob": blob}
        assert elapsed < 1.0

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

    def test_redact_dict_caps_list_nesting(self, middleware: AuditMiddleware) -> None:
        """Test that nested lists count toward the depth limit, like nested dicts."""
        nested: list[Any] = ["leaf"]
        for _ in range(10):
            nested = [nested]

        result = middleware._redact_dict({"nested": nested})

        assert '{"_redacted": true}' in json.dumps(result)
        assert "leaf" not in json.dumps(result)

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

        await middleware.dispatch(request, call_next)

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

        await middleware.dispatch(request, call_next)

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

        await middleware.dispatch(request, call_next)

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

        await middleware.dispatch(request, call_next)

        request.body.assert_called_once()


def _request(method: str, audit_repo: AsyncMock | None = None) -> Request:
    """Build a real Starlette request to /api/v1/widgets."""
    app = FastAPI()
    app.state.audit_repo = audit_repo

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    return Request(
        {
            "type": "http",
            "app": app,
            "method": method,
            "path": "/api/v1/widgets",
            "query_string": b"",
            "headers": [],
        },
        receive,
    )


class TestAuditMiddlewareSkips:
    """The middleware writes a generic row only for mutations nothing else audited."""

    @pytest.fixture
    def middleware(self) -> AuditMiddleware:
        """Return an audit middleware whose row writer is observable."""
        middleware = AuditMiddleware(MagicMock())
        middleware._log_request = AsyncMock()  # type: ignore[method-assign]
        return middleware

    async def test_skips_reads(self, middleware: AuditMiddleware) -> None:
        """GETs get no row, but still get an X-Request-ID."""
        response = await middleware.dispatch(_request("GET"), AsyncMock(return_value=Response()))

        middleware._log_request.assert_not_called()  # type: ignore[attr-defined]
        assert "X-Request-ID" in response.headers

    async def test_skips_requests_with_an_audit_entry(self, middleware: AuditMiddleware) -> None:
        """A route that recorded its own entry gets no generic duplicate."""
        request = _request("POST", audit_repo=AsyncMock())

        async def audited_route(req: Request) -> Response:
            await record_audit(req, action="webhook.create", tenant_id=uuid4())
            return Response(status_code=201)

        await middleware.dispatch(request, audited_route)

        middleware._log_request.assert_not_called()  # type: ignore[attr-defined]

    async def test_logs_unaudited_mutations(self, middleware: AuditMiddleware) -> None:
        """Mutations nothing else audited keep their generic row."""
        await middleware.dispatch(_request("POST"), AsyncMock(return_value=Response()))

        middleware._log_request.assert_called_once()  # type: ignore[attr-defined]


def test_audited_route_gets_no_generic_row_in_a_real_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint's Request and the middleware's share state through the ASGI scope."""
    log_request = AsyncMock()
    monkeypatch.setattr(AuditMiddleware, "_log_request", log_request)
    app = FastAPI()
    app.state.audit_repo = AsyncMock()
    app.add_middleware(AuditMiddleware)

    async def authenticate(request: Request) -> None:
        request.state.auth_context = MagicMock(tenant_id=uuid4(), user_id=uuid4())

    @app.post("/widgets", dependencies=[Depends(authenticate)])
    @audited(action="widget.create", resource_type="widget")
    async def create_widget(http_request: Request) -> dict[str, str]:
        return {"id": str(uuid4())}

    @app.post("/gadgets", dependencies=[Depends(authenticate)])
    async def create_gadget() -> dict[str, str]:
        return {}

    client = TestClient(app)

    client.post("/widgets")
    assert log_request.call_count == 0

    client.post("/gadgets")
    assert log_request.call_count == 1
