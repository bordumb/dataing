"""Tests for the @audited route decorator."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

from dataing.adapters.audit import (
    audited,
    get_client_ip,
    record_audit,
    suppress_audit_errors,
    was_audited,
)
from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.middleware.auth import ApiKeyContext
from dataing.entrypoints.api.middleware.jwt_auth import JwtContext

_DEFAULT_HEADERS = [
    (b"user-agent", b"pytest-agent"),
    (b"x-forwarded-for", b"203.0.113.7, 10.0.0.1"),
]


class CreateWidgetRequest(BaseModel):
    """JSON body named `request`, like the EE settings handlers."""

    name: str


def _make_request(
    audit_repo: Any = None,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] | None = ("10.0.0.1", 50000),
    path_params: dict[str, str] | None = None,
) -> Request:
    """Build a real Starlette request whose app carries the given audit repository."""
    app = FastAPI()
    app.state.audit_repo = audit_repo
    scope: dict[str, Any] = {
        "type": "http",
        "app": app,
        "method": "POST",
        "path": "/api/v1/widgets",
        "query_string": b"",
        "headers": _DEFAULT_HEADERS if headers is None else headers,
        "path_params": path_params or {},
    }
    if client is not None:
        scope["client"] = client
    return Request(scope)


def _api_key_context(tenant_id: UUID, user_id: UUID) -> ApiKeyContext:
    """Build the context verify_api_key stores on request.state.auth_context."""
    return ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="acme",
        tenant_name="Acme",
        user_id=user_id,
        scopes=["read", "write", "admin"],
    )


class TestGetClientIp:
    """Tests for get_client_ip helper."""

    def test_extracts_from_x_forwarded_for(self) -> None:
        """Test extracting IP from X-Forwarded-For header."""
        request = _make_request(headers=[(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")])

        assert get_client_ip(request) == "1.2.3.4"

    def test_falls_back_to_client_host(self) -> None:
        """Test falling back to request.client.host."""
        request = _make_request(headers=[], client=("192.168.1.1", 50000))

        assert get_client_ip(request) == "192.168.1.1"

    def test_returns_none_when_no_client(self) -> None:
        """Test returning None when no client info available."""
        request = _make_request(headers=[], client=None)

        assert get_client_ip(request) is None


class TestRecordAudit:
    """Tests for record_audit, used by routes @audited can't cover."""

    async def test_records_entry_with_request_details(self) -> None:
        """Explicit fields are combined with the caller's IP, user agent, method and path."""
        audit_repo = AsyncMock()
        tenant_id = uuid4()

        await record_audit(
            _make_request(audit_repo),
            action="auth.login_failed",
            tenant_id=tenant_id,
            actor_email="bob@example.com",
            resource_type="user",
            resource_name="bob@example.com",
            status_code=401,
            metadata={"reason": "Invalid email or password"},
        )

        audit_repo.record.assert_awaited_once()
        entry = audit_repo.record.await_args.args[0]
        assert entry.action == "auth.login_failed"
        assert entry.tenant_id == tenant_id
        assert entry.actor_id is None
        assert entry.actor_email == "bob@example.com"
        assert entry.resource_type == "user"
        assert entry.resource_name == "bob@example.com"
        assert entry.status_code == 401
        assert entry.metadata == {"reason": "Invalid email or password"}
        assert entry.actor_ip == "203.0.113.7"
        assert entry.actor_user_agent == "pytest-agent"
        assert entry.request_method == "POST"
        assert entry.request_path == "/api/v1/widgets"

    async def test_never_raises_when_recording_fails(self) -> None:
        """A failure to audit must not fail the request."""
        audit_repo = AsyncMock()
        audit_repo.record.side_effect = RuntimeError("database down")

        await record_audit(_make_request(audit_repo), action="auth.login", tenant_id=uuid4())

        audit_repo.record.assert_awaited_once()

    async def test_skips_without_audit_repo(self) -> None:
        """Nothing to record into, nothing raised."""
        await record_audit(_make_request(audit_repo=None), action="auth.login", tenant_id=uuid4())

    async def test_marks_request_once_recorded(self) -> None:
        """EE's middleware skips its generic row for requests that have an entry."""
        request = _make_request(AsyncMock())
        assert not was_audited(request)

        await record_audit(request, action="auth.login", tenant_id=uuid4())

        assert was_audited(request)

    async def test_leaves_request_unmarked_when_recording_fails(self) -> None:
        """The middleware's generic row stays as a fallback."""
        audit_repo = AsyncMock()
        audit_repo.record.side_effect = RuntimeError("database down")
        request = _make_request(audit_repo)

        await record_audit(request, action="auth.login", tenant_id=uuid4())

        assert not was_audited(request)

    async def test_adds_request_id_to_metadata(self) -> None:
        """Entries carry the request ID EE's middleware returns as X-Request-ID."""
        audit_repo = AsyncMock()
        request = _make_request(audit_repo)
        request.state.request_id = "req-123"

        await record_audit(
            request, action="auth.login_failed", tenant_id=uuid4(), metadata={"reason": "nope"}
        )

        entry = audit_repo.record.await_args.args[0]
        assert entry.metadata == {"reason": "nope", "request_id": "req-123"}


class TestSuppressAuditErrors:
    """Tests for suppress_audit_errors."""

    def test_swallows_errors(self) -> None:
        """Errors while preparing an audit entry don't reach the caller."""
        with suppress_audit_errors("auth.login"):
            raise RuntimeError("lookup failed")


class TestAuditedDecorator:
    """Tests for @audited."""

    async def test_records_when_json_body_is_named_request(self) -> None:
        """A body parameter named `request` must not hide the real Request."""
        audit_repo = AsyncMock()
        tenant_id, user_id, widget_id = uuid4(), uuid4(), uuid4()
        http_request = _make_request(audit_repo)
        http_request.state.auth_context = _api_key_context(tenant_id, user_id)

        @audited(action="widget.create", resource_type="widget")
        async def create_widget(
            request: CreateWidgetRequest, http_request: Request
        ) -> dict[str, str]:
            return {"id": str(widget_id), "name": request.name}

        result = await create_widget(
            request=CreateWidgetRequest(name="Gizmo"), http_request=http_request
        )

        assert result == {"id": str(widget_id), "name": "Gizmo"}
        audit_repo.record.assert_awaited_once()
        entry = audit_repo.record.await_args.args[0]
        assert entry.action == "widget.create"
        assert entry.resource_type == "widget"
        assert entry.tenant_id == tenant_id
        assert entry.actor_id == user_id
        assert entry.resource_id == widget_id
        assert entry.resource_name == "Gizmo"
        assert entry.request_method == "POST"
        assert entry.request_path == "/api/v1/widgets"
        assert entry.actor_ip == "203.0.113.7"
        assert entry.actor_user_agent == "pytest-agent"

    async def test_records_actor_from_jwt_context(self) -> None:
        """Handlers behind verify_jwt (e.g. RequireAdmin) are attributed to the JWT user."""
        audit_repo = AsyncMock()
        org_id, admin_id = uuid4(), uuid4()
        http_request = _make_request(audit_repo)
        http_request.state.user = JwtContext(
            user_id=str(admin_id), org_id=str(org_id), role=OrgRole.ADMIN, teams=[]
        )

        @audited(action="user.remove", resource_type="user")
        async def remove_member(user_id: UUID, http_request: Request) -> None:
            return None

        await remove_member(user_id=uuid4(), http_request=http_request)

        audit_repo.record.assert_awaited_once()
        entry = audit_repo.record.await_args.args[0]
        assert entry.tenant_id == org_id
        assert entry.actor_id == admin_id

    async def test_finds_request_passed_positionally(self) -> None:
        """Test that the request is found when passed as a positional arg."""
        audit_repo = AsyncMock()
        http_request = _make_request(audit_repo)
        http_request.state.auth_context = _api_key_context(uuid4(), uuid4())

        @audited(action="team.create", resource_type="team")
        async def create_team(http_request: Request) -> dict[str, str]:
            return {"id": str(uuid4()), "name": "Engineering"}

        await create_team(http_request)

        audit_repo.record.assert_awaited_once()

    async def test_takes_resource_id_from_path_params(self) -> None:
        """Test that resource_id falls back to path params when the result has none."""
        audit_repo = AsyncMock()
        team_id = uuid4()
        http_request = _make_request(audit_repo, path_params={"team_id": str(team_id)})
        http_request.state.auth_context = _api_key_context(uuid4(), uuid4())

        @audited(action="team.delete", resource_type="team")
        async def delete_team(http_request: Request, team_id: UUID) -> None:
            return None

        await delete_team(http_request=http_request, team_id=team_id)

        entry = audit_repo.record.await_args.args[0]
        assert entry.resource_id == team_id

    async def test_skips_unauthenticated_requests(self) -> None:
        """Test that no entry is recorded when no auth dependency identified the caller."""
        audit_repo = AsyncMock()
        http_request = _make_request(audit_repo)

        @audited(action="widget.create", resource_type="widget")
        async def create_widget(http_request: Request) -> str:
            return "created"

        assert await create_widget(http_request=http_request) == "created"
        audit_repo.record.assert_not_awaited()

    async def test_continues_without_audit_repo(self) -> None:
        """Test that the handler still succeeds if no audit repo is configured."""
        http_request = _make_request(audit_repo=None)
        http_request.state.auth_context = _api_key_context(uuid4(), uuid4())

        @audited(action="widget.create", resource_type="widget")
        async def create_widget(http_request: Request) -> str:
            return "created"

        assert await create_widget(http_request=http_request) == "created"

    async def test_audit_failure_does_not_fail_the_request(self) -> None:
        """Test that the handler result is returned even if recording fails."""
        audit_repo = AsyncMock()
        audit_repo.record.side_effect = RuntimeError("database down")
        http_request = _make_request(audit_repo)
        http_request.state.auth_context = _api_key_context(uuid4(), uuid4())

        @audited(action="widget.create", resource_type="widget")
        async def create_widget(http_request: Request) -> str:
            return "created"

        assert await create_widget(http_request=http_request) == "created"
        audit_repo.record.assert_awaited_once()

    def test_rejects_handler_without_request_parameter(self) -> None:
        """FastAPI passes no Request to such a handler, so it could never record."""
        with pytest.raises(TypeError, match="widget.create"):

            @audited(action="widget.create", resource_type="widget")
            async def create_widget(request: CreateWidgetRequest) -> None:
                return None

    def test_accepts_postponed_request_annotation(self) -> None:
        """Route modules use `from __future__ import annotations`, so hints are strings."""

        @audited(action="widget.delete", resource_type="widget")
        async def delete_widget(http_request: "Request") -> None:
            return None


def _serve(router: APIRouter, audit_repo: AsyncMock) -> TestClient:
    """Serve router to an authenticated caller, recording into audit_repo."""
    app = FastAPI()
    app.state.audit_repo = audit_repo

    async def authenticate(request: Request) -> None:
        request.state.auth_context = _api_key_context(uuid4(), uuid4())

    app.include_router(router, dependencies=[Depends(authenticate)])
    return TestClient(app)


def _recorded(audit_repo: AsyncMock) -> Any:
    """Return the single entry recorded."""
    audit_repo.record.assert_awaited_once()
    return audit_repo.record.await_args.args[0]


class TestAuditedRoutes:
    """Tests for @audited on routes FastAPI serves."""

    def test_records_the_route_status_code(self) -> None:
        """A 201 route is recorded as 201."""
        audit_repo, router = AsyncMock(), APIRouter()

        @router.post("/widgets", status_code=201)
        @audited(action="widget.create", resource_type="widget")
        async def create_widget(http_request: Request) -> dict[str, str]:
            return {"id": str(uuid4()), "name": "Gizmo"}

        _serve(router, audit_repo).post("/widgets")

        assert _recorded(audit_repo).status_code == 201

    def test_records_the_status_code_of_a_returned_response(self) -> None:
        """A handler returning Response(status_code=204) is recorded as 204."""
        audit_repo, router = AsyncMock(), APIRouter()

        @router.delete("/widgets/{widget_id}")
        @audited(action="widget.delete", resource_type="widget")
        async def delete_widget(http_request: Request, widget_id: UUID) -> Response:
            return Response(status_code=204)

        _serve(router, audit_repo).delete(f"/widgets/{uuid4()}")

        assert _recorded(audit_repo).status_code == 204

    def test_takes_resource_id_from_path_param_named_for_resource_type(self) -> None:
        """A delete returning a bare Response is recorded against {resource_type}_id."""
        audit_repo, router = AsyncMock(), APIRouter()
        webhook_id = uuid4()

        @router.delete("/webhooks/{webhook_id}", status_code=204, response_class=Response)
        @audited(action="webhook.delete", resource_type="webhook")
        async def delete_webhook(http_request: Request, webhook_id: UUID) -> Response:
            return Response(status_code=204)

        _serve(router, audit_repo).delete(f"/webhooks/{webhook_id}")

        assert _recorded(audit_repo).resource_id == webhook_id

    def test_takes_resource_id_from_named_path_param(self) -> None:
        """resource_id_param names the path param when it isn't {resource_type}_id."""
        audit_repo, router = AsyncMock(), APIRouter()
        key_id = uuid4()

        @router.delete("/api-keys/{key_id}", status_code=204, response_class=Response)
        @audited(action="api_key.revoke", resource_type="api_key", resource_id_param="key_id")
        async def revoke_api_key(http_request: Request, key_id: UUID) -> Response:
            return Response(status_code=204)

        _serve(router, audit_repo).delete(f"/api-keys/{key_id}")

        assert _recorded(audit_repo).resource_id == key_id

    def test_member_removal_is_recorded_against_the_team(self) -> None:
        """The team is the resource; the removed member stays in the path params."""
        audit_repo, router = AsyncMock(), APIRouter()
        team_id, user_id = uuid4(), uuid4()

        @router.delete(
            "/teams/{team_id}/members/{user_id}", status_code=204, response_class=Response
        )
        @audited(action="team.member_remove", resource_type="team")
        async def remove_team_member(
            http_request: Request, team_id: UUID, user_id: UUID
        ) -> Response:
            return Response(status_code=204)

        _serve(router, audit_repo).delete(f"/teams/{team_id}/members/{user_id}")

        entry = _recorded(audit_repo)
        assert entry.resource_id == team_id
        assert entry.metadata == {"path_params": {"team_id": str(team_id), "user_id": str(user_id)}}

    def test_rejects_resource_id_param_the_handler_lacks(self) -> None:
        """A misspelled resource_id_param fails at import instead of recording None."""
        with pytest.raises(TypeError, match="key_id"):

            @audited(action="api_key.revoke", resource_type="api_key", resource_id_param="key_id")
            async def revoke_api_key(http_request: Request, api_key_id: UUID) -> None:
                return None
