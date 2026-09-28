"""Tests for the Enterprise Edition ASGI app."""

import os
import subprocess
import sys

import pytest
from dataing_ee.entrypoints.api.app import app
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

# Imports the EE app and prints how many FastAPI apps were constructed along the way.
_COUNT_APPS_BUILT_BY_IMPORT = """
import fastapi

built = 0
fastapi_init = fastapi.FastAPI.__init__


def counting_init(self, *args, **kwargs):
    global built
    built += 1
    fastapi_init(self, *args, **kwargs)


fastapi.FastAPI.__init__ = counting_init
import dataing_ee.entrypoints.api.app
print(built)
"""


def test_importing_app_builds_one_fastapi_app() -> None:
    """Importing the EE app builds the EE app only, not a throwaway CE app as well.

    Every build runs init_telemetry(), configure_logging() and the FastAPI instrumentor.
    The import runs in a fresh interpreter: this test process has usually imported the
    app already, and importing it again would build nothing.
    """
    result = subprocess.run(
        [sys.executable, "-c", _COUNT_APPS_BUILT_BY_IMPORT],
        capture_output=True,
        text=True,
        # Resolve imports exactly as this test process does.
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert int(result.stdout.splitlines()[-1]) == 1


def test_health_reports_enterprise_edition() -> None:
    """GET /health identifies the server as the Enterprise Edition."""
    response = TestClient(app).get("/health")

    assert response.json() == {"status": "healthy", "edition": "enterprise"}


def test_app_has_one_health_route() -> None:
    """EE replaces CE's /health route instead of adding a second one that never matches."""
    health_routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path == "/health"]

    assert len(health_routes) == 1


def test_ee_app_refuses_to_start_without_a_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """The EE app, which SSO logins sign tokens for, needs the JWT key as well."""
    from dataing_ee.entrypoints.api.app import create_ee_app

    from dataing.core.auth.jwt import JWTSecretKeyError

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(JWTSecretKeyError):
        create_ee_app()
