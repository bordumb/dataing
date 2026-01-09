"""Tests for audit decorator."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from dataing_ee.adapters.audit.decorator import audited, get_client_ip
from fastapi import Request
from starlette.datastructures import Headers


class TestGetClientIp:
    """Tests for get_client_ip helper."""

    def test_extracts_from_x_forwarded_for(self) -> None:
        """Test extracting IP from X-Forwarded-For header."""
        request = MagicMock(spec=Request)
        request.headers = Headers({"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
        request.client = MagicMock(host="127.0.0.1")

        ip = get_client_ip(request)

        assert ip == "1.2.3.4"

    def test_falls_back_to_client_host(self) -> None:
        """Test falling back to request.client.host."""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.client = MagicMock(host="192.168.1.1")

        ip = get_client_ip(request)

        assert ip == "192.168.1.1"

    def test_returns_none_when_no_client(self) -> None:
        """Test returning None when no client info available."""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.client = None

        ip = get_client_ip(request)

        assert ip is None


class TestAuditedDecorator:
    """Tests for @audited decorator."""

    async def test_decorator_records_audit_log(self) -> None:
        """Test that decorator records audit log after success."""
        mock_repo = AsyncMock()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({"user-agent": "TestAgent"})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "POST"
        mock_request.url = MagicMock(path="/api/v1/teams")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = mock_repo

        @audited(action="team.create", resource_type="team")
        async def create_team(request: Request) -> dict:
            return {"id": str(uuid4()), "name": "Engineering"}

        result = await create_team(request=mock_request)

        assert result["name"] == "Engineering"
        mock_repo.record.assert_called_once()

    async def test_decorator_extracts_resource_id_from_result(self) -> None:
        """Test that decorator extracts resource_id from result."""
        mock_repo = AsyncMock()
        resource_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "POST"
        mock_request.url = MagicMock(path="/api/v1/teams")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = mock_repo

        @audited(action="team.create", resource_type="team")
        async def create_team(request: Request) -> dict:
            return {"id": str(resource_id), "name": "Engineering"}

        await create_team(request=mock_request)

        call_args = mock_repo.record.call_args[0][0]
        assert call_args.resource_id == resource_id
        assert call_args.resource_name == "Engineering"

    async def test_decorator_extracts_resource_id_from_kwargs(self) -> None:
        """Test that decorator extracts resource_id from path params."""
        mock_repo = AsyncMock()
        team_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "DELETE"
        mock_request.url = MagicMock(path=f"/api/v1/teams/{team_id}")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = mock_repo

        @audited(action="team.delete", resource_type="team")
        async def delete_team(request: Request, team_id: str) -> None:
            return None

        await delete_team(request=mock_request, team_id=str(team_id))

        call_args = mock_repo.record.call_args[0][0]
        assert call_args.resource_id == team_id

    async def test_decorator_continues_without_audit_repo(self) -> None:
        """Test that decorator doesn't fail if audit repo not configured."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "POST"
        mock_request.url = MagicMock(path="/api/v1/teams")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = None

        @audited(action="team.create", resource_type="team")
        async def create_team(request: Request) -> dict:
            return {"id": str(uuid4()), "name": "Engineering"}

        result = await create_team(request=mock_request)

        assert result["name"] == "Engineering"

    async def test_decorator_handles_audit_failure_gracefully(self) -> None:
        """Test that decorator doesn't fail the request if auditing fails."""
        mock_repo = AsyncMock()
        mock_repo.record.side_effect = Exception("Database error")
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "POST"
        mock_request.url = MagicMock(path="/api/v1/teams")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = mock_repo

        @audited(action="team.create", resource_type="team")
        async def create_team(request: Request) -> dict:
            return {"id": str(uuid4()), "name": "Engineering"}

        result = await create_team(request=mock_request)

        assert result["name"] == "Engineering"

    async def test_decorator_with_request_as_positional_arg(self) -> None:
        """Test that decorator finds request when passed as positional arg."""
        mock_repo = AsyncMock()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "POST"
        mock_request.url = MagicMock(path="/api/v1/teams")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = mock_repo

        @audited(action="team.create", resource_type="team")
        async def create_team(request: Request) -> dict:
            return {"id": str(uuid4()), "name": "Engineering"}

        result = await create_team(mock_request)

        assert result["name"] == "Engineering"
        mock_repo.record.assert_called_once()
