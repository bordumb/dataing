"""Route authorization policy for every mutating EE route.

Same tiers as the CE policy: viewers keep reads and feedback, members need
the write scope to change shared state, and admins alone manage org-wide
configuration, including outbound webhooks that send tenant data out.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dataing_ee.entrypoints.api.routes.audit import router as audit_router
from dataing_ee.entrypoints.api.routes.automation import router as automation_router
from dataing_ee.entrypoints.api.routes.integrations import router as integrations_router
from dataing_ee.entrypoints.api.routes.runbooks import router as runbooks_router
from dataing_ee.entrypoints.api.routes.scim import router as scim_router
from dataing_ee.entrypoints.api.routes.scim import validate_scim_token
from dataing_ee.entrypoints.api.routes.settings import router as settings_router
from dataing_ee.entrypoints.api.routes.sso import router as sso_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fixtures.route_authorization import (
    ANY_USER,
    JWT_VIAS,
    PUBLIC,
    SCOPE_ADMIN,
    SCOPE_WRITE,
    concrete_path,
    jwt_request_kwargs,
    mutating_routes,
    route_gate,
    scope_denied_detail,
    stub_service_dependencies,
)

from dataing.core.auth.types import OrgRole

SCIM_TOKEN = "scim_token"
EXTRA_GATES = {validate_scim_token: SCIM_TOKEN}

POLICY: dict[tuple[str, str], str] = {
    # automation.py: rules are admin-managed; a dry run only reads
    ("POST", "/rules"): SCOPE_ADMIN,
    ("DELETE", "/rules/{rule_id}"): SCOPE_ADMIN,
    ("PATCH", "/rules/{rule_id}"): SCOPE_ADMIN,
    ("POST", "/rules/{rule_id}/dry-run"): ANY_USER,
    ("POST", "/rules/{rule_id}/reset-circuit-breaker"): SCOPE_ADMIN,
    # integrations.py: provider webhooks authenticate by signature
    ("POST", "/integrations"): SCOPE_ADMIN,
    ("DELETE", "/integrations/{integration_id}"): SCOPE_ADMIN,
    ("PATCH", "/integrations/{integration_id}"): SCOPE_ADMIN,
    ("POST", "/integrations/{integration_id}/regenerate-secret"): SCOPE_ADMIN,
    ("POST", "/integrations/{provider}/webhook"): PUBLIC,
    # runbooks.py: feedback on a linked runbook stays open to viewers
    ("POST", "/runbooks"): SCOPE_WRITE,
    ("POST", "/runbooks/from-issue/{issue_id}"): SCOPE_WRITE,
    ("DELETE", "/runbooks/{runbook_id}"): SCOPE_ADMIN,
    ("PATCH", "/runbooks/{runbook_id}"): SCOPE_WRITE,
    ("POST", "/runbooks/{runbook_id}/link/{issue_id}"): SCOPE_WRITE,
    ("POST", "/runbooks/{runbook_id}/link/{issue_id}/feedback"): ANY_USER,
    # scim.py: provisioning by the identity provider's SCIM token
    ("POST", "/scim/v2/Groups"): SCIM_TOKEN,
    ("DELETE", "/scim/v2/Groups/{group_id}"): SCIM_TOKEN,
    ("POST", "/scim/v2/Users"): SCIM_TOKEN,
    ("DELETE", "/scim/v2/Users/{user_id}"): SCIM_TOKEN,
    ("PUT", "/scim/v2/Users/{user_id}"): SCIM_TOKEN,
    # settings.py: outbound webhooks send tenant data out, so admin-only
    ("POST", "/settings/api-keys"): SCOPE_ADMIN,
    ("DELETE", "/settings/api-keys/{key_id}"): SCOPE_ADMIN,
    ("DELETE", "/settings/sso/config"): SCOPE_ADMIN,
    ("POST", "/settings/sso/config"): SCOPE_ADMIN,
    ("POST", "/settings/sso/domains"): SCOPE_ADMIN,
    ("DELETE", "/settings/sso/domains/{domain}"): SCOPE_ADMIN,
    ("POST", "/settings/sso/domains/{domain}/verify"): SCOPE_ADMIN,
    ("POST", "/settings/sso/test"): SCOPE_ADMIN,
    ("PATCH", "/settings/tenant"): SCOPE_ADMIN,
    ("POST", "/settings/webhooks"): SCOPE_ADMIN,
    ("DELETE", "/settings/webhooks/{webhook_id}"): SCOPE_ADMIN,
    # sso.py: sign-in discovery
    ("POST", "/auth/sso/discover"): PUBLIC,
}

_SCOPE_GATED = sorted(key for key, gate in POLICY.items() if gate in (SCOPE_WRITE, SCOPE_ADMIN))
_ADMIN_ONLY = sorted(key for key, gate in POLICY.items() if gate == SCOPE_ADMIN)


@pytest.fixture(scope="module")
def stub() -> MagicMock:
    """Return the stand-in for every service dependency."""
    return MagicMock()


@pytest.fixture(scope="module")
def app(stub: MagicMock) -> FastAPI:
    """Return an app serving every EE route with real auth and stubbed services."""
    app = FastAPI()
    for router in (
        audit_router,
        automation_router,
        integrations_router,
        runbooks_router,
        scim_router,
        settings_router,
        sso_router,
    ):
        app.include_router(router)
    stub_service_dependencies(app, stub, EXTRA_GATES)
    return app


@pytest.fixture
def client(app: FastAPI, stub: MagicMock) -> TestClient:
    """Return a client for the app, with a fresh stub.

    Server errors become 500 responses so an open gate fails the status
    assertion instead of erroring inside the handler.
    """
    stub.reset_mock()
    return TestClient(app, raise_server_exceptions=False)


def test_policy_lists_every_mutating_route(app: FastAPI) -> None:
    """A new write route needs a deliberate entry in POLICY."""
    assert set(mutating_routes(app)) == set(POLICY)


@pytest.mark.parametrize(("method", "path"), sorted(POLICY))
def test_route_enforces_its_policy(app: FastAPI, method: str, path: str) -> None:
    """Each route's dependencies enforce exactly the gate POLICY names."""
    route = mutating_routes(app)[(method, path)]

    assert route_gate(route, EXTRA_GATES) == POLICY[(method, path)]


@pytest.mark.parametrize("via", JWT_VIAS)
@pytest.mark.parametrize(("method", "path"), _SCOPE_GATED)
def test_viewer_is_rejected_before_the_handler(
    client: TestClient, stub: MagicMock, method: str, path: str, via: str
) -> None:
    """A viewer JWT gets 403 and no service is touched."""
    response = client.request(
        method, concrete_path(path), **jwt_request_kwargs(OrgRole.VIEWER, via)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == scope_denied_detail(POLICY[(method, path)])
    assert stub.mock_calls == []


@pytest.mark.parametrize("via", JWT_VIAS)
@pytest.mark.parametrize(("method", "path"), _ADMIN_ONLY)
def test_member_is_rejected_from_admin_routes(
    client: TestClient, stub: MagicMock, method: str, path: str, via: str
) -> None:
    """A member JWT gets 403 on admin routes and no service is touched."""
    response = client.request(
        method, concrete_path(path), **jwt_request_kwargs(OrgRole.MEMBER, via)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == scope_denied_detail(SCOPE_ADMIN)
    assert stub.mock_calls == []
