"""Tests for JWT token service."""

import warnings
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from dataing.core.auth.jwt import (
    JWTSecretKeyError,
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


class TestSecretKey:
    """Tokens are only signed and verified with a configured key of 32+ bytes."""

    @pytest.mark.parametrize(
        "key",
        [None, "", "k" * 31, "dev-secret-change-in-production"],
        ids=["unset", "empty", "31-bytes", "old-default"],
    )
    def test_refuses_missing_or_short_key(
        self, monkeypatch: pytest.MonkeyPatch, key: str | None
    ) -> None:
        """No token is issued or verified without a proper key."""
        if key is None:
            monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        else:
            monkeypatch.setenv("JWT_SECRET_KEY", key)

        with pytest.raises(JWTSecretKeyError, match="openssl rand -hex 32"):
            create_access_token(user_id="u", org_id="o", role="admin", teams=[])
        with pytest.raises(JWTSecretKeyError):
            create_refresh_token(user_id="u")
        with pytest.raises(JWTSecretKeyError):
            decode_token("header.payload.signature")

    def test_accepts_a_32_byte_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A key of exactly 32 bytes signs and verifies tokens."""
        monkeypatch.setenv("JWT_SECRET_KEY", "k" * 32)

        token = create_access_token(user_id="u", org_id="o", role="admin", teams=[])

        assert decode_token(token).sub == "u"

    def test_rejects_a_token_forged_with_the_old_default_key(self) -> None:
        """A token signed with the key that used to ship in the source is refused."""
        now = datetime.now(UTC)
        claims = {
            "sub": "attacker",
            "org_id": str(uuid4()),
            "role": "owner",
            "teams": [],
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
        }
        with warnings.catch_warnings():  # pyjwt warns that this old key is too short
            warnings.simplefilter("ignore")
            forged = jwt.encode(claims, "dev-secret-change-in-production", algorithm="HS256")

        with pytest.raises(TokenError, match="Signature verification failed"):
            decode_token(forged)
