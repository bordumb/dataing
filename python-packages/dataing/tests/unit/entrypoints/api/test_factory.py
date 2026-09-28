"""Tests for the CE app factory."""

import pytest

from dataing.core.auth.jwt import JWTSecretKeyError
from dataing.entrypoints.api.factory import create_app


def test_refuses_to_build_the_app_without_a_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API does not start when JWTs could only be signed with a missing key."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(JWTSecretKeyError):
        create_app()


def test_refuses_to_build_the_app_with_a_short_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key shorter than 32 bytes is refused at startup too."""
    monkeypatch.setenv("JWT_SECRET_KEY", "dev-secret-change-in-production")

    with pytest.raises(JWTSecretKeyError):
        create_app()
