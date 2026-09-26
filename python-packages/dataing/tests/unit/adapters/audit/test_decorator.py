"""Tests for the @audited route decorator."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.requests import Request

from dataing.adapters.audit import audited, get_client_ip
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
        http_request = _make_request(audit_repo)
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
