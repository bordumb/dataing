"""Tests for JWT token service."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from dataing.core.auth.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from dataing.core.auth.types import TokenPayload


class TestCreateAccessToken:
    """Test access token creation."""

    def test_creates_valid_jwt(self) -> None:
        """Should create a valid JWT string."""
        user_id = uuid4()
        org_id = uuid4()

        token = create_access_token(
            user_id=str(user_id),
            org_id=str(org_id),
            role="admin",
            teams=["team-1"],
        )

        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts separated by dots
        assert len(token.split(".")) == 3

    def test_token_contains_claims(self) -> None:
        """Token should contain correct claims."""
        user_id = str(uuid4())
        org_id = str(uuid4())

        token = create_access_token(
            user_id=user_id,
            org_id=org_id,
            role="member",
            teams=["team-1", "team-2"],
        )

        payload = decode_token(token)
        assert payload.sub == user_id
        assert payload.org_id == org_id
        assert payload.role == "member"
        assert payload.teams == ["team-1", "team-2"]


class TestDecodeToken:
    """Test token decoding."""

    def test_decode_valid_token(self) -> None:
        """Should decode a valid token."""
        token = create_access_token(
            user_id="user-123",
            org_id="org-456",
            role="admin",
            teams=[],
        )

        payload = decode_token(token)
        assert isinstance(payload, TokenPayload)
        assert payload.sub == "user-123"

    def test_decode_invalid_token_raises(self) -> None:
        """Should raise TokenError for invalid token."""
        with pytest.raises(TokenError):
            decode_token("invalid.token.here")


class TestRefreshToken:
    """Test refresh token creation."""

    def test_refresh_token_longer_expiry(self) -> None:
        """Refresh token should have longer expiry than access token."""
        access = create_access_token(
            user_id="user-123",
            org_id="org-456",
            role="admin",
            teams=[],
        )
        refresh = create_refresh_token(user_id="user-123")

        access_payload = decode_token(access)
        refresh_payload = decode_token(refresh)

        # Refresh should expire later than access
        assert refresh_payload.exp > access_payload.exp
