"""Tests for JWT authentication middleware."""

from unittest.mock import MagicMock

import pytest
from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.middleware.jwt_auth import (
    JwtContext,
    require_role,
    verify_jwt,
)
from fastapi import HTTPException


class TestVerifyJwt:
    """Test JWT verification dependency."""

    @pytest.mark.asyncio
    async def test_valid_token(self) -> None:
        """Should return JwtContext for valid token."""
        from dataing.core.auth.jwt import create_access_token
        from fastapi.security import HTTPAuthorizationCredentials

        token = create_access_token(
            user_id="user-123",
            org_id="org-456",
            role="admin",
            teams=["team-1"],
        )

        mock_request = MagicMock()
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        context = await verify_jwt(mock_request, credentials)

        assert context.user_id == "user-123"
        assert context.org_id == "org-456"
        assert context.role == OrgRole.ADMIN

    @pytest.mark.asyncio
    async def test_missing_token(self) -> None:
        """Should raise 401 for missing token."""
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt(mock_request, None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token(self) -> None:
        """Should raise 401 for invalid token."""
        from fastapi.security import HTTPAuthorizationCredentials

        mock_request = MagicMock()
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid.token.here"
        )

        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt(mock_request, credentials)

        assert exc_info.value.status_code == 401


class TestRequireRole:
    """Test role requirement decorator."""

    @pytest.mark.asyncio
    async def test_allows_sufficient_role(self) -> None:
        """Should allow when user has required role or higher."""
        context = JwtContext(
            user_id="user-123",
            org_id="org-456",
            role=OrgRole.ADMIN,
            teams=["team-1"],
        )

        checker = require_role(OrgRole.MEMBER)
        result = await checker(context)

        assert result == context

    @pytest.mark.asyncio
    async def test_blocks_insufficient_role(self) -> None:
        """Should raise 403 when role is insufficient."""
        context = JwtContext(
            user_id="user-123",
            org_id="org-456",
            role=OrgRole.VIEWER,
            teams=[],
        )

        checker = require_role(OrgRole.ADMIN)

        with pytest.raises(HTTPException) as exc_info:
            await checker(context)

        assert exc_info.value.status_code == 403
